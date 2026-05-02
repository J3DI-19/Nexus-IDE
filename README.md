# LoopForge

LoopForge is a local AI-powered code modification engine that generates and safely applies code changes using structured prompts and unified diff patches.

## 🚀 Features

* ⚡ Fast project scanning (os.scandir)
* 🧠 Structured AI prompt generation
* 🧩 Modular prompt template system
* 🔒 Safe patch application engine
* 🛡️ Path traversal protection
* 🔁 Dry-run validation before applying changes

## 🏗️ Architecture

LoopForge consists of four core endpoints:

* `/scan` → scans project files
* `/file` → retrieves file content
* `/prompt` → generates structured AI prompts
* `/apply` → safely applies diff patches

## ⚙️ Setup

```bash
pip install fastapi uvicorn
python backend.py
```

Server runs on:
http://localhost:5000

## 🧪 Usage

1. Scan project
2. Select file
3. Generate prompt
4. Send prompt to AI
5. Apply returned diff

## ⚠️ Requirements

* Python 3.8+
* `patch` utility (Linux/macOS) OR Git Bash / WSL on Windows

## 🧠 Notes

* Fully local — no API required
* Prompt template is external and editable
* Designed for iterative AI-assisted development

## 📌 Status

Core backend is complete. Frontend and workflow improvements are in progress.

# LoopForge Progress

## ✅ Completed

* [x] Fast file scanner (os.scandir)
* [x] Secure file access endpoint
* [x] Modular prompt generation system
* [x] External prompt template
* [x] Structured AI prompt format
* [x] Safe diff execution engine (/apply)
* [x] Path validation & traversal protection
* [x] Dry-run patch validation
* [x] Git fallback support
* [x] Timeout protection

## 🔄 In Progress / Next

* [ ] Frontend integration polish
* [ ] Prompt preview UI
* [ ] Apply patch button wiring
* [ ] Console/log viewer UI

## 🚀 Future Improvements

* [ ] Undo / rollback system
* [ ] Patch preview before apply
* [ ] Multi-file context intelligence
* [ ] Error-aware prompting
* [ ] Auto-loop execution (agent-like behavior)
* [ ] Project-specific prompt tuning

