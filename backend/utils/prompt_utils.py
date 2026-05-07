import os
from pathlib import Path
from fastapi import HTTPException
from context_engine.adapters import registry

# Robustness: Use relative path based on this file
TEMPLATE_PATH = Path(__file__).parent.parent.parent / "templates" / "PromptTemplateV1.txt"

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
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".py": "python",
        ".css": "css",
        ".html": "html",
        ".json": "json",
        ".md": "markdown"
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

def _fallback_structure_parser(content: str) -> dict:
    """Naive string-based extraction for non-Python or broken files."""
    lines = content.splitlines()
    imports = []
    classes = []
    functions = []
    
    for line in lines:
        trimmed = line.strip()
        if trimmed.startswith(("import ", "from ", "require(")):
            imports.append(f"* {trimmed}")
        elif trimmed.startswith("class "):
            classes.append(f"* {trimmed.split('{')[0].strip()}")
        elif trimmed.startswith(("function ", "def ")):
            functions.append(f"* {trimmed.split('{')[0].strip()}")
            
    return {
        "imports": imports,
        "classes": classes,
        "functions": functions,
        "methods": []
    }

def _format_structure_sections(structure_data: dict) -> str:
    """Converts structured data into a formatted string compatible with templates."""
    result = []
    
    sections = [
        ("Imports:", "imports"),
        ("Classes:", "classes"),
        ("Functions:", "functions"),
        ("Methods:", "methods")
    ]
    
    for title, key in sections:
        items = structure_data.get(key, [])
        if items:
            section_text = f"{title}\n" + "\n".join(items)
            if key == "imports":
                section_text += "\n(These imports may affect the logic of this file.)"
            result.append(section_text)
            
    return "\n\n".join(result) if result else "No significant structure detected."

def build_structure_section(content: str, file_path: str) -> str:
    """Dispatches to appropriate adapter or fallback based on file extension."""
    adapter = registry.get_adapter_for_file(file_path)
    
    if adapter:
        try:
            symbols = adapter.extract_symbols(content, file_path)
            dependencies = adapter.extract_dependencies(content, file_path)
            
            # Map new models back to old dict structure for backward compatibility
            structure_data = {
                "imports": [f"* {d.target_id}" for d in dependencies if d.type == "import"],
                "classes": [f"* class {s.name}" for s in symbols if s.type == "class"],
                "functions": [f"* def {s.name}" for s in symbols if s.type == "function"],
                "methods": [f"* def {s.name}" for s in symbols if s.type == "method"]
            }
        except Exception as e:
            print(f"Adapter extraction failed for {file_path}: {e}")
            structure_data = _fallback_structure_parser(content)
    else:
        structure_data = _fallback_structure_parser(content)
        
    return _format_structure_sections(structure_data)

def format_code_block(content: str, language: str) -> str:
    """Formats file content into a markdown code block with truncation."""
    lines = content.splitlines()
    truncated_content = "\n".join(lines[:300]).strip()
    if len(lines) > 300:
        truncated_content += "\n... (truncated)"
        
    return truncated_content
