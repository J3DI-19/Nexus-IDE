# Nexus IDE

Nexus IDE is a local-first AI-assisted development environment that enables controlled, transparent, and safe code modification using structured prompts and validated diff patches.

It acts as a bridge between your codebase and AI tools—giving you full control over what changes are made and how they are applied.

---

## 🚀 Overview

Nexus IDE runs directly inside your project.

It provides a lightweight IDE-like interface combined with a safe AI workflow:

* Scan and explore your project
* Open and view files with syntax highlighting
* Generate structured prompts for AI tools
* Apply code changes safely via diff patches

Everything runs locally — no external APIs required.

---

## 🧩 Core Features

### 🗂 Project Explorer

* Automatically scans the current project directory
* Displays a structured file tree (like VS Code)
* Expand/collapse folders
* Select files to open in editor

---

### 📝 Code Editor (Monaco)

* Powered by Monaco (VS Code engine)
* Syntax highlighting based on file type
* Multi-tab support
* Read-only safe viewing mode
* Built-in minimap and editor features

---

### 🧠 AI Actions Panel

* Dedicated right-side control panel
* Generate structured prompts (UI ready)
* Patch application flow (UI scaffold ready)
* Active file context display

---

### 🔍 In-Editor Search

* Search directly inside open file
* Next / previous match navigation
* Replace mode (via Monaco integration)

---

### 📄 Secure File Access

* Reads files directly from project
* Prevents unsafe paths
* Encodes paths safely for backend requests

---

### 🧠 Structured Prompt Generation

* Backend-driven prompt generation system
* Uses external templates
* Includes:

  * File content
  * Project structure
  * Context-aware formatting

---

### 🔒 Safe Patch Execution Engine

* Applies unified diff patches with:

  * Dry-run validation
  * Path safety checks
  * Patch verification
  * Timeout protection
  * Git fallback

---

### ⚡ Fast Project Scanning

* Optimized using `os.scandir`
* Skips unnecessary files and directories

---

## 🏗️ Architecture

### Backend (FastAPI)

* `/scan` → Scan project files
* `/file` → Retrieve file content
* `/prompt` → Generate structured AI prompts
* `/apply` → Apply validated diff patches

---

### Frontend (React + Vite)

* Explorer panel (file tree)
* Editor panel (Monaco)
* Right panel (AI + context)
* Header (search + controls)

---

## ⚙️ Setup

### Backend

```bash
cd backend
pip install fastapi uvicorn
python main.py
```

Server runs at:
[http://localhost:5000](http://localhost:5000)

---

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App runs at:
[http://localhost:5173](http://localhost:5173)

---

## 🧪 Usage Workflow

1. Run Nexus IDE inside your project
2. Open frontend UI
3. Browse files in Explorer
4. Open file in editor
5. Generate prompt (next step)
6. Send prompt to AI
7. Paste diff patch
8. Apply safely

---

## ⚠️ Requirements

* Python 3.8+
* Node.js 18+
* `patch` utility OR Git Bash / WSL (Windows)

---

## 🔐 Design Principles

* Local-first (no external APIs)
* Safety over automation
* Transparent modifications
* Modular architecture
* AI-assisted, not AI-controlled

---

## 📌 Current Status

### ✅ Completed

#### Backend

* Modular FastAPI backend
* Fast project scanner
* Secure file endpoint
* Prompt generation system
* External prompt templates
* Safe diff patch engine
* Path validation & protection
* Dry-run patch validation
* Git fallback support
* Timeout handling

#### Frontend (Major Progress)

* Full 3-panel IDE layout
* File explorer (tree-based)
* Monaco editor integration
* Multi-tab system
* File loading from backend
* In-editor search (Monaco-powered)
* Right-side AI panel UI
* Panel toggle system
* Clean responsive layout
* Consistent dark theme design

---

### 🔄 In Progress

* Generate Prompt → backend connection
* Patch input + apply workflow
* Prompt display UI
* Execution logs / output viewer

---

### 🚀 Planned Features

#### Code Intelligence

* Language-aware parsing (Python, JS/TS, Java, C++)
* Function/class/import extraction
* Cross-file linking

#### Editing & Navigation

* Global search (project-wide)
* Symbol navigation
* Clickable imports

#### Execution Engine

* Detect project type
* Run builds/tests locally
* Capture structured errors

#### Patch System

* Patch preview before apply
* Undo / rollback
* Multi-file patch viewer

#### AI Workflow

* Iterative loop system
* Context-aware prompts
* Smart prompt tuning

---

## 🧭 Vision

Nexus IDE aims to become a fully local AI-assisted development environment where:

* Developers stay in control
* AI assists, not replaces
* Code changes are safe and reviewable
* Everything remains private and local

---

## 🛠️ Tech Stack

* Backend: FastAPI (Python)
* Frontend: React + Vite (TypeScript)
* Editor: Monaco
* Execution: Local tools (`patch`, `git`, subprocess)

---

## 📍 Status

Actively evolving from a backend engine into a full local AI-powered IDE.
