import os
import re
import tempfile
import subprocess
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from pydantic import BaseModel

app = FastAPI(title="LoopForge Backend")

class PromptRequest(BaseModel):
    file: str
    goal: str

class PatchRequest(BaseModel):
    patch: str

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration: Project root directory
PROJECT_ROOT = Path(__file__).parent.parent / "workspace"
PROJECT_ROOT = PROJECT_ROOT.resolve()
PROJECT_ROOT.mkdir(exist_ok=True)

# Optimization: Skip these directories entirely during scan
IGNORED_DIRS = {"node_modules", ".git", "__pycache__", ".vscode", ".idea", "dist", "build"}
# Optimization: Skip these common binary/large file types
IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".zip", ".tar", ".gz",
    ".exe", ".bin", ".pyc", ".o", ".obj", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf"
}

# --- Prompt Templates and Builders ---

# Robustness: Use relative path based on backend file
TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "PromptTemplateV1.txt"

def load_prompt_template() -> str:
    """Reads the prompt template from disk with robust error handling."""
    try:
        return TEMPLATE_PATH.read_text(encoding="utf-8")
    except Exception:
        raise HTTPException(
            status_code=500, 
            detail="Prompt template could not be loaded."
        )

def detect_language(file_path: str) -> str:
    """Maps file extensions to markdown language tags."""
    ext = os.path.splitext(file_path)[1].lower()
    mapping = {
        ".js": "javascript",
        ".ts": "typescript",
        ".py": "python",
        ".css": "css",
        ".html": "html",
        ".json": "json"
    }
    return mapping.get(ext, "")

def build_project_context(file_path: str, all_files: list) -> str:
    """Builds a prioritized numbered list of relevant project files."""
    current_dir = os.path.dirname(file_path)
    nearby = [f for f in all_files if os.path.dirname(f) == current_dir and f != file_path][:5]
    others = [f for f in all_files if f != file_path and f not in nearby][:4]
    
    context = [f"1. {file_path} (current file)"]
    context += [f"{i+2}. {f} (same module)" for i, f in enumerate(nearby)]
    start_idx = len(nearby) + 2
    context += [f"{i+start_idx}. {f} (general context)" for i, f in enumerate(others)]
    
    return "\n".join(context)

def build_structure_section(content: str) -> str:
    """Extracts and formats imports, classes, and functions with hyphen markers."""
    lines = content.splitlines()
    imports = []
    classes = []
    functions = []
    
    for line in lines:
        trimmed = line.strip()
        if trimmed.startswith(("import ", "from ", "require(")):
            imports.append(f"- {trimmed}")
        elif trimmed.startswith("class "):
            classes.append(f"- {trimmed.split('{')[0].strip()}")
        elif trimmed.startswith(("function ", "def ")):
            functions.append(f"- {trimmed.split('{')[0].strip()}")
            
    result = []
    if imports:
        result.append("Imports:\n" + "\n".join(imports) + "\n(These imports may affect the logic of this file.)")
    if classes:
        result.append("Classes:\n" + "\n".join(classes))
    if functions:
        result.append("Functions:\n" + "\n".join(functions))
        
    return "\n\n".join(result) if result else "No significant structure detected."

def format_code_block(content: str, language: str) -> str:
    """Formats file content into a markdown code block with truncation and safety escaping."""
    # Safety: Strip trailing whitespace and handle curly braces for .format() safety
    # Note: Escaping curly braces is done at the final step before .format() call
    # but we prepare the content here.
    lines = content.splitlines()
    truncated_content = "\n".join(lines[:300]).strip()
    if len(lines) > 300:
        truncated_content += "\n... (truncated)"
        
    return truncated_content

# --- End Builders ---

def is_safe_path(path: Path) -> Path:
    """
    Resolves the path and verifies it is safely inside PROJECT_ROOT.
    Returns the resolved path if safe, otherwise raises an HTTPException.
    """
    try:
        resolved_path = path.resolve()
        if PROJECT_ROOT in resolved_path.parents or resolved_path == PROJECT_ROOT:
            return resolved_path
    except Exception:
        pass
    
    raise HTTPException(status_code=403, detail="Access denied: Path is outside project root.")

