# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository is a design guide and prompt library for building **Google Chat knowledge assistants** powered by Dialogflow CX and Vertex AI RAG. It documents how to build bots that answer questions by searching a library of documents in Google Cloud Storage.

Two bot personalities are included as examples:

- **General Bot** — HR policies, operational procedures, and equipment specs for all employees (bilingual EN/ES)
- **Technical Bot** — vendor manuals, SOPs, and technical procedures for technicians and installers (bilingual EN/ES)

Both share the same architecture pattern but live in separate GCP projects (required by Google Chat's project-level bot identity).

## Repository Structure

```text
├── README.md                  # project overview and quick start
├── CLAUDE.md                  # this file
├── architecture.md            # system architecture and component design
├── setup-guide.md             # step-by-step GCP setup instructions
├── prompt-templates.md        # all prompt templates with both bot variants
├── gotchas.md                 # known issues, pitfalls, and next steps
├── sync-workflow.md           # Make.com document sync automation
├── shared/
│   └── scripts/               # generate_index.py + tests
├── bots/
│   ├── general-bot/           # see "Bot Folder Structure" below
│   └── technical-bot/
└── old/                       # archived iterations
```

### Bot Folder Structure

Every bot under `bots/` follows the same folder layout:

```text
bots/<botname>/
├── <BOTNAME>.md               # bot-specific config (see "Bot MD File Structure")
├── prompts/                   # Dialogflow CX prompts (goal, instructions, tool-*)
├── playbooks/                 # playbook examples for Dialogflow CX
├── docs/                      # specifications, checklists, design docs
├── source-docs/               # local copies of documents uploaded to GCS
├── output/                    # generated files (index.txt, import logs)
└── assets/                    # avatar images
```

### Bot MD File Structure

Each `<BOTNAME>.md` file uses the same section order:

| Section | Purpose |
|---------|---------|
| **Infrastructure** | GCP project, bucket, agent ID, model, location |
| **Tool Design** | Tools, data store config, GCS bucket structure |
| **Prompt Files** | Map of Dialogflow CX fields → local prompt files |
| **Response Requirements** | Word counts, citation format, language rules |
| **Domain Coverage** | Topics, vendors, or document types this bot covers |
| **Security Considerations** | Privacy constraints, NDA notes (N/A if none) |
| **Implementation Checklist** | Link to task tracker (N/A if none) |
| **Future Considerations** | Planned improvements |
| **Full Specification** | Link to detailed spec doc (N/A if none) |

## Scripts

### Index Generation (`shared/scripts/generate_index.py`)

Scans a GCS category folder, generates a Gemini description per document, and writes `index.txt`.

**Run (dry-run):**
```bash
python shared/scripts/generate_index.py \
  --bucket [your-gcs-bucket] \
  --category [category-name] \
  --project [your-gcp-project] \
  --dry-run
```

**Run tests:**
```bash
pytest shared/scripts/test_generate_index.py
```

**Local GCP auth (one-time):**
```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project [your-gcp-project]
pip install google-cloud-storage google-genai python-docx openpyxl xlrd olefile pytest
```

**File type handling:** PDFs and images via GCS URI (`Part.from_uri()`). DOCX via `python-docx`; XLSX via `openpyxl`. Others fall back to filename.

## Dialogflow CX Architecture — IMPORTANT

In Dialogflow CX, prompts (description, rewriter, summarizer) are configured at the **tool** level. Each tool gets exactly 3 prompt files:
- `tool-{name}.txt` — tool description
- `tool-{name}-rewriter.txt` — query rewriter
- `tool-{name}-summarization.txt` — response summarizer

**Do not create separate prompt files per data store.** A tool may contain one or more data stores, but it always has exactly 3 prompt files.

### Tool Design Pattern — Separate Tools

All bots use **separate tools** for docs and index data stores. Each domain (e.g., HR Policies, Equipment Specs, Technical Documentation) has two tools:

- **Docs tool** — content questions (RAG over full documents). 3 prompt files.
- **Index tool** — file discovery and listings (index.txt). 3 prompt files.

The agent instructions route queries to the correct tool. Each summarizer has a single responsibility — no ambiguity about response type.

**Do not combine docs and index into a single tool.** Combined tools force the summarizer to guess whether the user wants content or a file listing, leading to mixed responses and hedging when both data stores return results. Separate tools keep routing deterministic and prompts simple.

### Structural Parity Across Bots

Bots should maintain structural and formatting parity where appropriate. Instructions files follow a shared section order (`## Heading Name` format), tool prompts follow a shared section layout, and rewriter/summarizer templates use consistent conventions (`User:` label, `-` bullets, `##` sections).

When making structural or formatting changes to one bot's prompts, review the other bots to determine whether the same change should be applied. This is a review step, not an automatic change — bot-specific sections remain unique.

## Known Issues / Gotchas

See [gotchas.md](gotchas.md) for the full list. Key items:

- GCS URLs must use `https://storage.cloud.google.com/` (authenticated) not `https://storage.googleapis.com/`
- `index.txt` must stay outside `docs/` folders or it gets indexed as a document
- Google Chat has a 4,096 character limit — target 3,800 max
- First Vertex AI use: service agents take minutes to provision (`FAILED_PRECONDITION` → wait and retry)
- Session isolation in multi-user spaces is TBD — test in your environment

## Testing

Test cases cover:
- RAG queries (contextual answers from document content)
- File link queries (GCS URL returned correctly)
- File listing queries (multiple results)
- Cross-tool routing (correct tool handles each query type)
- Negative cases (missing documents handled gracefully)
- Bilingual queries (English and Spanish)
