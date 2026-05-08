import argparse
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import Optional
from urllib.parse import quote, unquote

from google.cloud import storage
from google import genai
from google.genai.types import Part
import docx
import olefile
import openpyxl
import xlrd


CHECKPOINT_EVERY = 50  # upload progress to GCS after this many new entries
MAX_DESCRIPTION_CHARS = 200


def truncate_description(text: str) -> str:
    """Collapse whitespace (including newlines), then truncate at the last complete word within MAX_DESCRIPTION_CHARS."""
    text = " ".join(text.split())
    if len(text) <= MAX_DESCRIPTION_CHARS:
        return text
    truncated = text[:MAX_DESCRIPTION_CHARS]
    last_space = truncated.rfind(" ")
    return truncated[:last_space] if last_space > 0 else truncated


def extract_folder_path(blob_name: str, docs_prefix: str) -> str:
    """Return the folder path of a blob relative to docs_prefix.

    'spec-sheets/docs/Sonos/file.pdf' with prefix 'spec-sheets/docs/'
    → 'Sonos'

    A file directly under docs/ returns ''.
    """
    relative = blob_name[len(docs_prefix):]  # e.g. 'Sonos/file.pdf'
    parts = relative.rsplit("/", 1)
    return parts[0] if len(parts) > 1 else ""


def encode_gcs_url(url: str) -> str:
    """Normalize the path portion of a GCS HTTPS URL to percent-encoded form.

    Fully decodes the path (handling any level of double/triple encoding)
    then re-encodes once. Idempotent on subsequent calls.
    Migrates old storage.googleapis.com URLs to storage.cloud.google.com.
    """
    for old_prefix in ("https://storage.googleapis.com/", "https://storage.cloud.google.com/"):
        if url.startswith(old_prefix):
            path = url[len(old_prefix):]
            decoded = unquote(path)
            while decoded != unquote(decoded):
                decoded = unquote(decoded)
            return GCS_URL_PREFIX + quote(decoded, safe='/')
    return url


GCS_URL_PREFIX = "https://storage.cloud.google.com/"


def build_gcs_url(bucket: str, blob_name: str) -> str:
    """Construct the authenticated HTTPS URL for a GCS object.

    Uses storage.cloud.google.com which prompts for Google account auth,
    required for private buckets. Encodes the blob path so filenames with
    spaces and special characters produce valid URLs.
    """
    return f"{GCS_URL_PREFIX}{bucket}/{quote(blob_name, safe='/')}"


