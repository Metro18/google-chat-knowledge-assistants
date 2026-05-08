# General Bot — Knowledge Assistant

## Infrastructure

| Field | Value |
|-------|-------|
| **Purpose** | HR policies, operational procedures, equipment specs for all employees |
| **GCP Project** | `[your-gcp-project]` |
| **Project Number** | — |
| **GCS Bucket** | `gs://[your-bucket]/` |
| **Interface** | Google Chat |
| **Agent Platform** | Dialogflow CX |
| **Agent Name** | `[your-agent-name]` |
| **Agent ID** | — |
| **RAG Engine** | Vertex AI Search |
| **Data Store** | Dual data store per tool (see below) |
| **Location** | `us-central1` |
| **Model** | `gemini-2.5-flash` |
| **Language** | Multilingual (English/Spanish) |

## Tool Design

The general bot uses a **four-tool design** — separate docs and index tools per domain. The main agent routes queries to the correct tool:

| Tool | Data Store | Purpose |
|------|------------|---------|
| **[DOMAIN-1]-DOCS** | `[domain-1]-docs` (RAG) | Policy/procedure content questions |
| **[DOMAIN-1]-INDEX** | `[domain-1]-index-txt` | Document file discovery and listings |
| **[DOMAIN-2]-DOCS** | `[domain-2]-docs` (RAG) | Content questions for second domain |
| **[DOMAIN-2]-INDEX** | `[domain-2]-index-txt` | Second domain file discovery and listings |

### Data Store Configuration

Each tool contains one Vertex AI Search data store. Prompts (description, rewriter, summarizer) are configured at the tool level — each tool gets exactly 3 prompt files.

The `index.txt` must live *outside* the `docs/` subfolder to prevent Vertex AI from indexing it as a document.

### GCS Bucket Structure

```text
gs://[your-bucket]/
  [domain-1]/
    index.txt             ← file metadata index (outside docs/)
    docs/
      [category]/         ← documents organized by category
  [domain-2]/
    index.txt             ← file metadata index (outside docs/)
    docs/
      [category]/         ← documents organized by category
```

## Prompt Files

| Dialogflow CX Location | File |
|-------------------------|------|
| Main Agent Goal | `prompts/goal.txt` |
| Main Agent Instructions | `prompts/instructions.txt` |
| [DOMAIN-1]-DOCS — Description | `prompts/tool-docs.txt` |
| [DOMAIN-1]-DOCS — Query Rewriter | `prompts/tool-docs-rewriter.txt` |
| [DOMAIN-1]-DOCS — Summarizer | `prompts/tool-docs-summarization.txt` |
| [DOMAIN-1]-INDEX — Description | `prompts/tool-index.txt` |
| [DOMAIN-1]-INDEX — Query Rewriter | `prompts/tool-index-rewriter.txt` |
| [DOMAIN-1]-INDEX — Summarizer | `prompts/tool-index-summarization.txt` |

> **Multi-domain note:** If your general bot covers multiple domains (e.g., HR policies + equipment specs), duplicate the tool prompt files for each additional domain and adjust the tool descriptions and routing table in `instructions.txt`. Each domain gets its own DOCS + INDEX tool pair.

## Response Requirements

- **Policy/procedure answers**: 200–500 words with inline citations
- **File link responses**: include direct GCS download URLs
- **Language**: respond in user's language; technical terms get multilingual parenthetical explanations
- **Sensitive topics**: escalate to appropriate human contact
- **Character limit**: Google Chat has a 4,096 character limit; responses must stay under 3,800

## Domain Coverage

Replace with your bot's domain coverage. Example domains:
- HR policies, employee handbook, benefits, PTO
- Operational procedures, expense reporting, travel policies
- Equipment specifications organized by manufacturer/vendor

## Security Considerations

N/A — replace with any privacy constraints, NDA notes, or access control requirements specific to your deployment.

## Implementation Checklist

N/A — link to your task tracker if applicable.

## Future Considerations

- Automate document sync / re-import pipeline (see [sync-workflow.md](../../sync-workflow.md))
- Expand to additional knowledge domains
- Add playbook examples for improved tool routing accuracy

## Full Specification

N/A — link to your detailed spec doc if applicable.
