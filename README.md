# Nexus IDE

Nexus IDE is a local-first deterministic engineering intelligence platform designed to bridge modern codebases with external LLMs through structured context engineering.

Unlike autonomous AI agents, Nexus focuses on:

* deterministic retrieval
* inspectable reasoning
* runtime-aware context generation
* structured engineering briefings
* safe developer-controlled workflows

Nexus does not attempt to replace developers.
It acts as a high-signal context engine that prepares elite prompts and engineering context for external AI systems.

---

# 🚀 Vision

Nexus IDE aims to become a professional local-first engineering workspace where:

* developers stay fully in control
* AI assists instead of autonomously acting
* context retrieval is explainable and inspectable
* prompts are architecture-aware
* execution workflows remain safe and reviewable
* everything runs locally

The long-term goal:

```text
Open Project
→ Nexus understands architecture/runtime/context
→ Nexus assembles engineering briefings
→ External LLM produces high-quality output
→ Nexus safely reviews/applies execution changes
```

---

# 🧠 Core Philosophy

Nexus is:

* deterministic
* local-first
* modular
* inspectable
* developer-controlled
* ecosystem-aware

Nexus is NOT:

* an autonomous AI agent
* an opaque vector-database system
* a cloud-dependent coding assistant
* a black-box prompt generator

---

# 🏗️ Major Architecture Evolution

Nexus has evolved from:

```text
Open file → Generate prompt
```

Into:

```text
Project Scan
→ Metadata Indexing
→ Symbol Graph Construction
→ Runtime/Impact Intelligence
→ Context Retrieval
→ Structured Prompt Assembly
```

---

# ⚡ Current Capabilities

## 🗂️ Workspace & Project Intelligence

* Dynamic project root switching
* High-speed recursive scanning
* Incremental indexing via SHA-256 hashing
* Framework detection
* Runtime-aware project analysis
* Workspace-wide symbol search
* Multi-language project understanding

---

## 🧠 Nexus Context Engine

The backend now contains a fully modular Context Engine:

```text
backend/context_engine/
```

Core systems include:

* indexing
* traversal
* retrieval
* extraction
* prompt assembly
* runtime diagnostics
* impact analysis
* framework intelligence
* language adapters

---

# 🔍 Deterministic Retrieval Engine

Nexus retrieves context using deterministic scoring instead of embeddings.

Retrieval signals include:

* dependency traversal
* call chains
* inheritance relationships
* runtime stack traces
* framework artifacts
* directory proximity
* symbol similarity
* execution paths
* config relationships

Every retrieved candidate includes:

* score breakdowns
* reasoning
* relationship paths
* framework/runtime relevance

---

# 🧩 Multi-Language Intelligence

## Deep Language Support

### Python

* AST parsing
* classes/functions
* imports
* inheritance
* call chains
* FastAPI route intelligence
* runtime diagnostics

### TypeScript / JavaScript

* imports/exports
* React components/hooks
* symbol extraction
* execution relationships
* runtime-aware retrieval

### Java

* classes/interfaces
* annotations
* inheritance
* method traversal
* runtime mapping

### Kotlin

* data classes
* coroutines
* Compose detection
* inheritance
* runtime integration

### C#

* namespaces
* async methods
* delegates/events
* inheritance
* .NET runtime parsing

### C++

* namespaces
* templates/macros
* include relationships
* header/source linking
* compiler/runtime diagnostics

---

# 🏛️ Structural + Config Intelligence

Nexus now deeply understands project structure.

## Supported Structural Systems

### HTML/CSS

* DOM hierarchy
* class/id extraction
* style relationships
* linked scripts/styles

### XML

* Android layouts
* Manifest parsing
* navigation relationships
* resource IDs
* Activity/Fragment linking

### Config Systems

* package.json
* tsconfig
* vite config
* pyproject.toml
* Gradle configs
* docker-compose
* YAML/TOML/JSON parsing

---

# ⚠️ Runtime + Execution Intelligence

Nexus includes deterministic runtime diagnostics.

Supported:

