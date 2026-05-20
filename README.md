# NEXUS IDE v1.0

NEXUS IDE is an open-source, local-first IDE focused on two core capabilities:

- **Prompt Engine**: deterministic context retrieval + structured prompt assembly for external LLMs.
- **Executor**: safe execution workflow with preview, local version history, restore, and undo.

Licensed under the [MIT License](./LICENSE).

## Why NEXUS IDE

Most AI coding tools optimize for autonomous behavior. NEXUS IDE optimizes for:

- deterministic and inspectable context
- explicit safety checks before mutation
- developer-controlled workflows
- local operation without GitHub/remote dependency

## Core Capabilities

### Prompt Engine

- Deterministic Context Engine (indexing, retrieval, extraction, prompt assembly)
- Runtime and impact intelligence fed into context ranking
- Structured engineering prompt generation with selected code slices

### Executor

- Executor popup workflow with:
  - file/project history timelines
  - commit preview
  - restore preview + conflict detection
  - guarded force restore
  - undo
- Local-only Git-backed versioning with auto-init for non-git projects
- Standardized API envelope for execution flows (`status`, `code`, `message`, `details`, `request_id`)
- Default patch contract: `nexus_edits_v2` (unified diff available as fallback mode)

## High-Level Flow

```text
Project Scan
-> Metadata Indexing
-> Symbol Graph Construction
-> Runtime/Impact Intelligence
-> Context Retrieval
-> Prompt Assembly
-> Executor Preview/Apply/Restore/Undo
```

## Tech Stack

### Backend

- FastAPI
- Python
- Modular context engine + runtime analyzers

### Frontend

- React
- TypeScript
- Vite
- Monaco Editor

## Setup

### Backend

```bash
cd backend
pip install -r ../requirements.txt
python main.py
```

Backend URL:

```text
http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

## Release Validation

### Frontend

```bash
cd frontend
npm run test
npm run build
```

### Backend (Python 3.10+ required)

```bash
python -m pytest -q backend/tests/test_history_api.py backend/tests/test_version_service.py
```

## Executor Safety Model

- Preview before restore/apply
- Deterministic patch pipeline: `parse -> normalize -> validate -> simulate -> intent_guard -> apply -> verify -> snapshot`
- Apply is blocked by blockers only (warnings are non-blocking)
- Intent assertions merged from task-derived + model-provided + user-provided checks
- Conflict detection (`dirty_buffer`, `workspace_diverged`, `commit_not_found`, `missing_path`, `path_type_mismatch`, `restore_scope_mismatch`)
- Explicit force-restore acknowledgement
- Post-action reload prompt for editor-buffer sync
- Post-apply verification with automatic rollback on semantic mismatch

## `nexus_edits_v2` Contract

Canonical shape:

```json
{
  "format": "nexus_edits_v2",
  "assert_contains": ["optional"],
  "assert_not_contains": ["optional"],
  "edits": [
    {
      "path": "relative/path",
      "op": "replace_range|insert_after|insert_before|create_file|delete_file"
    }
  ]
}
```

Operation fields:

- `replace_range`: `old_text`, `new_text`
- `insert_after` / `insert_before`: `anchor_text`, `new_text`
- `create_file`: `new_text`
- `delete_file`: no extra fields
