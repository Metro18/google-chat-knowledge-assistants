# Architecture

## Overview

```
Google Chat → Dialogflow CX Agent → Vertex AI Search (RAG) → GCS Documents
```

Each user message travels from Google Chat into a Dialogflow CX generative agent (playbook). The playbook routes the query to the appropriate tool. Each tool contains a Vertex AI Search data store backed by documents in Google Cloud Storage. Vertex AI retrieves the most relevant document chunks, and a custom summarizer prompt synthesizes the final answer using Google Chat markup formatting.

## Components

| Component | Service | Purpose |
|-----------|---------|---------|
| Chat interface | Google Chat | User-facing messaging surface |
| Agent runtime | Dialogflow CX (generative playbook) | Orchestrates routing, tool calls, response |
| Query optimization | Dialogflow CX tool — query rewriter | Expands abbreviations, normalizes language |
| Document retrieval | Vertex AI Search (RAG) | Semantic search over document library |
| Response formatting | Dialogflow CX tool — response summarizer | Formats output, adds citations, enforces Chat markup |
| Document storage | Google Cloud Storage | Stores PDFs, DOCX, and other source files |
| File index | Vertex AI Search (text index) | Structured index for file discovery queries |

## Tool Design Pattern — Two Tools Per Domain

Each knowledge domain uses **two separate tools**:

| Tool Type | Purpose | When to Route Here |
|-----------|---------|-------------------|
| **DOCS tool** | RAG search over full document content | "What is the policy on X?" / "How do I configure Y?" |
| **INDEX tool** | Search a structured text index for file listings | "List all docs for X" / "Send me the Y manual" |

**Why separate tools?** Combining docs and index into one tool forces the summarizer to guess whether the user wants a content answer or a file listing. When both data stores return results, the bot hedges and often returns mixed responses. Separate tools keep routing deterministic and each summarizer has a single responsibility.

A general-purpose bot covering multiple topic areas (e.g., HR policies + equipment specs) will have two tools per domain:
```
HR-DOCS, HR-INDEX, SPECS-DOCS, SPECS-INDEX
```

A single-domain technical bot needs only one pair:
```
TECHNICAL-DOCS, TECHNICAL-INDEX
```

## Prompt Architecture

Prompts live at two levels in Dialogflow CX:

**Playbook level (1 set per agent):**
- **Goal** — one paragraph describing the agent's identity and purpose
- **Instructions** — behavioral rules, response formatting, tool routing table, language handling

**Tool level (3 files per tool):**
- **Description** — tells the agent what this tool searches and when to use it
- **Query Rewriter** — optimizes the user's query for better RAG retrieval
- **Response Summarizer** — formats the retrieved content into the final answer

> **Important:** Prompts belong to the tool, not to individual data stores. One tool = exactly 3 prompt files, regardless of how many data stores are inside it.

## GCS Bucket Layout

```
gs://[your-bucket]/
  [domain]/
    index.txt           ← file metadata index (MUST be outside docs/)
    docs/
      [category]/       ← your documents organized by category or vendor
```

The `index.txt` must live outside the `docs/` subfolder. If it sits inside `docs/`, Vertex AI will index it as a document and it will pollute RAG results.

## Index File Format

The `index.txt` is a plain-text structured file with one entry per document:

```
Document: Fleet Vehicle Policy.pdf
Folder: Fleet
Description: Policy covering vehicle use, fuel card procedures, and accident reporting for company fleet drivers.
URL: https://storage.cloud.google.com/[your-bucket]/[domain]/docs/Fleet/Fleet%20Vehicle%20Policy.pdf
Drive File ID:
---
```

GCS URLs must use `https://storage.cloud.google.com/` (authenticated, browser-friendly) rather than `https://storage.googleapis.com/` (unauthenticated). Users must be signed into their Google Workspace account to open authenticated links.

Filenames with spaces or special characters must be percent-encoded in the URL (spaces → `%20`). The `generate_index.py` script in this repo handles this automatically.
