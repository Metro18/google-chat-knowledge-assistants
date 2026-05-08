# Technical Bot — Technical Documentation Assistant

## Infrastructure

| Field | Value |
|-------|-------|
| **Purpose** | Vendor manuals, SOPs, and technical procedures for technicians/installers |
| **GCP Project** | `[your-gcp-project]` |
| **Project Number** | — |
| **GCS Bucket** | `gs://[your-bucket]/` |
| **Interface** | Google Chat |
| **Agent Platform** | Dialogflow CX |
| **Agent Name** | `[your-agent-name]` |
| **Agent ID** | — |
| **RAG Engine** | Vertex AI Search |
| **Data Store** | Dual data store (see below) |
| **Location** | `us-central1` |
| **Model** | `gemini-2.5-flash` |
| **Language** | Bilingual (English/Spanish) |

## Tool Design

The technical bot uses a **two-tool design** — separate docs and index tools. The main agent routes queries to the correct tool:

| Tool | Data Store | Purpose |
|------|------------|---------|
| **TECHNICAL-DOCS** | `[technical-docs-store]` (RAG) | Technical content questions (procedures, config, troubleshooting) |
| **TECHNICAL-INDEX** | `[technical-index-store]` | List/find documents by vendor, product, or topic |

### Data Store Configuration

- Type: Unstructured data
- Sync: One-time (manual re-import for updates)
- Document Processing: Layout Parser enabled
- Chunking: Layout-based, 500 tokens, include ancestor headings

### GCS Bucket Structure

```text
gs://[your-bucket]/
  [technical-docs]/
    index.txt             ← file metadata index (outside docs/)
    docs/
      [vendor-or-category]/  ← technical docs organized by vendor or category
```

## Prompt Files

| Dialogflow CX Location | File |
|-------------------------|------|
| Main Agent Goal | `prompts/goal.txt` |
| Main Agent Instructions | `prompts/instructions.txt` |
| TECHNICAL-DOCS — Description | `prompts/tool-docs.txt` |
| TECHNICAL-DOCS — Query Rewriter | `prompts/tool-docs-rewriter.txt` |
| TECHNICAL-DOCS — Summarizer | `prompts/tool-docs-summarization.txt` |
| TECHNICAL-INDEX — Description | `prompts/tool-index.txt` |
| TECHNICAL-INDEX — Query Rewriter | `prompts/tool-index-rewriter.txt` |
| TECHNICAL-INDEX — Summarizer | `prompts/tool-index-summarization.txt` |

## Response Requirements

- **Procedures**: 300–800 words, full fidelity (no abbreviating steps)
- **Lookups**: 100–200 words
- **Complex topics**: up to 1,000 words
- Exact model numbers, firmware versions, IP addresses preserved from sources
- SOP content prioritized over vendor manual content
- `NOT_ENOUGH_INFORMATION` when sources don't cover the query
- **Character limit**: Google Chat has a 4,096 character limit; responses must stay under 3,800

## Domain Coverage

Replace with your bot's vendor and topic coverage. Example:
- Internal SOPs for installation, configuration, and maintenance procedures
- Vendor manuals for products your team supports (e.g., networking, AV, security, lighting)

## Security Considerations

N/A — replace with any privacy constraints, NDA notes, or client confidentiality requirements specific to your deployment.

## Implementation Checklist

N/A — link to your task tracker if applicable.

## Future Considerations

- Generate `index.txt` for additional document categories (extend `shared/scripts/generate_index.py`)
- Automate document sync / re-import pipeline (see [sync-workflow.md](../../sync-workflow.md))
- Add playbook examples for improved tool routing accuracy

## Full Specification

N/A — link to your detailed spec doc if applicable.
