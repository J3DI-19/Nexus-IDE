from __future__ import annotations

from pathlib import Path
from typing import Set

from .base import FileVerificationResult, SyntaxVerifier, VerificationDiagnostic


class KotlinSyntaxVerifier(SyntaxVerifier):
    @property
    def name(self) -> str:
        return "kotlin_delimiter_checker"

    @property
    def supported_extensions(self) -> Set[str]:
        return {".kt", ".kts"}

    def verify(self, path: Path, content: str) -> FileVerificationResult:
        result = FileVerificationResult(path=str(path))
        issue = _scan_for_unbalanced_tokens(content)
        if issue:
            result.failed = True
            result.diagnostics.append(
                VerificationDiagnostic(
                    severity="error",
                    code="syntax_error",
                    message="Kotlin syntax validation failed.",
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
    in_triple = False
    escaped = False

    i = 0
    length = len(content)
    while i < length:
        ch = content[i]
        nxt = content[i + 1] if i + 1 < length else ""
        nxt2 = content[i + 2] if i + 2 < length else ""
        tri = ch == '"' and nxt == '"' and nxt2 == '"'

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_triple:
            if tri:
                in_triple = False
                i += 3
                continue
            i += 1
            continue
        if in_string:
            if escaped:
                escaped = False
                i += 1
                continue
            if ch == "\\":
                escaped = True
                i += 1
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            if escaped:
                escaped = False
                i += 1
                continue
            if ch == "\\":
                escaped = True
                i += 1
                continue
            if ch == "'":
                in_char = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if tri:
            in_triple = True
            i += 3
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "'":
            in_char = True
            i += 1
            continue

        if ch in "{([":
            stack.append((ch, i))
            i += 1
            continue
        if ch in "})]":
            if not stack:
                return f"Unexpected closing token '{ch}'"
            open_tok, _ = stack.pop()
            if pairs[ch] != open_tok:
                return f"Mismatched token '{ch}' for opener '{open_tok}'"
        i += 1

    if in_triple:
        return "Unclosed triple-quoted string literal"
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
