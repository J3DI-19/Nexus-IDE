from typing import List, Optional
import subprocess
import os
from pathlib import Path
from ..runtime.models import RuntimeArtifact, RuntimeArtifactType, StackTraceFrame

class BaseChecker:
    def check(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        return []

class PythonChecker(BaseChecker):
    def check(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        artifacts = []
        # Use python -m py_compile to check syntax
        # We need to write to a temp file or use a pipe if possible, 
        # but py_compile usually wants a file.
        # For simplicity, we'll check the saved file on disk since this is triggered post-save.
        try:
            # We don't actually need to compile, just check for SyntaxError
            # compile(content, file_path, 'exec') is faster and doesn't need disk
            compile(content, file_path, 'exec')
        except SyntaxError as e:
            frames = [StackTraceFrame(
                file_path=file_path,
                line_number=e.lineno or 0,
                symbol_name="Syntax"
            )]
            artifacts.append(RuntimeArtifact(
                artifact_type=RuntimeArtifactType.COMPILER_ERROR,
                message=f"SyntaxError: {e.msg}",
                frames=frames,
                raw_log=str(e),
                metadata={"lang": "python", "type": "syntax"}
            ))
        except Exception as e:
            pass
            
        return artifacts

class JavaScriptChecker(BaseChecker):
    def check(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        # Simple node syntax check if available
        return []

class DiagnosticsEngine:
    def __init__(self):
        self.checkers = {
            ".py": PythonChecker(),
            ".js": JavaScriptChecker(),
            ".jsx": JavaScriptChecker(),
            # Add more as needed
        }

    def run_diagnostics(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        ext = os.path.splitext(file_path)[1].lower()
        checker = self.checkers.get(ext)
        if checker:
            return checker.check(file_path, content)
        return []