def detect_mime(filename: str) -> Optional[str]:
    """Return the Gemini-native MIME type for a filename, or None.

    None means Gemini cannot consume this file type via GCS URI.
    generate_description() handles None by checking the extension again
    to decide between text extraction (DOCX/XLSX) and filename fallback.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime_map = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "tiff": "image/tiff",
        "tif": "image/tiff",
        "webp": "image/webp",
        "gif": "image/gif",
    }
    return mime_map.get(ext)


def build_entry(
    filename: str,
    folder_path: str,
    gcs_url: str,
    gcs_generation: str,
    description: str,
) -> dict:
    """Assemble one index entry. drive_file_id is always '' during POC."""
    return {
        "filename": filename,
        "folder_path": folder_path,
        "gcs_url": gcs_url,
        "gcs_generation": gcs_generation,
        "drive_file_id": "",
        "description": description,
    }


def entry_to_text(entry: dict) -> str:
    """Serialize an entry dict to a labeled text block (no trailing newline).

    Empty values omit the trailing space (e.g. 'Drive File ID:' not 'Drive File ID: ').
    parse_text_entry handles both forms correctly via its ': ' guard.
    """
    lines = [
        f"Document: {entry['filename']}",
        f"Folder: {entry['folder_path']}",
        f"Description: {entry['description']}",
        f"URL: {entry['gcs_url']}",
        f"GCS Generation: {entry['gcs_generation']}",
        f"Drive File ID: {entry['drive_file_id']}".rstrip(),
    ]
    return "\n".join(lines)


def parse_text_entry(block: str) -> Optional[dict]:
    """Parse a labeled text block into an entry dict.

    Uses partition(': ') so Description values containing ': ' are preserved intact.
    Returns None if required fields (Document, URL) are missing or the block is empty.

    Lines without ': ' are silently skipped. This means a hand-edited entry with
    a missing space after the colon (e.g. 'Document:foo.pdf') will silently drop
    that field, returning None if it was a required field. Machine-written files
    are not affected.
    """
    if not block.strip():
        return None
    fields = {}
    for line in block.strip().splitlines():
        if ": " in line:
            key, _, value = line.partition(": ")
            fields[key.strip()] = value  # preserve value exactly, no strip
    try:
        return {
            "filename": fields["Document"],
            "folder_path": fields.get("Folder", ""),
            "gcs_url": fields["URL"],
            "gcs_generation": fields.get("GCS Generation", ""),
            "drive_file_id": fields.get("Drive File ID", ""),
            "description": fields.get("Description", ""),
        }
    except KeyError:
        return None


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate index.txt for a GCS category folder."
    )
    parser.add_argument("--bucket", required=True, help="GCS bucket name")
    parser.add_argument("--category", required=True, help="Category folder (e.g. spec-sheets, sops, vendors)")
    parser.add_argument("--project", required=True, help="GCP project ID")
    parser.add_argument("--region", default="us-central1", help="Vertex AI region")
    parser.add_argument("--model", default="publishers/google/models/gemini-2.5-flash", help="Gemini model ID")
    parser.add_argument("--dry-run", action="store_true", help="Scan only, no writes")
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing index and reprocess all files")
    return parser.parse_args()


IGNORED_FILENAMES = {".DS_Store"}


def list_gcs_objects(bucket_name: str, prefix: str, project: str) -> list:
    """List all blobs under prefix in the bucket. Returns list of Blob objects."""
    client = storage.Client(project=project)
    blobs = list(client.list_blobs(bucket_name, prefix=prefix))
    return [
        b for b in blobs
        if not b.name.endswith("/")
        and b.name.rsplit("/", 1)[-1] not in IGNORED_FILENAMES
    ]


def load_existing_index(bucket_name: str, category: str, project: str) -> tuple:
    """Load existing index.txt from GCS.

    Returns a tuple of:
      - entries: list of existing entry dicts (to carry forward into the new index)
      - seen:    {gcs_url: gcs_generation} for skip-check logic

    A blob is skipped only if its URL and generation both match an existing entry,
    meaning the file content is unchanged. A re-uploaded file (same URL, new
    generation) will be reprocessed and its entry replaced.

    Returns ([], {}) if the index does not exist or cannot be read.
    """
    client = storage.Client(project=project)
    blob = client.bucket(bucket_name).blob(f"{category}/index.txt")
    try:
        if not blob.exists():
            return [], {}
        content = blob.download_as_text()
        entries = []
        seen = {}
        for block in content.strip().split("\n\n"):
            entry = parse_text_entry(block)
            if entry:
                entry["gcs_url"] = encode_gcs_url(entry["gcs_url"])
                entries.append(entry)
                seen[entry["gcs_url"]] = entry["gcs_generation"]
        return entries, seen
    except Exception as e:
        print(f"  Warning: could not load existing index: {e}")
        return [], {}


def checkpoint_to_gcs(tmp_path: str, bucket_name: str, category: str, project: str) -> None:
    """Upload the current temp file to GCS as index.txt."""
    client = storage.Client(project=project)
    blob = client.bucket(bucket_name).blob(f"{category}/index.txt")
    blob.upload_from_filename(tmp_path, content_type="text/plain")


def _build_prompt(category: str, filename: str, folder_path: str, content_available: bool) -> str:
    """Build a category-aware Gemini prompt.

    For spec-sheets: focus on manufacturer, product name, and key specs.
    For hr-operations: focus on topics and policies an employee would search for.
    When content is not available, instructs Gemini to infer from metadata only.
    """
    char_limit = f"one complete sentence of no more than {MAX_DESCRIPTION_CHARS} characters"
    folder_label = f"the '{folder_path}' subfolder" if folder_path else "the root folder"

    if not content_available:
        base = (
            f"Based only on the filename and location (you do not have access to the file "
            f"content), write {char_limit} describing what this file likely contains. "
            f"The file is named '{filename}' in {folder_label}."
        )
    else:
        base = f"Write {char_limit} describing this document."

    style = (
        " Do not refer to the document itself. Do not start with 'This', 'This document',"
        " 'This is', or similar phrases. Write the content directly as a catalog entry or"
        " search snippet — state the subject first, then key details."
    )

    if category == "spec-sheets":
        focus = (
            " Format: '[Manufacturer] [Product]: [key specs and features a technician or"
            " engineer would search for].'"
        )
    elif category == "vendors":
        focus = (
            " Format: '[Vendor] [Product/Topic]: [key procedures, specifications, or"
            " configuration details a field technician would search for].'"
        )
    elif category == "sops":
        focus = (
            " Format: '[Procedure or topic name]: [key steps, equipment, or systems covered"
            " that a field technician would search for].'"
        )
    else:
        # hr-operations and any future categories
        focus = (
            " Format: '[Policy or topic name]: [key points covered that an employee would"
            " search for].' Do not mention authorship or consulting firms."
        )

    return base + style + focus


def generate_description(
    gcs_uri: str,
    mime,
    filename: str,
    folder_path: str,
    args,
) -> str:
    """Generate a one-sentence description for a document.

    Routing:
    - mime is not None (PDF/image) → Part.from_uri() → Gemini
    - mime is None, ext is .docx   → download → python-docx → Gemini
    - mime is None, ext is .xlsx   → download → openpyxl → Gemini
    - mime is None, ext is .xls    → download → xlrd → Gemini
    - mime is None, ext is .doc    → download → olefile → Gemini
    - extraction fails or unsupported type → metadata-only prompt → Gemini
    """
    client = genai.Client(
        vertexai=True,
        project=args.project,
        location=args.region,
    )

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_prompt = _build_prompt(args.category, filename, folder_path, content_available=True)

    if mime is not None:
        # PDF or image — pass GCS URI directly, Gemini reads from GCS
        contents = [Part.from_uri(file_uri=gcs_uri, mime_type=mime), content_prompt]
    elif ext == "docx":
        contents = _build_docx_contents(gcs_uri, content_prompt, args.project)
    elif ext == "xlsx":
        contents = _build_xlsx_contents(gcs_uri, content_prompt, args.project)
    elif ext == "xls":
        contents = _build_xls_contents(gcs_uri, content_prompt, args.project)
    elif ext == "doc":
        contents = _build_doc_contents(gcs_uri, content_prompt, args.project)
    else:
        contents = None

    if contents is None:
        # Unsupported type or extraction failed — infer from metadata only
        contents = [_build_prompt(args.category, filename, folder_path, content_available=False)]

    return _call_gemini_with_retry(client, args.model, contents, filename)


def _call_gemini_with_retry(client, model: str, contents: list, filename: str) -> str:
    """Call Gemini with exponential backoff. Falls back to filename on failure.

    delays defines both the number of attempts (len=3) and the sleep duration after
    each failure. The sleep occurs only in the except block, so the first attempt
    runs immediately.
    """
    delays = [1, 2, 4]
    for attempt, delay in enumerate(delays):
        try:
            response = client.models.generate_content(model=model, contents=contents)
            text = response.text
            if not text:
                print(f"  Gemini returned empty response for {filename}, using filename as fallback")
                return truncate_description(filename)
            return truncate_description(text)
        except Exception as e:
            if attempt < len(delays) - 1:
                print(f"  Gemini retry {attempt + 1} for {filename}: {e}")
                time.sleep(delay)
            else:
                print(f"  Gemini failed for {filename} after {len(delays)} attempts: {e}")
                return truncate_description(filename)


def _build_docx_contents(gcs_uri: str, prompt: str, project: str) -> list:
    """Download a DOCX from GCS and extract its text. Returns Gemini contents list or None on failure."""
    try:
        client = storage.Client(project=project)
        # gcs_uri is 'gs://bucket/path' — parse bucket and blob name
        path = gcs_uri[len("gs://"):]
        bucket_name, blob_name = path.split("/", 1)
        blob = client.bucket(bucket_name).blob(blob_name)
        data = BytesIO(blob.download_as_bytes())
        doc = docx.Document(data)
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return [text[:10000], prompt]  # cap extracted text to avoid token limits
    except Exception as e:
        print(f"  DOCX extraction failed for {gcs_uri}: {e}")
        return None


def _build_xlsx_contents(gcs_uri: str, prompt: str, project: str) -> list:
    """Download an XLSX from GCS and extract its cell data. Returns Gemini contents list or None on failure."""
    try:
        client = storage.Client(project=project)
        path = gcs_uri[len("gs://"):]
        bucket_name, blob_name = path.split("/", 1)
        blob = client.bucket(bucket_name).blob(blob_name)
        data = BytesIO(blob.download_as_bytes())
        wb = openpyxl.load_workbook(data, read_only=True, data_only=True)
        rows = []
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                row_text = "\t".join(str(c) for c in row if c is not None)
                if row_text.strip():
                    rows.append(row_text)
        text = "\n".join(rows)
        return [text[:10000], prompt]
    except Exception as e:
        print(f"  XLSX extraction failed for {gcs_uri}: {e}")
        return None


def _extract_doc_text(data: bytes) -> str:
    """Extract readable text from a Word .doc binary using olefile.

    Word .doc files use OLE2 compound document format. The body text lives in
    the 'WordDocument' stream encoded as UTF-16LE, interleaved with binary
    formatting bytes. This extracts contiguous word-like sequences from that
    stream — imperfect but sufficient for Gemini description generation.
    """
    try:
        if not olefile.isOleFile(data):
            # Not an OLE file — try brute-force ASCII extraction as fallback
            sequences = re.findall(rb'[ -~]{5,}', data)
            return "\n".join(s.decode("ascii", errors="ignore") for s in sequences)

        ole = olefile.OleFileIO(BytesIO(data))
        text_parts = []

        if ole.exists("WordDocument"):
            raw = ole.openstream("WordDocument").read()
            # Text is UTF-16LE; decode and strip control characters
            decoded = raw.decode("utf-16-le", errors="ignore")
            cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", decoded)
            # Keep only runs of printable characters
            words = re.findall(r"[A-Za-z0-9 \t.,;:/()\-]{4,}", cleaned)
            text_parts.append(" ".join(words))

        return "\n".join(text_parts).strip()
    except Exception:
        return ""


def _build_doc_contents(gcs_uri: str, prompt: str, project: str) -> list:
    """Download a DOC from GCS and extract text via OLE2 parsing. Returns Gemini contents list or None on failure."""
    try:
        client = storage.Client(project=project)
        path = gcs_uri[len("gs://"):]
        bucket_name, blob_name = path.split("/", 1)
        blob = client.bucket(bucket_name).blob(blob_name)
        data = blob.download_as_bytes()
        text = _extract_doc_text(data)
        if not text.strip():
            print(f"  DOC extraction yielded no text for {gcs_uri}, using metadata fallback")
            return None
        return [text[:10000], prompt]
    except Exception as e:
        print(f"  DOC extraction failed for {gcs_uri}: {e}")
        return None


def _build_xls_contents(gcs_uri: str, prompt: str, project: str) -> list:
    """Download an XLS from GCS and extract its cell data via xlrd. Returns Gemini contents list or None on failure."""
    try:
        client = storage.Client(project=project)
        path = gcs_uri[len("gs://"):]
        bucket_name, blob_name = path.split("/", 1)
        blob = client.bucket(bucket_name).blob(blob_name)
        data = blob.download_as_bytes()
        wb = xlrd.open_workbook(file_contents=data)
        rows = []
        for sheet in wb.sheets():
            for row_idx in range(sheet.nrows):
                row_text = "\t".join(str(sheet.cell_value(row_idx, col)) for col in range(sheet.ncols))
                if row_text.strip():
                    rows.append(row_text)
        text = "\n".join(rows)
        return [text[:10000], prompt]
    except Exception as e:
        print(f"  XLS extraction failed for {gcs_uri}: {e}")
        return None


def process_file(blob, docs_prefix: str, args) -> Optional[dict]:
    """Process one GCS blob into an index entry. Returns None on unrecoverable error."""
    try:
        filename = blob.name.rsplit("/", 1)[-1]
        folder_path = extract_folder_path(blob.name, docs_prefix)
        gcs_url = build_gcs_url(args.bucket, blob.name)
        gcs_uri = f"gs://{args.bucket}/{blob.name}"
        gcs_generation = str(blob.generation)
        mime = detect_mime(filename)

        if args.dry_run:
            print(f"  [dry-run] {filename} | folder_path={folder_path!r} | url={gcs_url}")
            return None

        print(f"  Processing {filename}...")
        description = generate_description(gcs_uri, mime, filename, folder_path, args)
        return build_entry(filename, folder_path, gcs_url, gcs_generation, description)

    except Exception as e:
        print(f"  ERROR processing {blob.name}: {e}")
        return None


def print_summary(total: int, new_entries: int, errors: int, skipped: int) -> None:
    print("\n--- Summary ---")
    print(f"  Files found:            {total}")
    print(f"  Skipped (already done): {skipped}")
    print(f"  Processed:              {total - skipped}")
    print(f"  New entries written:    {new_entries}")
    print(f"  Errors:                 {errors}")


def main():
    args = parse_args()
    docs_prefix = f"{args.category}/docs/"
    print(f"Scanning gs://{args.bucket}/{docs_prefix}")

    blobs = list_gcs_objects(args.bucket, docs_prefix, args.project)
    if not blobs:
        print("No files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(blobs)} file(s).")

    if args.dry_run:
        print("--- DRY RUN: listing files only, no Gemini calls, no write ---")
        for blob in blobs:
            process_file(blob, docs_prefix, args)
        print(f"--- DRY RUN complete: {len(blobs)} file(s) listed ---")
        return

    # Load existing index for resumability (unless --no-resume)
    existing_entries = []
    seen = {}
    if not args.no_resume:
        existing_entries, seen = load_existing_index(args.bucket, args.category, args.project)
        if existing_entries:
            print(f"Resuming: {len(existing_entries)} existing entries found.")

    # Skip blobs already indexed at the same generation (url + generation must match).
    # Re-uploaded files (same URL, new generation) are reprocessed and their entry replaced.
    blobs_to_process = [
        b for b in blobs
        if seen.get(build_gcs_url(args.bucket, b.name)) != str(b.generation)
    ]
    skipped = len(blobs) - len(blobs_to_process)
    if skipped:
        print(f"Skipping {skipped} already-indexed file(s). Processing {len(blobs_to_process)} new file(s).")

    new_entries_count = 0
    errors = 0

    # Write to a local temp file; checkpoint to GCS every CHECKPOINT_EVERY new entries.
    # as_completed() yields results in the main thread, so file writes and GCS uploads
    # are sequential — no locking required.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(tmp_fd, "w") as tmp:
            # Seed temp file with existing entries so every checkpoint is complete.
            # Entries for re-uploaded files are omitted here; new entries replace them.
            reprocessed_urls = {build_gcs_url(args.bucket, b.name) for b in blobs_to_process}
            for entry in existing_entries:
                if entry["gcs_url"] not in reprocessed_urls:
                    tmp.write(entry_to_text(entry) + "\n\n")
            tmp.flush()

            if blobs_to_process:
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {
                        executor.submit(process_file, blob, docs_prefix, args): blob
                        for blob in blobs_to_process
                    }
                    for future in as_completed(futures):
                        result = future.result()
                        if result is not None:
                            tmp.write(entry_to_text(result) + "\n\n")
                            tmp.flush()
                            new_entries_count += 1
                            if new_entries_count % CHECKPOINT_EVERY == 0:
                                checkpoint_to_gcs(tmp_path, args.bucket, args.category, args.project)
                                print(f"  Checkpoint: {new_entries_count} new entries saved to GCS.")
                        else:
                            errors += 1

        total_entries = new_entries_count + skipped
        if total_entries == 0:
            print("No entries generated — nothing to write.", file=sys.stderr)
            print_summary(len(blobs), new_entries_count, errors, skipped)
            sys.exit(1)

        # Final upload
        checkpoint_to_gcs(tmp_path, args.bucket, args.category, args.project)
        print(f"Wrote {total_entries} entries to gs://{args.bucket}/{args.category}/index.txt")

    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    print_summary(len(blobs), new_entries_count, errors, skipped)


if __name__ == "__main__":
    main()
