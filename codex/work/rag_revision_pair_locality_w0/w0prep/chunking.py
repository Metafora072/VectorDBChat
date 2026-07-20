"""Deterministic heading-aware chunking for the W0 preparation gate.

This module deliberately has no model or network dependency.  A pinned fast
tokenizer is injected by the caller; tests use a deterministic stand-in.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import re
import unicodedata
from typing import Any, Iterable, Sequence

from .common import canonical_json_bytes


MAX_PAYLOAD_TOKENS = 254
ROOT_SECTION = "<root>"


class ChunkingError(ValueError):
    """A deterministic document- or section-level exclusion."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)
        self.reason_code = reason_code
        self.detail = detail


@dataclass(frozen=True)
class Chunk:
    document_path: str
    section_path: str
    occurrence: int
    document_ordinal: int
    payload: str
    payload_sha256: str


@dataclass(frozen=True)
class _Section:
    path: str
    components: tuple[str, ...]
    body_lines: tuple[str, ...]


_WS_RE = re.compile(r"\s+", flags=re.UNICODE)
_ATX_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?)[ \t]*|[ \t]*)$")
_SETEXT_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_RST_ADORN_RE = re.compile(r"^([^\w\s])\1{2,}$", flags=re.UNICODE)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_chunk_id(source: str, chunk: Chunk) -> str:
    """Bind source and complete occurrence-aware chunk identity."""

    return sha256_hex(
        canonical_json_bytes(
            [
                source,
                chunk.document_path,
                chunk.section_path,
                chunk.occurrence,
                chunk.payload_sha256,
            ]
        )
    )


def normalize_heading(text: str) -> str:
    return _WS_RE.sub(" ", unicodedata.normalize("NFC", text).strip()).casefold()


def canonicalize_body(lines: Iterable[str]) -> str:
    """Apply the common body canonicalization after heading extraction."""

    cleaned = [line.rstrip(" \t") for line in lines]
    while cleaned and cleaned[0] == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    out: list[str] = []
    blanks = 0
    for line in cleaned:
        if line == "":
            blanks += 1
            if blanks <= 2:
                out.append("")
        else:
            blanks = 0
            out.append(line)
    return "\n".join(out)


def _validate_path(document_path: str) -> None:
    if not document_path or document_path.startswith("/"):
        raise ChunkingError("INVALID_DOCUMENT_PATH", document_path)
    parts = document_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ChunkingError("INVALID_DOCUMENT_PATH", document_path)


def _decode(raw: bytes | str) -> str:
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ChunkingError("INVALID_UTF8", str(exc)) from exc
    elif isinstance(raw, str):
        text = raw
    else:
        raise TypeError("raw document must be bytes or str")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _section_path(stack: Sequence[str]) -> str:
    return "/".join(stack) if stack else ROOT_SECTION


def _strip_atx_closer(text: str) -> str:
    # CommonMark-style closing hashes require whitespace before the run.
    return re.sub(r"[ \t]+#+[ \t]*$", "", text).strip()


def _markdown_sections(text: str) -> list[_Section]:
    lines = text.split("\n")
    if lines and lines[0] == "---":
        for i in range(1, len(lines)):
            if lines[i] in {"---", "..."}:
                lines = lines[i + 1 :]
                break

    sections: list[_Section] = []
    stack: list[tuple[int, str]] = []
    body: list[str] = []
    active_path = ROOT_SECTION
    fence_char: str | None = None
    fence_len = 0

    def flush() -> None:
        nonlocal body
        sections.append(
            _Section(active_path, tuple(title for _, title in stack), tuple(body))
        )
        body = []

    i = 0
    while i < len(lines):
        line = lines[i]
        fm = _FENCE_RE.match(line)
        if fence_char is not None:
            body.append(line)
            close_re = re.compile(
                rf"^ {{0,3}}{re.escape(fence_char)}{{{fence_len},}}[ \t]*$"
            )
            if close_re.match(line):
                fence_char = None
                fence_len = 0
            i += 1
            continue
        if fm:
            marker = fm.group(1)
            fence_char, fence_len = marker[0], len(marker)
            body.append(line)
            i += 1
            continue

        atx = _ATX_RE.match(line)
        if atx:
            flush()
            level = len(atx.group(1))
            heading = normalize_heading(_strip_atx_closer(atx.group(2) or ""))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, heading))
            active_path = _section_path([title for _, title in stack])
            i += 1
            continue

        if i + 1 < len(lines) and line.strip() and _SETEXT_RE.match(lines[i + 1]):
            underline = _SETEXT_RE.match(lines[i + 1])
            assert underline is not None
            flush()
            level = 1 if underline.group(1).startswith("=") else 2
            heading = normalize_heading(line)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, heading))
            active_path = _section_path([title for _, title in stack])
            i += 2
            continue

        body.append(line)
        i += 1
    flush()
    return sections


def _rst_adornment(line: str) -> str | None:
    if line != line.strip():
        return None
    match = _RST_ADORN_RE.match(line)
    return match.group(1) if match else None


