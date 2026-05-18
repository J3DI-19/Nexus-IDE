import os
import hashlib
from pathlib import Path
from typing import List

# Deterministic ignore directories for project scanning/indexing.
# Keep this set centralized and extensible for future ignore config support.
IGNORED_DIRS = {
    ".git",
    ".vscode",
    ".idea",
    ".nexus",
    "node_modules",
    "dist",
    "build",
    "out",
    "coverage",
    ".next",
    ".gradle",
    "venv",
    "__pycache__",
    "workspace",
    "tmp",
    ".cache",
}
IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".zip", ".tar", ".gz",
    ".exe", ".bin", ".pyc", ".o", ".obj", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf"
}


def _normalize_rel_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _should_exclude_rel_path(rel_path: str) -> bool:
    normalized = _normalize_rel_path(rel_path)
    if not normalized:
        return False
    parts = normalized.split("/")
    return any(part in IGNORED_DIRS for part in parts)

def fast_recursive_scan(root_path: str, include_dirs: bool = False) -> List[str]:
    """
    High-performance directory traversal.
    Returns sorted list of relative paths.
    Directories are included with a trailing slash if include_dirs is True.
    """
    root = Path(root_path).resolve()
    file_list: List[str] = []
    
    def _scan(current_dir: Path):
        try:
            with os.scandir(current_dir) as entries:
                for entry in entries:
                    rel_path = _normalize_rel_path(os.path.relpath(entry.path, root))
                    if _should_exclude_rel_path(rel_path):
                        continue

                    if entry.is_dir(follow_symlinks=False):
                        if include_dirs:
                            file_list.append(rel_path + "/")
                        _scan(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext not in IGNORED_EXTENSIONS:
                            file_list.append(rel_path)
        except (PermissionError, OSError):
            pass

    _scan(root)
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
