# Google Chat Knowledge Assistants

A design guide and prompt library for building conversational knowledge assistants that live inside Google Chat, powered by Dialogflow CX and Vertex AI RAG.

Users ask questions in natural language — the agent finds the most relevant documents in your Google Cloud Storage library, synthesizes a clear answer, and includes direct download links to the source files.

## What You Get

- Natural language Q&A over your internal document library
- Direct download links to source files returned with every answer
- Bilingual support (the agent responds in the language the user writes in)
- A file discovery mode ("show me all Lutron docs") separate from content Q&A
- Inline citations so users know exactly which document each answer came from

## Architecture

```
Google Chat → Dialogflow CX Agent → Vertex AI Search (RAG) → GCS Documents
```

This stack runs entirely on Google Cloud and integrates natively with Google Workspace. If your organization already uses Google Chat, setup requires no additional infrastructure beyond a GCP project and document storage.

Two bot personalities are included as templates: a **general-purpose assistant** (for HR policies, operational procedures, company handbooks) and a **technical specialist** (for vendor manuals, SOPs, and step-by-step technical procedures). Both share the same architecture — the difference is in tone, routing logic, and how strictly they reproduce source content.

## Documentation

| Document | Description |
|----------|-------------|
| [architecture.md](architecture.md) | System architecture, components, tool design pattern, prompt architecture, GCS layout |
| [setup-guide.md](setup-guide.md) | Step-by-step GCP setup: project, storage, data stores, agent, Chat integration |
| [prompt-templates.md](prompt-templates.md) | All prompt templates for both bot personalities with difference callouts |
| [gotchas.md](gotchas.md) | Known issues, pitfalls, and roadmap |
| [sync-workflow.md](sync-workflow.md) | Make.com automation for document sync between GCS and Vertex AI |

## Ready-to-Use Prompts

The `bots/` folder contains ready-to-paste prompt files organized by bot type:

```
bots/
├── general-bot/prompts/
│   ├── goal.txt                      # Playbook goal
│   ├── instructions.txt              # Playbook instructions
│   ├── tool-docs.txt                 # Docs tool description
│   ├── tool-docs-rewriter.txt        # Docs query rewriter
│   ├── tool-docs-summarization.txt   # Docs response summarizer
│   ├── tool-index.txt                # Index tool description
│   ├── tool-index-rewriter.txt       # Index query rewriter
│   └── tool-index-summarization.txt  # Index response summarizer
└── technical-bot/prompts/
    └── (same 8 files, technical variant)
```

Replace `[Company]`, `[Agent Name]`, `[Domain]`, and other bracketed placeholders with your values, then paste directly into Dialogflow CX.

## Index Generation Script

The `shared/scripts/generate_index.py` script scans a GCS folder, generates a one-sentence Gemini description per document, and writes an `index.txt` file for the INDEX tool's data store.

```bash
python shared/scripts/generate_index.py \
  --bucket your-bucket \
  --category your-domain-folder \
  --project your-gcp-project \
  --dry-run
```

Supports PDF, DOCX, XLSX, XLS, DOC, and image files. Includes resume logic and checkpointing for large document libraries.

### Prerequisites

**Google Cloud SDK (`gcloud`)** — the command-line tool for interacting with Google Cloud. If you don't have it installed:

1. Download from https://cloud.google.com/sdk/docs/install (macOS, Linux, Windows)
2. Run `gcloud init` to authenticate and select your project
3. Verify with `gcloud --version`

**Python 3.9+** with pip.

Then authenticate and install dependencies:

```bash
# Authenticate with Google Cloud (opens a browser)
gcloud auth application-default login

# Set your project for API quota (required for Gemini API calls)
gcloud auth application-default set-quota-project your-gcp-project

# Install Python dependencies
pip install google-cloud-storage google-genai python-docx openpyxl xlrd olefile
```

## Quick Start

1. Read [architecture.md](architecture.md) to understand the component design
2. Follow [setup-guide.md](setup-guide.md) to create your GCP resources
3. Copy prompt files from `bots/general-bot/prompts/` or `bots/technical-bot/prompts/`
4. Replace all `[bracketed placeholders]` with your company/domain values
5. Paste prompts into Dialogflow CX (goal, instructions, tool descriptions, rewriters, summarizers)
6. Run `generate_index.py` to create your document index
7. Review [gotchas.md](gotchas.md) before going to production

## License

MIT
