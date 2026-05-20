# NEXUS IDE

NEXUS IDE is an open-source, local-first IDE built for deterministic AI-assisted development.

It focuses on two core systems:

- **Prompt Engine**: deterministic context retrieval and structured prompt assembly.
- **Executor**: guarded code execution with preview, restore, undo, and local history.

License: [MIT](./LICENSE)

## Why NEXUS IDE

NEXUS IDE is designed for developers who want control, traceability, and safety in AI workflows.

- Deterministic and inspectable context selection
- Explicit safety checks before applying changes
- Local-first operation without requiring cloud repository integration
- Versioned execution flow with rollback support

## Architecture

### Prompt Engine

- Project scan and metadata indexing
- Symbol-aware retrieval and ranking
- Runtime and impact signals for context quality
- Structured engineering prompt generation

### Executor

- Preview-before-apply workflow
- Restore and undo with conflict detection
- Local Git-backed snapshot history
- Standardized execution response envelope

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

- Backend: FastAPI, Python
- Frontend: React, TypeScript, Vite, Monaco Editor

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+ and npm

### 1) Start Backend

```bash
cd backend
pip install -r ../requirements.txt
python main.py
```

Backend runs at `http://localhost:8000`.

### 2) Start Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

## Repository Notes

- Large local runtime bundles and temporary artifacts are intentionally excluded from version control.
- If you need optional local runtimes, generate or install them in your own environment.

## `nexus_edits_v2` Patch Contract

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

Operation-specific fields:

- `replace_range`: `old_text`, `new_text`
- `insert_after` / `insert_before`: `anchor_text`, `new_text`
- `create_file`: `new_text`
- `delete_file`: no extra fields
