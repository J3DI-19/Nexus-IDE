import os

# Optimization: Skip these directories entirely during scan
IGNORED_DIRS = {"node_modules", ".git", "__pycache__", ".vscode", ".idea", "dist", "build"}
# Optimization: Skip these common binary/large file types
IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".zip", ".tar", ".gz",
    ".exe", ".bin", ".pyc", ".o", ".obj", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf"
}

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
