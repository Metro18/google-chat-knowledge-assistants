from generate_index import truncate_description
from generate_index import extract_folder_path
from generate_index import build_gcs_url
from generate_index import detect_mime
from generate_index import build_entry


def test_truncate_description_long():
    # Text with no spaces: truncates hard at MAX_DESCRIPTION_CHARS
    long_text = "A" * 250
    result = truncate_description(long_text)
    assert len(result) == 200


def test_truncate_description_word_boundary():
    # Truncation lands on a word boundary, not mid-word
    long_text = ("word " * 60).strip()  # well over 200 chars
    result = truncate_description(long_text)
    assert len(result) <= 200
    assert result.endswith("word")


def test_truncate_description_short():
    text = "Short description."
    result = truncate_description(text)
    assert result == "Short description."


def test_truncate_description_strips_whitespace():
    # Strip happens BEFORE truncation
    padded = "  " + "A" * 198 + "  "
    result = truncate_description(padded)
    assert result == "A" * 198
    assert len(result) == 198


def test_truncate_description_collapses_newlines():
    # Embedded newlines must be collapsed — newlines in a Description field
    # would break the labeled text block format used by parse_text_entry.
    text = "First sentence.\nSecond sentence."
    result = truncate_description(text)
    assert "\n" not in result
    assert result == "First sentence. Second sentence."


def test_extract_folder_path_nested():
    blob_name = "spec-sheets/docs/Sonos/Sonos-Arc-Spec.pdf"
    docs_prefix = "spec-sheets/docs/"
    result = extract_folder_path(blob_name, docs_prefix)
    assert result == "Sonos"


def test_extract_folder_path_root():
    blob_name = "hr-operations/docs/Employee-Handbook.pdf"
    docs_prefix = "hr-operations/docs/"
    result = extract_folder_path(blob_name, docs_prefix)
    assert result == ""


def test_extract_folder_path_deeply_nested():
    blob_name = "spec-sheets/docs/Audio/Sonos/Sonos-Arc-Spec.pdf"
    docs_prefix = "spec-sheets/docs/"
    result = extract_folder_path(blob_name, docs_prefix)
    assert result == "Audio/Sonos"


def test_build_gcs_url():
    result = build_gcs_url("my-docs-bucket", "spec-sheets/docs/Sonos/Sonos-Arc-Spec.pdf")
    assert result == "https://storage.cloud.google.com/my-docs-bucket/spec-sheets/docs/Sonos/Sonos-Arc-Spec.pdf"


def test_detect_mime_pdf():
    assert detect_mime("Handbook.pdf") == "application/pdf"


def test_detect_mime_png():
    assert detect_mime("diagram.png") == "image/png"


def test_detect_mime_jpg():
    assert detect_mime("photo.jpg") == "image/jpeg"


def test_detect_mime_jpeg():
    assert detect_mime("photo.jpeg") == "image/jpeg"


def test_detect_mime_webp():
    assert detect_mime("image.webp") == "image/webp"


def test_detect_mime_gif():
    assert detect_mime("anim.gif") == "image/gif"


def test_detect_mime_tiff():
    assert detect_mime("scan.tiff") == "image/tiff"


def test_detect_mime_tif():
    assert detect_mime("scan.tif") == "image/tiff"


def test_detect_mime_docx():
    # DOCX requires text extraction — detect_mime returns None
    assert detect_mime("Policy.docx") is None


def test_detect_mime_xlsx():
    # XLSX requires text extraction — detect_mime returns None
    assert detect_mime("Budget.xlsx") is None


def test_detect_mime_unknown():
    assert detect_mime("readme.txt") is None


REQUIRED_FIELDS = {"filename", "folder_path", "gcs_url", "gcs_generation", "drive_file_id", "description"}


