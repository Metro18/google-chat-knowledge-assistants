# Sync Workflow: Google Drive to AI Data Sources

## Overview

Automated pipeline that keeps AI assistant data sources in sync with source documents managed in Google Drive. Changes flow through a four-stage pipeline:

```
Google Drive (source of truth)
  |  file added / modified / deleted
  v
GCS Bucket (docs/ folders)
  |  object finalized / deleted
  v
Vertex AI Data Source - docs (RAG)        generate_index.py
  |  import complete                        |  rebuild index.txt
  v                                         v
Vertex AI Data Source - index
```

## Current State

| Component | Status |
|-----------|--------|
| Google Drive folders | TBD — need to identify/create source folders |
| GCS buckets | In place (see below) |
| Vertex AI data stores (docs) | In place, manual re-import |
| Index generation script | In place (`shared/scripts/generate_index.py`) |
| Vertex AI data stores (index) | In place, manual re-import |
| Automation | None — all steps are manual |

## Infrastructure

### General Bot (HR & Operations)

| Stage | Resource |
|-------|----------|
| GCP Project | `[general-bot-gcp-project]` |
| GCS Bucket | `gs://[general-bot-bucket]/` |
| Category: HR | Drive folder TBD → `hr-operations/docs/` |
| Category: Spec Sheets | Drive folder TBD → `spec-sheets/docs/` |

### Technical Bot (Technical Documentation)

| Stage | Resource |
|-------|----------|
| GCP Project | `[technical-bot-gcp-project]` |
| GCS Bucket | `gs://[technical-bot-bucket]/` |
| Category: SOPs | Drive folder TBD → `sops/docs/` |
| Category: Vendors | Drive folder TBD → `vendors/docs/` |

## Pipeline Stages

### Stage 1: Google Drive → GCS Bucket

Source documents are managed in Google Drive shared folders. When files are added, modified, or deleted, they need to sync to the corresponding GCS bucket path.

**Drive folder → GCS path mapping (to be defined):**

| Drive Folder | GCS Destination |
|-------------|-----------------|
| TBD | `gs://[general-bot-bucket]/hr-operations/docs/` |
| TBD | `gs://[general-bot-bucket]/spec-sheets/docs/` |
| TBD | `gs://[technical-bot-bucket]/sops/docs/` |
| TBD | `gs://[technical-bot-bucket]/vendors/docs/` |

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| **Drive push notifications** (Drive API `changes.watch()` → Cloud Function) | Real-time, precise control over folder-to-bucket mapping | Requires webhook endpoint, renewal every 24h |
| **Storage Transfer Service** | Native GCP, no custom code | Scheduled only (not event-driven), folder-level granularity |
| **Make scenario** | Visual workflow, no-code orchestration | External dependency, per-operation cost |
| **Apps Script trigger** | Simple setup, no infra | Less robust, limited error handling |

**Considerations:**
- Subfolder structure in Drive should mirror GCS (e.g., `Spec Sheets/[Vendor]/` → `spec-sheets/docs/[Vendor]/`)
- File deletions in Drive should remove from GCS
- Need to handle filename conflicts and special characters

### Stage 2: GCS Bucket → Vertex AI Data Source (docs)

When files land in or are removed from a `docs/` folder, the corresponding Vertex AI Search data store needs to re-import.

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| **Eventarc + Cloud Function** (GCS `finalize`/`delete` events) | Real-time, native GCP | Need debouncing — multiple file changes shouldn't trigger multiple imports |
| **Cloud Scheduler** (periodic re-import) | Simple, predictable | Not real-time, unnecessary imports when nothing changed |
| **Chained from Stage 1** | Single orchestration | Tighter coupling between stages |

**Considerations:**
- Vertex AI data store re-import can take minutes
- Debounce: buffer events (e.g., wait 5 minutes after last change, then import once)
- Vertex AI Search unstructured data stores currently require manual/API-triggered re-import (no native auto-sync)

### Stage 3: Docs Import Complete → Regenerate Index

After the docs data store finishes importing, run `generate_index.py` to update `index.txt` with descriptions for any new/changed files.

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| **Cloud Run job** (triggered after import) | Scalable, same script | Needs containerization |
| **Cloud Function** (chained from Stage 2) | Serverless, auto-triggered | 9-min timeout may be tight for large categories |
| **Cloud Workflows** (orchestrate stages 2-4) | Visual, built-in retry/polling | Another GCP service to manage |

**Considerations:**
- `generate_index.py` resume logic means only new/changed files get Gemini calls
- Large categories (1,000+ files) full rebuild takes ~10 minutes — incremental is fast
- Script needs GCS access + Gemini API (Vertex AI) access
- Currently uses `--project` flag for Gemini API quota project

### Stage 4: Index Updated → Vertex AI Data Source (index)

When `index.txt` is written to GCS, the index data store needs to re-import.

**Trigger:** GCS `finalize` event on `{category}/index.txt`
**Action:** Call Vertex AI Search API to re-import the index data store

This is the simplest stage — single file, predictable trigger.

## Design Questions

- [ ] **Latency tolerance:** Near-real-time (minutes) or daily batch?
- [ ] **Drive folder structure:** Do source folders already exist? What's the current folder layout?
- [ ] **Orchestration platform:** GCP-native (Cloud Functions + Eventarc + Cloud Workflows) vs. Make?
- [ ] **Cross-project:** General Bot and Technical Bot are in different GCP projects — shared orchestration or separate?
- [ ] **Deletion handling:** When a file is removed from Drive, remove from GCS + remove index entry + re-import both data stores?
- [ ] **Notifications:** Should someone be notified on sync failures?
- [ ] **Permissions:** Which service account(s) need access to Drive, GCS, and Vertex AI?

## Future Considerations

- Monitoring dashboard for sync status and failures
- Manual trigger for full re-sync (all files, all categories)
- Support for additional bots/categories without code changes
- Versioning or audit trail of document changes