* Python exceptions
* Node.js stack traces
* React/Vite runtime errors
* TypeScript compiler errors
* pytest failures
* Gradle failures
* Java/Kotlin stack traces
* C# runtime traces
* GCC/MSVC diagnostics

Runtime intelligence integrates directly into:

* retrieval scoring
* extraction prioritization
* impact analysis
* prompt generation

---

# 🌐 Framework Intelligence

## Current Framework Support

### FastAPI

* route extraction
* decorator parsing
* endpoint relationships
* runtime route impact analysis

### React

* component detection
* hook relationships
* runtime-aware component traversal

### Vite / Node.js

* project classification
* build/runtime awareness
* dependency extraction

---

# 🔄 Impact Analysis Engine

Nexus performs deterministic downstream dependency analysis.

It can answer:

* What breaks if this changes?
* Which APIs depend on this symbol?
* Which components are affected?
* Which runtime paths are impacted?

Impact traversal includes:

* imports
* calls
* inheritance
* framework artifacts
* runtime execution paths
* structural/config relationships

---

# ✂️ Smart Context Extraction

Nexus does not dump entire files.

Instead it performs:

* symbol-boundary extraction
* runtime-aware slicing
* execution-aware extraction
* XML/layout slicing
* framework artifact extraction
* dependency-focused context selection

This drastically improves signal-to-noise ratio in prompts.

---

# 🧠 Structured Engineering Briefings

Generated prompts now behave like:

```text
Senior engineer handoff documents
```

Prompt sections may include:

* runtime diagnostics
* execution chains
* architectural dependencies
* framework artifacts
* impact warnings
* selected context
* code slices
* retrieval reasoning

Prompt modes include:

* Feature Implementation
* Bugfix / Debugging
* Refactoring
* Architecture Analysis

---

# 🖥️ Frontend Features

## IDE Layout

* Explorer sidebar
* Monaco editor
* Progressive right-side intelligence workflow
* Workspace-wide search
* Runtime diagnostics UI
* Context review modals
* Prompt preview modals

---

## Workspace Search

The global search bar now acts as:

```text
Workspace / Symbol Search
```

Used for:

* files
* symbols
* classes
* functions
* project-wide lookup

Monaco search remains editor-local.

---

## Right Panel Workflow

The Nexus Intelligence Panel now follows a progressive workflow:

```text
Initialize Index
→ View Active Context
→ Enter Goal
→ Retrieve Context
→ Review Runtime/Impact
→ Assemble Engineering Briefing
```

Heavy sections open as overlays/modals to reduce clutter and maintain IDE-like focus.

---

# 🛡️ Safety Principles

Nexus prioritizes:

* transparent retrieval
* explainable scoring
* safe execution
* reviewable modifications
* deterministic behavior

The system intentionally avoids:

* autonomous AI agents
* opaque embeddings/vector DBs
* uncontrolled execution
* hidden prompt manipulation

---

# ⚙️ Tech Stack

## Backend

* FastAPI
* Python
* Modular Context Engine
* AST/heuristic parsers
* Runtime analyzers

## Frontend

* React
* TypeScript
* Vite
* Monaco Editor

---

# ⚙️ Setup

## Backend

```bash
cd backend
pip install fastapi uvicorn
python main.py
```

Runs on:

```text
http://localhost:8000
```

---

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs on:

```text
http://localhost:5173
```

---

# 🧪 Current Development Focus

## Immediate Priorities

### Stability & Prompt Quality

* retrieval tuning
* extraction refinement
* prompt compression
* real-project testing
* frontend stabilization

### Safe Execution Layer

Planned workflow:

```text
AI Response
→ Patch Review
→ Manual Approval
→ Validation
→ Safe Apply
```

### Ecosystem Expansion

Upcoming ecosystem intelligence:

* Android ecosystem intelligence
* advanced web ecosystem intelligence
* Unity ecosystem intelligence
* Unreal/C++ ecosystem support

---

# 📍 Current Status

Nexus IDE has evolved from:

```text
basic AI-assisted editor
```

into:

```text
a deterministic engineering intelligence platform
```

The project is currently transitioning from:

* architecture expansion

into:

* refinement
* stabilization
* ecosystem specialization
* execution workflows