def _rst_sections(text: str) -> list[_Section]:
    """Recognize unindented RST overline/underline and underline headings."""

    lines = text.split("\n")
    sections: list[_Section] = []
    stack: list[tuple[int, str]] = []
    body: list[str] = []
    active_path = ROOT_SECTION
    style_levels: dict[tuple[str, str], int] = {}

    def flush() -> None:
        nonlocal body
        sections.append(
            _Section(active_path, tuple(title for _, title in stack), tuple(body))
        )
        body = []

    def activate(style: tuple[str, str], title: str) -> None:
        nonlocal active_path, stack
        if style not in style_levels:
            style_levels[style] = len(style_levels) + 1
        level = style_levels[style]
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, normalize_heading(title)))
        active_path = _section_path([value for _, value in stack])

    i = 0
    while i < len(lines):
        over = _rst_adornment(lines[i])
        if (
            over is not None
            and i + 2 < len(lines)
            and lines[i + 1]
            and lines[i + 1] == lines[i + 1].strip()
            and _rst_adornment(lines[i + 2]) == over
        ):
            flush()
            activate(("overline", over), lines[i + 1])
            i += 3
            continue
        if (
            i + 1 < len(lines)
            and lines[i]
            and lines[i] == lines[i].strip()
            and (under := _rst_adornment(lines[i + 1])) is not None
        ):
            flush()
            activate(("underline", under), lines[i])
            i += 2
            continue
        body.append(lines[i])
        i += 1
    flush()
    return sections


def _token_offsets(tokenizer: Any, text: str) -> tuple[list[int], list[tuple[int, int]]]:
    encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    ids = encoded["input_ids"]
    offsets = encoded.get("offset_mapping")
    # A direct fast-tokenizer call is unbatched.  Reject batched results rather
    # than silently interpreting them differently.
    if ids and isinstance(ids[0], list):
        raise ChunkingError("TOKENIZER_BATCHED_OUTPUT")
    if offsets is None:
        raise ChunkingError("TOKENIZER_OFFSETS_UNAVAILABLE")
    return list(ids), [tuple(pair) for pair in offsets]


def _parts_for_paragraph(
    breadcrumb: str, paragraph: str, tokenizer: Any, max_tokens: int
) -> list[str]:
    separator = "\n\n"
    heading_ids, _ = _token_offsets(tokenizer, breadcrumb)
    if len(heading_ids) > max_tokens:
        raise ChunkingError("HEADING_OVER_CAP")
    fixed_ids, _ = _token_offsets(tokenizer, breadcrumb + separator)

    parts: list[str] = []
    remaining = paragraph
    while remaining:
        payload = breadcrumb + separator + remaining
        payload_ids, _ = _token_offsets(tokenizer, payload)
        if len(payload_ids) <= max_tokens:
            parts.append(remaining)
            break

        remaining_ids, offsets = _token_offsets(tokenizer, remaining)
        budget = max_tokens - len(fixed_ids)
        b = min(budget, len(remaining_ids) - 1)
        if b <= 0 or not offsets:
            cut = 1
            one_payload = breadcrumb + separator + remaining[:cut]
            if len(_token_offsets(tokenizer, one_payload)[0]) > max_tokens:
                raise ChunkingError("UNSPLITTABLE_OVER_CAP")
        else:
            cut = offsets[b][0]
            while cut > 0 and len(
                _token_offsets(tokenizer, breadcrumb + separator + remaining[:cut])[0]
            ) > max_tokens:
                b -= 1
                if b <= 0:
                    cut = 0
                    break
                cut = offsets[b][0]
            if cut <= 0:
                cut = 1
                if len(
                    _token_offsets(tokenizer, breadcrumb + separator + remaining[:cut])[0]
                ) > max_tokens:
                    raise ChunkingError("UNSPLITTABLE_OVER_CAP")
        parts.append(remaining[:cut])
        remaining = remaining[cut:]
    return parts


def chunk_document(
    document_path: str,
    raw: bytes | str,
    document_format: str,
    tokenizer: Any,
    *,
    max_payload_tokens: int = MAX_PAYLOAD_TOKENS,
) -> tuple[Chunk, ...]:
    """Chunk one Markdown or RST blob under the frozen W0 contract."""

    _validate_path(document_path)
    text = _decode(raw)
    fmt = document_format.lower()
    if fmt in {"md", "markdown"}:
        sections = _markdown_sections(text)
    elif fmt in {"rst", "restructuredtext"}:
        sections = _rst_sections(text)
    else:
        raise ChunkingError("UNSUPPORTED_DOCUMENT_FORMAT", document_format)

    occurrences: defaultdict[str, int] = defaultdict(int)
    chunks: list[Chunk] = []
    for section in sections:
        body = canonicalize_body(section.body_lines)
        if not body:
            continue
        breadcrumb = (
            "[SECTION] <root>"
            if section.path == ROOT_SECTION
            else "[SECTION] " + " > ".join(section.components)
        )
        # Check the heading budget even if a tokenizer happens to ignore LF.
        if len(_token_offsets(tokenizer, breadcrumb)[0]) > max_payload_tokens:
            raise ChunkingError("HEADING_OVER_CAP", section.path)
        paragraphs = [part for part in re.split(r"\n{2,}", body) if part]
        for paragraph in paragraphs:
            for part in _parts_for_paragraph(
                breadcrumb, paragraph, tokenizer, max_payload_tokens
            ):
                payload = breadcrumb + "\n\n" + part
                occurrence = occurrences[section.path]
                chunks.append(
                    Chunk(
                        document_path=document_path,
                        section_path=section.path,
                        occurrence=occurrence,
                        document_ordinal=len(chunks),
                        payload=payload,
                        payload_sha256=sha256_hex(payload.encode("utf-8")),
                    )
                )
                occurrences[section.path] += 1
    return tuple(chunks)