def test_build_entry_fields():
    entry = build_entry(
        filename="Sonos-Arc-Spec.pdf",
        folder_path="Sonos",
        gcs_url="https://storage.cloud.google.com/my-docs-bucket/spec-sheets/docs/Sonos/Sonos-Arc-Spec.pdf",
        gcs_generation="1234567890",
        description="Sonos Arc premium soundbar with Dolby Atmos.",
    )
    assert set(entry.keys()) == REQUIRED_FIELDS
    assert entry["filename"] == "Sonos-Arc-Spec.pdf"
    assert entry["folder_path"] == "Sonos"
    assert entry["drive_file_id"] == ""   # always empty during POC
    assert entry["gcs_generation"] == "1234567890"  # must be string, not int


from generate_index import entry_to_text


def test_entry_to_text():
    entry = {
        "filename": "Sonos-Arc-Spec.pdf",
        "folder_path": "Sonos",
        "gcs_url": "https://storage.cloud.google.com/my-docs-bucket/spec-sheets/docs/Sonos/Sonos-Arc-Spec.pdf",
        "gcs_generation": "1234567890",
        "drive_file_id": "",
        "description": "Sonos Arc premium soundbar with Dolby Atmos.",
    }
    result = entry_to_text(entry)
    assert result == (
        "Document: Sonos-Arc-Spec.pdf\n"
        "Folder: Sonos\n"
        "Description: Sonos Arc premium soundbar with Dolby Atmos.\n"
        "URL: https://storage.cloud.google.com/my-docs-bucket/spec-sheets/docs/Sonos/Sonos-Arc-Spec.pdf\n"
        "GCS Generation: 1234567890\n"
        "Drive File ID:"
    )


def test_entry_to_text_description_with_colon():
    # Descriptions containing ': ' must survive serialization intact
    entry = {
        "filename": "doc.pdf",
        "folder_path": "",
        "gcs_url": "https://storage.cloud.google.com/bucket/doc.pdf",
        "gcs_generation": "999",
        "drive_file_id": "",
        "description": "HR policy: covers leave, benefits, and conduct.",
    }
    result = entry_to_text(entry)
    assert "Description: HR policy: covers leave, benefits, and conduct." in result


from generate_index import parse_text_entry


def test_parse_text_entry_roundtrip():
    entry = {
        "filename": "Sonos-Arc-Spec.pdf",
        "folder_path": "Sonos",
        "gcs_url": "https://storage.cloud.google.com/my-docs-bucket/spec-sheets/docs/Sonos/Sonos-Arc-Spec.pdf",
        "gcs_generation": "1234567890",
        "drive_file_id": "",
        "description": "Sonos Arc premium soundbar with Dolby Atmos.",
    }
    block = entry_to_text(entry)
    result = parse_text_entry(block)
    assert result == entry


def test_parse_text_entry_description_with_colon():
    # Descriptions containing ': ' must round-trip without truncation
    entry = {
        "filename": "doc.pdf",
        "folder_path": "",
        "gcs_url": "https://storage.cloud.google.com/bucket/doc.pdf",
        "gcs_generation": "999",
        "drive_file_id": "",
        "description": "HR policy: covers leave, benefits, and conduct.",
    }
    assert parse_text_entry(entry_to_text(entry)) == entry


def test_parse_text_entry_missing_required_field_returns_none():
    block = "Folder: Sonos\nURL: https://example.com/file.pdf"
    assert parse_text_entry(block) is None


def test_parse_text_entry_empty_block_returns_none():
    assert parse_text_entry("") is None
    assert parse_text_entry("   \n  ") is None


def test_parse_text_entry_skips_malformed_lines():
    # Lines without ': ' are silently skipped; required fields still present → returns entry
    block = (
        "Document: file.pdf\n"
        "this line has no colon separator\n"
        "URL: https://storage.cloud.google.com/bucket/file.pdf\n"
        "GCS Generation: 42\n"
        "Drive File ID: \n"
        "Description: A file."
    )
    result = parse_text_entry(block)
    assert result is not None
    assert result["filename"] == "file.pdf"
