import os
import re
from pathlib import Path
from typing import List, Optional
from .models import CodeSlice
from ..models.symbol import Symbol

class CodeSlicer:
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)

    def extract_lines(self, rel_path: str, start_line: int, end_line: int, reason: str) -> Optional[CodeSlice]:
        """Extracts a specific range of lines from a file."""
        abs_path = self.root_path / rel_path
        if not abs_path.is_file():
            return None

        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            
            # Line numbers are usually 1-indexed in IDEs/ASTs
            actual_start = max(0, start_line - 1)
            actual_end = min(len(lines), end_line)
            
            content = "".join(lines[actual_start:actual_end])
            return CodeSlice(
                content=content.strip(),
                start_line=start_line,
                end_line=end_line,
                reason=reason
            )
        except Exception as e:
            print(f"[Slicer] Failed to read {rel_path}: {e}")
            return None

    def extract_symbol(self, rel_path: str, symbol: Symbol, reason: str) -> Optional[CodeSlice]:
        """Extracts the code for a specific symbol, expanding if end_line is not provided."""
        start_line = symbol.start_line
        end_line = symbol.end_line
        
        # If adapter didn't provide a valid end_line (or it's just the start line), try to expand
        if end_line <= start_line:
            end_line = self._expand_symbol_range(rel_path, start_line)

        return self.extract_lines(
            rel_path, 
            start_line, 
            end_line, 
            reason=f"Symbol: {symbol.name} ({reason})"
        )

    def extract_imports(self, rel_path: str) -> Optional[CodeSlice]:
        """Extracts import statements from the top of the file."""
        abs_path = self.root_path / rel_path
        if not abs_path.is_file():
            return None

        ext = rel_path.lower().split('.')[-1]
        
        # Simple heuristic: take lines that look like imports until we hit real code
        import_patterns = {
            'py': re.compile(r'^(import\s+|from\s+)'),
            'ts': re.compile(r'^(import\s+)'),
            'tsx': re.compile(r'^(import\s+)'),
            'js': re.compile(r'^(import\s+|const\s+.*require\()'),
            'jsx': re.compile(r'^(import\s+|const\s+.*require\()'),
        }
        
        pattern = import_patterns.get(ext)
        if not pattern:
            return None

        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            
            import_lines = []
            last_import_idx = 0
            for i, line in enumerate(lines):
                if pattern.match(line.strip()) or line.strip() == "":
                    if line.strip() != "":
                        import_lines.append(line)
                        last_import_idx = i + 1
                elif i > 0 and (lines[i-1].strip().endswith(',') or lines[i-1].strip().startswith('{')):
                    # Likely multi-line import
                    import_lines.append(line)
                    last_import_idx = i + 1
                elif i > 50: # Don't scan too far
                    break
                else:
                    # Not an import and not clearly a continuation
                    if line.strip() != "":
                        break
            
            if not import_lines:
                return None
                
            return CodeSlice(
                content="".join(import_lines).strip(),
                start_line=1,
                end_line=last_import_idx,
                reason="Module Imports"
            )
        except Exception:
            return None

    def _expand_symbol_range(self, rel_path: str, start_line: int) -> int:
        """Deterministically expands from a start line to find the matching closing brace or tag."""
        abs_path = self.root_path / rel_path
        if not abs_path.is_file():
            return start_line

        ext = rel_path.lower().split('.')[-1]
        is_xml_html = ext in {"html", "xml", "htm", "tsx", "jsx"}

        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            
            if start_line > len(lines):
                return start_line
                
            start_idx = start_line - 1
            
            if is_xml_html:
                return self._expand_xml_tag_range(lines, start_idx)
            
            # Simple brace tracking for code
            brace_count = 0
            found_first_brace = False
            
            for i in range(start_idx, len(lines)):
                line = lines[i]
                brace_count += line.count('{')
                if not found_first_brace and '{' in line:
                    found_first_brace = True
                
                brace_count -= line.count('}')
                
                if found_first_brace and brace_count <= 0:
                    return i + 1
            
            return min(start_line + 20, len(lines))
            
        except Exception:
            return start_line

    def _expand_xml_tag_range(self, lines: List[str], start_idx: int) -> int:
        """Finds the closing tag for a given XML/HTML start tag."""
        tag_match = re.search(r'<([\w\.-]+)', lines[start_idx])
        if not tag_match:
            return start_idx + 1
            
        tag_name = tag_match.group(1)
        # Self-closing check
        if '/>' in lines[start_idx]:
            return start_idx + 1
            
        open_tag = f"<{tag_name}"
        close_tag = f"</{tag_name}>"
        
        stack = 1
        for i in range(start_idx + 1, len(lines)):
            line = lines[i]
            # Simple count (could be improved to handle multiple tags on one line)
            stack += line.count(open_tag)
            stack -= line.count(close_tag)
            
            if stack <= 0:
                return i + 1
        
        return min(start_idx + 50, len(lines))

    def extract_full_file(self, rel_path: str, reason: str, max_lines: int = 500) -> Optional[CodeSlice]:
        """Extracts the entire file (or a large chunk) as a slice."""
        abs_path = self.root_path / rel_path
        if not abs_path.is_file():
            return None
        
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            lines = content.splitlines()
            if len(lines) > max_lines:
                content = "\n".join(lines[:max_lines]) + "\n... (truncated)"
            
            return CodeSlice(
                content=content.strip(),
                start_line=1,
                end_line=min(len(lines), max_lines),
                reason=reason
            )
        except Exception:
            return None
