from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Callable, Dict, List

from ..runtime.models import RuntimeArtifact, RuntimeArtifactType, StackTraceFrame
from core.runtime_registry import runtime_registry


class BaseChecker:
    def check(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        return []


def _artifact(message: str, file_path: str, line_number: int, language: str, kind: str = "syntax") -> RuntimeArtifact:
    return RuntimeArtifact(
        artifact_type=RuntimeArtifactType.COMPILER_ERROR,
        message=message,
        frames=[StackTraceFrame(file_path=file_path, line_number=line_number, symbol_name="Syntax")],
        raw_log=message,
        metadata={"lang": language, "type": kind, "source": "live_diagnostics"},
    )


class PythonChecker(BaseChecker):
    def check(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        try:
            ast.parse(content, filename=file_path)
            return []
        except SyntaxError as err:
            return [_artifact(f"SyntaxError: {err.msg}", file_path, err.lineno or 0, "python")]


class JsonChecker(BaseChecker):
    def check(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        try:
            json.loads(content)
            return []
        except json.JSONDecodeError as err:
            return [_artifact(f"JSONError: {err.msg}", file_path, err.lineno or 0, "json")]


class BraceBalanceChecker(BaseChecker):
    def __init__(self, language: str, brace_pairs: Dict[str, str]):
        self.language = language
        self.brace_pairs = brace_pairs

    def check(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        stack: List[tuple[str, int]] = []
        line = 1
        for char in content:
            if char == "\n":
                line += 1
                continue
            if char in self.brace_pairs:
                stack.append((char, line))
            elif char in self.brace_pairs.values():
                if not stack:
                    return [_artifact(f"Unmatched closing '{char}'", file_path, line, self.language)]
                opener, opener_line = stack.pop()
                if self.brace_pairs[opener] != char:
                    return [_artifact(f"Mismatched '{opener}' opened on line {opener_line}", file_path, line, self.language)]
        if stack:
            opener, opener_line = stack[-1]
            return [_artifact(f"Unclosed '{opener}' started on line {opener_line}", file_path, opener_line, self.language)]
        return []


class JavaScriptChecker(BaseChecker):
    def check(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        return BraceBalanceChecker("javascript", {"{": "}", "[": "]", "(": ")"}).check(file_path, content)


class TypeScriptChecker(JavaScriptChecker):
    def check(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        return super().check(file_path, content)


class JavaChecker(BaseChecker):
    def check(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        return BraceBalanceChecker("java", {"{": "}", "[": "]", "(": ")"}).check(file_path, content)


class CppChecker(BaseChecker):
    def check(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        return BraceBalanceChecker("cpp", {"{": "}", "[": "]", "(": ")"}).check(file_path, content)


class CSharpChecker(BaseChecker):
    def check(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        return BraceBalanceChecker("csharp", {"{": "}", "[": "]", "(": ")"}).check(file_path, content)


class DiagnosticsEngine:
    def __init__(self):
        self.checkers: Dict[str, BaseChecker] = {
            ".py": PythonChecker(),
            ".json": JsonChecker(),
            ".js": JavaScriptChecker(),
            ".jsx": JavaScriptChecker(),
            ".ts": TypeScriptChecker(),
            ".tsx": TypeScriptChecker(),
            ".java": JavaChecker(),
            ".c": CppChecker(),
            ".cc": CppChecker(),
            ".cpp": CppChecker(),
            ".cxx": CppChecker(),
            ".cs": CSharpChecker(),
        }

    def run_diagnostics(self, file_path: str, content: str) -> List[RuntimeArtifact]:
        ext = os.path.splitext(file_path)[1].lower()
        checker = self.checkers.get(ext)
        if checker:
            return checker.check(file_path, content)
        return []
