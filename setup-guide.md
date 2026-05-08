# Setup Guide

> **Prerequisites:** You'll need a Google Cloud account, the `gcloud` CLI (see [README.md](README.md#prerequisites) for installation), and Python 3.9+ for the index generation script.

## Step 1: GCP Project Setup

1. Create a GCP project (or use an existing one)
2. Enable APIs: **Dialogflow CX**, **Vertex AI**, **Cloud Storage**, **Google Chat API**
3. Each Google Chat bot identity requires a separate GCP project — you cannot run two independent Chat bots from the same project

## Step 2: Document Storage

1. Create a GCS bucket in your project
2. Create domain subfolders following the layout in [architecture.md](architecture.md) (e.g., `hr-operations/docs/`, `spec-sheets/docs/`)
3. Upload your documents into the appropriate category subfolders
4. Name files clearly — filenames appear in index results and citations

## Step 3: Generate the Index File

Use `shared/scripts/generate_index.py` (in this repo) to scan a GCS category folder, generate a one-sentence Gemini description per document, and write `index.txt`.

```bash
python shared/scripts/generate_index.py \
  --bucket [your-bucket] \
  --category [domain-folder] \
  --project [your-gcp-project]
```

Upload the resulting `index.txt` to `gs://[your-bucket]/[domain]/index.txt` (outside `docs/`).

Re-run and re-upload whenever documents are added, removed, or renamed.

## Step 4: Create Vertex AI Search Data Stores

For each tool you need two data stores:

**Docs data store (RAG):**
1. Go to Vertex AI → Agent Builder → Data Stores
2. Create → Cloud Storage → Unstructured documents
3. Point to `gs://[your-bucket]/[domain]/docs/`
4. Enable **Layout Parser** for PDFs
5. Set chunking: Layout-based, 500 tokens, include ancestor headings
6. Sync type: One-time (re-import manually when documents change)

**Index data store:**
1. Create another data store → Cloud Storage → Unstructured documents
2. Point to `gs://[your-bucket]/[domain]/index.txt` (the single file, not a folder)
3. No layout parser needed — it's plain text
4. Sync type: One-time

## Step 5: Create the Dialogflow CX Agent

1. Go to Dialogflow CX → Create Agent
2. Select region (recommend `us-central1`)
3. Select model (recommend `gemini-2.5-flash` for a good cost/quality balance)
4. Under **Generative Features**, enable **Playbooks**

## Step 6: Configure the Playbook

1. Navigate to the **Default Generative Playbook**
2. Paste your **Goal** prompt (see [prompt-templates.md](prompt-templates.md))
3. Paste your **Instructions** prompt (see [prompt-templates.md](prompt-templates.md))
4. Optionally add **Examples** in the Examples tab — these are powerful for teaching tool routing and preventing parameter injection errors

## Step 7: Create Tools

For each tool (DOCS and INDEX per domain):

1. Playbook → Tools → Create Tool
2. Name: `[DOMAIN]-DOCS` or `[DOMAIN]-INDEX` (use ALL-CAPS-DASHED format)
3. Type: **Data Store**
4. Add the appropriate Vertex AI Search data store
5. Paste the **Tool Description** prompt
6. Under **Custom query rewriter**, paste the **Query Rewriter** prompt
7. Under **Custom response**, paste the **Response Summarizer** prompt

> Tool names must be valid Python identifiers if you plan to use code blocks. Use underscores or hyphens — avoid spaces.

## Step 8: Wire Tools in Instructions

In the Instructions prompt, include a routing table that maps query types to tool names using the `${TOOL:TOOL-NAME}` reference syntax (or plain names — the playbook understands both).

## Step 9: Connect to Google Chat

1. Go to **Google Cloud Console → APIs & Services → Google Chat API**
2. Configure the app: name, avatar, description
3. Under **Connection settings**, select **Dialogflow** and point to your agent
4. Under **Slash commands** and **Bot works in**: configure as needed
5. Add the bot to a Google Chat space to test

> **Session isolation gotcha:** The native Google Chat + Dialogflow CX integration may share a single session ID across all users in a space — meaning every user in a shared Chat space could see the same conversation context. This behavior may vary by deployment configuration. Test in your environment before going to production with multi-user spaces. If session bleed is confirmed, the fix is a Cloud Function middleware that uses `message.sender.name` as the Dialogflow session ID.

## Step 10: Test

Use the Dialogflow CX simulator to test queries before going live:
- Content questions → confirm the DOCS tool fires and returns cited answers
- File listing questions → confirm the INDEX tool fires and returns links
- Multilingual queries → confirm language detection works
- Negative cases → confirm graceful "not found" responses
