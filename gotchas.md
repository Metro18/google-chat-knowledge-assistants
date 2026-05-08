# Gotchas and Known Issues

## GCS URL Format
Use `https://storage.cloud.google.com/[bucket]/path/file.pdf` — not `https://storage.googleapis.com/`. The authenticated URL requires users to be signed into their Google Workspace account but works seamlessly for Workspace organizations. The unauthenticated URL returns an AccessDenied error for private buckets.

## URL Encoding
Filenames with spaces or special characters must be percent-encoded in GCS URLs (spaces → `%20`, parentheses → `%28` / `%29`). Run `encode_gcs_url()` from `generate_index.py` to normalize URLs idempotently — decode fully first (loop until stable), then re-encode.

## index.txt Must Live Outside docs/
If `index.txt` is placed inside the `docs/` subfolder, Vertex AI will index it as a document and it will pollute RAG results with index metadata showing up in content answers. Keep it at `gs://[bucket]/[domain]/index.txt`.

## Avoid filter and userMetadata Parameters
Vertex AI Search will sometimes inject `filter` or `userMetadata` parameters into tool requests. This causes errors. Add `IMPORTANT: Do not use the filter or userMetadata parameters in the requestBody.` to every tool description.

## Don't Combine Docs and Index Into One Tool
A combined tool forces the summarizer to determine whether the user wants a content answer or a file listing. When both data stores return results, the bot hedges. Keep them separate — one tool for docs, one for index, with explicit routing in instructions.

## Session Isolation in Multi-User Spaces
The native Google Chat + Dialogflow CX integration may not scope sessions per user in all configurations. Whether all users in a shared Chat space see the same session context is TBD — behavior may vary by deployment setup. Worth testing in your environment before going to production with multi-user spaces.

## Google Chat Character Limit
Google Chat enforces a 4,096 character message limit. Responses that exceed this limit fail silently — the message is dropped with no error shown to the user. Target 3,800 characters maximum to maintain a safe margin. Index responses listing many files are especially vulnerable — cap at 8 results.

## Vertex AI Service Agent Provisioning
On first use of Vertex AI in a new project, service agents take several minutes to provision. API calls during this window return `FAILED_PRECONDITION`. Wait and retry.

## Gemini Model IDs
Use the full publisher path when referencing Gemini models via API: `publishers/google/models/gemini-2.5-flash`. Short IDs may return 404. `gcloud ai models list` shows only fine-tuned models — use the Python SDK `client.models.list()` for publisher models.

## Text Fragment Anchors in URLs
Vertex AI Search sometimes appends `#:~:text=something` to document URLs. These anchors don't work in all browsers and expose internal document structure. Strip everything from `#:~:text=` onward in your summarizer prompts and in the index generation script.

## Playbook Examples Are Powerful
Adding examples in the Default Generative Playbook → Examples tab significantly improves tool routing accuracy and prevents parameter injection errors. Use examples to show correct tool selection, response format, and what NOT to do.

---

## Next Steps

### Near-Term

- **Validate session isolation behavior** — Whether the native Google Chat + Dialogflow CX integration properly scopes sessions per user in multi-user spaces is TBD. Test in your environment. If session bleed is confirmed, a Cloud Function middleware routing messages using `message.sender.name` as the Dialogflow session ID is the fix — and also enables per-turn session parameter injection (e.g., current date/time).

- **Automated document sync pipeline** — Currently, documents are manually uploaded to GCS and re-imported into Vertex AI Search. A Cloud Function triggered by GCS object finalization events could automate re-import and index regeneration.

- **Index generation for additional domains** — The `generate_index.py` script currently handles one domain at a time. Extend to support batch generation across all domains.

### Medium-Term

- **CX Agent Studio migration** — Google has deprecated Dialogflow CX Playbooks in favor of CX Agent Studio (part of the Gemini Enterprise Agent Platform). Plan migration in the coming months. CX Agent Studio offers multi-model support (Gemini, Claude, open-source), better evaluation tooling, and a more robust agent runtime.

- **Response length optimization for index tools** — Current index responses cap at 8 results due to the 4,096 character limit. Options: remove description fields from listings (cut entry size in half), switch to Google Drive shortlinks (~60 chars) instead of GCS URLs (~100+ chars).

- **Document update notifications** — When source documents are updated in GCS, notify relevant users in Google Chat that the documentation has changed.

### Architectural

- **Multi-model routing** — With CX Agent Studio, route simpler queries to a faster/cheaper model (e.g., Gemini Flash) and complex multi-document synthesis to a more capable model (e.g., Gemini Pro or Claude).

- **Evaluation harness** — Build a set of canonical test queries with expected answers to regression-test prompt changes before deploying to production.
