import os
import hashlib
from typing import List, Set

# Shared ignore lists
IGNORED_DIRS = {
    "node_modules", ".git", "__pycache__", ".vscode", ".idea", 
    "dist", "build", ".nexus", "venv", ".env"
}
IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".zip", ".tar", ".gz",
    ".exe", ".bin", ".pyc", ".o", ".obj", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf"
}

def fast_recursive_scan(root_path: str, include_dirs: bool = False) -> List[str]:
    """
    High-performance directory traversal.
    Returns sorted list of relative paths.
    Directories are included with a trailing slash if include_dirs is True.
    """
    file_list = []
    
    def _scan(current_dir):
        try:
            with os.scandir(current_dir) as entries:
                for entry in entries:
                    if entry.name.startswith(".") and entry.name != ".nexus" or entry.name in IGNORED_DIRS:
                        continue
                    
                    if entry.is_dir(follow_symlinks=False):
                        if include_dirs:
                            rel_path = os.path.relpath(entry.path, root_path)
                            file_list.append(rel_path.replace("\\", "/") + "/")
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

def compute_file_hash(file_path: str) -> str:
    """Computes SHA-256 hash for incremental tracking."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception:
        return ""