def fast_recursive_scan(root_path: str):
    """
    High-performance directory traversal using os.scandir.
    Prunes ignored directories early to avoid unnecessary disk I/O.
    """
    file_list = []
    
    def _scan(current_dir):
        try:
            with os.scandir(current_dir) as entries:
                for entry in entries:
                    if entry.name.startswith(".") or entry.name in IGNORED_DIRS:
                        continue
                    
                    if entry.is_dir(follow_symlinks=False):
                        _scan(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext not in IGNORED_EXTENSIONS:
                            rel_path = os.path.relpath(entry.path, root_path)
                            file_list.append(rel_path.replace("\\", "/"))
        except (PermissionError, OSError):
            pass

    _scan(root_path)
    return sorted(file_list)

@app.get("/scan")
async def scan_project():
    """Returns a list of all relevant files in the project."""
    try:
        files = fast_recursive_scan(str(PROJECT_ROOT))
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")

@app.get("/file")
async def get_file_content(path: str = Query(..., description="Relative path to file")):
    """Returns the content of a file with robust reading and security checks."""
    # Input validation: Reject empty or whitespace-only paths
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="Invalid path: Path cannot be empty.")

    try:
        # Pass unresolved path and resolve ONCE inside is_safe_path
        resolved_path = is_safe_path(PROJECT_ROOT / path)
        
        if not resolved_path.is_file():
            raise HTTPException(status_code=404, detail="File not found or is a directory.")

        # Robustness: Use errors="ignore" for cleaner source file viewing
        with open(resolved_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        return PlainTextResponse(content)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Read failed: {str(e)}")

@app.post("/prompt")
async def generate_prompt(request: PromptRequest):
    """Builds a finalized, high-quality prompt for AI modification tasks using templates."""
    if not request.file or not request.file.strip():
        raise HTTPException(status_code=400, detail="Path cannot be empty.")
    
    try:
        # 1. Load and validate target file
        resolved_path = is_safe_path(PROJECT_ROOT / request.file)
        if not resolved_path.is_file():
            raise HTTPException(status_code=404, detail="File not found.")
        
        with open(resolved_path, "r", encoding="utf-8", errors="ignore") as f:
            full_content = f.read()
        
        # 2. Gather project-wide file list for context
        all_files = fast_recursive_scan(str(PROJECT_ROOT))
        
        # 3. Clean and prepare file content (ONLY escape curly braces for raw content)
        safe_content = full_content.strip()
        if not safe_content:
            safe_content = "Empty file"
        
        escaped_content = safe_content.replace("{", "{{").replace("}", "}}")
        
        # 4. Build modular prompt sections
        language = detect_language(request.file)
        file_content_block = format_code_block(escaped_content, language)
        project_context = build_project_context(request.file, all_files)
        structure_section = build_structure_section(full_content)
        
        # 5. Assemble final prompt using template loaded dynamically from file
        template = load_prompt_template()
        try:
            prompt = template.format(
                project_context=project_context,
                file_path=request.file,
                structure_section=structure_section,
                file_content_block=file_content_block,
                errors="No known runtime or compile errors.",
                goal=request.goal
            )
        except KeyError as e:
            raise HTTPException(status_code=500, detail=f"Template placeholder missing: {str(e)}")
        
        return {"prompt": prompt}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prompt generation failed: {str(e)}")

# Configuration: Anti-abuse limits
MAX_PATCH_SIZE = 1 * 1024 * 1024  # 1 MB
MAX_PATCH_LINES = 20000

@app.post("/apply")
async def apply_patch(request: PatchRequest):
    """Safely applies a unified diff patch to the workspace with high reliability."""
    if not request.patch or not request.patch.strip():
        raise HTTPException(status_code=400, detail="Patch content is empty.")
    
    # 0. Anti-abuse limits
    if len(request.patch.encode("utf-8")) > MAX_PATCH_SIZE:
        raise HTTPException(status_code=400, detail="Patch size exceeds 1MB limit.")
    
    lines = request.patch.splitlines()
    if len(lines) > MAX_PATCH_LINES:
        raise HTTPException(status_code=400, detail="Patch exceeds 20,000 lines limit.")

    # 1. Basic format validation
    if not ("--- " in request.patch and "+++ " in request.patch and "@@" in request.patch):
        raise HTTPException(status_code=400, detail="Invalid patch format. Must be a unified diff.")
    
    # 2. Strict Path Validation & Normalization
    paths_found = re.findall(r"^(?:---|\+\+\+) ([^\t\n\r]+)", request.patch, re.MULTILINE)
    if not paths_found:
        raise HTTPException(status_code=400, detail="Could not find target file paths in patch headers.")
    
    validated_files = set()
    for p in paths_found:
        p = p.strip()
        # 4. Handle a/ and b/ prefixes
        if p.startswith("a/") or p.startswith("b/"):
            p = p[2:]
        
        # 3. NORMALIZE PATHS BEFORE VALIDATION
        normalized = os.path.normpath(p)
        
        # Reject absolute paths or traversal
        if normalized.startswith("/") or normalized.startswith("\\") or os.path.isabs(normalized) or ".." in normalized:
            raise HTTPException(status_code=403, detail=f"Forbidden path in patch: {p}")
        
        # Verify inside PROJECT_ROOT
        is_safe_path(PROJECT_ROOT / normalized)
        validated_files.add(normalized.replace("\\", "/"))
    
    # 6. SAFE TEMP FILE HANDLING
    # We use a unique name in the PROJECT_ROOT to ensure compatibility with all tools
    tmp_path = str(PROJECT_ROOT / f"loopforge_{os.getpid()}.patch")
    
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(request.patch)
        
        # 4. Check if already applied (No-op check)
        try:
            check_result = subprocess.run(
                ["patch", "-p0", "--batch", "--dry-run", "--input", tmp_path],
                cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=10
            )
            if check_result.returncode != 0:
                out_lower = check_result.stdout.lower()
                if "previously applied" in out_lower or "skipping patch" in out_lower:
                    return {"status": "noop", "message": "Patch already applied"}
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="Patch execution timed out")

        # 5. Apply Patch
        result = None
        try:
            result = subprocess.run(
                ["patch", "-p0", "--batch", "--forward", "--input", tmp_path],
                cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=10
            )
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="Patch execution timed out")

        # 6. SAFE GIT FALLBACK
        if result is None or result.returncode != 0:
            try:
                git_check = subprocess.run(
                    ["git", "apply", "--check", tmp_path],
                    cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=10
                )
                if git_check.returncode == 0:
                    result = subprocess.run(
                        ["git", "apply", tmp_path],
                        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=10
                    )
                else:
                    if result is None: result = git_check
            except FileNotFoundError:
                if result is None:
                    raise HTTPException(
                        status_code=500, 
                        detail="Patch utility not found. Install 'patch' or use Git Bash / WSL."
                    )
            except subprocess.TimeoutExpired:
                raise HTTPException(status_code=500, detail="Patch execution timed out")

        # 7. Final Result Handling
        if result is None or result.returncode != 0:
            # 7. LIMIT ERROR OUTPUT SIZE
            return {
                "detail": "Patch failed",
                "stderr": result.stderr[:2000] if result else "Unknown error",
                "stdout": result.stdout[:2000] if result else ""
            }
            
        # 8. IMPROVE SUCCESS RESPONSE
        return {
            "status": "success",
            "message": "Patch applied successfully",
            "files": sorted(list(validated_files))
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error applying patch: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

if __name__ == "__main__":
    import uvicorn
    # Use 0.0.0.0 to allow access from local network if needed, but keep it local-focused
    uvicorn.run(app, host="127.0.0.1", port=5000)
