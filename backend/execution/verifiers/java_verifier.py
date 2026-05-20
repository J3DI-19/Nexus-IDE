from __future__ import annotations

from pathlib import Path
from typing import Set

from .base import FileVerificationResult, SyntaxVerifier, VerificationDiagnostic


class JavaSyntaxVerifier(SyntaxVerifier):
    @property
    def name(self) -> str:
        return "java_delimiter_checker"

    @property
    def supported_extensions(self) -> Set[str]:
        return {".java"}

    def verify(self, path: Path, content: str) -> FileVerificationResult:
        result = FileVerificationResult(path=str(path))
        issue = _scan_for_unbalanced_tokens(content)
        if issue:
            result.failed = True
            result.diagnostics.append(
                VerificationDiagnostic(
                    severity="error",
                    code="syntax_error",
                    message="Java syntax validation failed.",
                    path=str(path),
                    verifier=self.name,
                    details=issue,
                )
            )
            return result
        result.verified = True
        return result


def _scan_for_unbalanced_tokens(content: str) -> str | None:
    pairs = {"}": "{", ")": "(", "]": "["}
    stack: list[tuple[str, int]] = []
    in_line_comment = False
    in_block_comment = False
    in_string = False
    in_char = False
    escaped = False

    for idx, ch in enumerate(content):
        nxt = content[idx + 1] if idx + 1 < len(content) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
            continue
        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue
        if in_char:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == "'":
                in_char = False
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "'":
            in_char = True
            continue

        if ch in "{([":
            stack.append((ch, idx))
            continue
        if ch in "})]":
            if not stack:
                return f"Unexpected closing token '{ch}'"
            open_tok, _ = stack.pop()
            if pairs[ch] != open_tok:
                return f"Mismatched token '{ch}' for opener '{open_tok}'"

    if in_string:
        return "Unclosed string literal"
    if in_char:
        return "Unclosed character literal"
    if in_block_comment:
        return "Unclosed block comment"
    if stack:
        open_tok, _ = stack[-1]
        return f"Unclosed token '{open_tok}'"
    return None
