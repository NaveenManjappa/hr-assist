import re
import uuid
from dataclasses import dataclass, field
from typing import Protocol

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from hr_assist.corpus import Chunk, ChunkMetadata, ManifestEntry
from hr_assist.ingestion.parser import Page

_NUMBERED_HEADING = re.compile(r"^#{1,6}\s+(?:\*\*)?(\d+(?:\.\d+)*)\s+(.+?)(?:\*\*)?\s*$")
# Headings and table captions lead into the block after them, so they are never parted from it.
_LEAD_IN = re.compile(r"^(?:#{1,6}\s|\*\*Table\b)")
_CHUNK_NAMESPACE = uuid.UUID("5b0f8a52-7d0e-4c4e-9a43-2f9a8d0a1c11")
_ENCODING = "o200k_base"


class ChunkingStrategy(Protocol):
    version: str

    def chunk(self, entry: ManifestEntry, pages: list[Page]) -> list[Chunk]: ...


@dataclass
class _Block:
    """A paragraph, list item or table, with the pages its text sits on."""

    text: str
    page_start: int
    page_end: int
    is_table: bool = False


@dataclass
class _Section:
    number: str
    title: str
    page_start: int
    page_end: int
    lines: list[tuple[int, str]] = field(default_factory=list)

    def blocks(self) -> list[_Block]:
        """Splits the body at blank lines, keeping tables whole and headings with their text."""
        blocks: list[_Block] = []
        current: list[tuple[int, str]] = []
        for page, line in [*self.lines, (0, "")]:
            if line.strip():
                current.append((page, line))
                continue
            if current:
                pages = [p for p, _ in current]
                text = "\n".join(line for _, line in current).strip()
                is_table = all(line.startswith("|") for _, line in current)
                blocks.append(_Block(text, min(pages), max(pages), is_table))
                current = []
        return _attach_lead_ins(blocks)


class StructureV1:
    """One chunk per numbered section, split further only when a section is oversized.

    The PDFs use heading levels inconsistently (3.1 is `##`, 3.3 is `#`), so the section
    hierarchy comes from the section numbers. Unnumbered headings such as worked examples stay
    inside the section they belong to. Everything before the first numbered section (cover,
    document control, contents) is dropped.

    An oversized section is packed into parts of whole paragraphs and tables. A table is never
    split, so a part holding a long table can exceed the size limit. Each part carries the pages
    its own text sits on.

    A Summary Deck becomes one chunk per slide, located by its slide number instead of pages.
    """

    version = "structure_v1"

    def __init__(self, max_tokens: int = 500, overlap_tokens: int = 60) -> None:
        self._max_tokens = max_tokens
        self._overlap_tokens = overlap_tokens
        self._encoding = tiktoken.get_encoding(_ENCODING)
        self._splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name=_ENCODING, chunk_size=max_tokens, chunk_overlap=overlap_tokens
        )

    def chunk(self, entry: ManifestEntry, pages: list[Page]) -> list[Chunk]:
        if entry.kind == "summary_deck":
            return [self._slide_chunk(entry, slide) for slide in pages]
        sections = _split_into_sections(pages)
        titles = {section.number: f"{section.number} {section.title}" for section in sections}
        chunks = []
        for section in sections:
            path = [titles[n] for n in _ancestors(section.number) if n in titles]
            header = f"{_document_line(entry)}\n{' > '.join(path)}"
            for part, blocks in enumerate(self._parts(section.blocks())):
                chunks.append(
                    self._chunk(
                        entry,
                        key=f"{section.number}|{part}",
                        text=f"{header}\n\n{_join(blocks)}",
                        section_number=section.number,
                        section_title=section.title,
                        section_path=path,
                        page_start=min(b.page_start for b in blocks),
                        page_end=max(b.page_end for b in blocks),
                    )
                )
        return chunks

    def _slide_chunk(self, entry: ManifestEntry, slide: Page) -> Chunk:
        title = slide.text.split("\n\n", 1)[0].removeprefix("## ").strip()
        return self._chunk(
            entry,
            key=f"slide {slide.number}",
            text=f"{_document_line(entry)}\nSlide {slide.number}\n\n{slide.text}",
            section_number=None,
            section_title=title,
            section_path=[title],
            slide=slide.number,
        )

    def _chunk(
        self,
        entry: ManifestEntry,
        key: str,
        text: str,
        section_number: str | None,
        section_title: str,
        section_path: list[str],
        page_start: int | None = None,
        page_end: int | None = None,
        slide: int | None = None,
    ) -> Chunk:
        """A chunk with a stable ID and the document facts from its manifest entry."""
        return Chunk(
            id=str(
                uuid.uuid5(_CHUNK_NAMESPACE, f"{entry.document_id}|{entry.document_version}|{key}")
            ),
            text=text,
            metadata=ChunkMetadata(
                document_id=entry.document_id,
                document_version=entry.document_version,
                title=entry.title,
                document_kind=entry.kind,
                status=entry.status,
                effective_from=entry.effective_from,
                effective_to=entry.effective_to,
                section_number=section_number,
                section_title=section_title,
                section_path=section_path,
                page_start=page_start,
                page_end=page_end,
                slide=slide,
                chunking_version=self.version,
            ),
        )

    def _parts(self, blocks: list[_Block]) -> list[list[_Block]]:
        """Packs blocks into parts within the size limit, overlapping by trailing paragraphs."""
        if not blocks:
            return []
        if self._tokens(_join(blocks)) <= self._max_tokens:
            return [blocks]

        parts: list[list[_Block]] = []
        current: list[_Block] = []
        for block in self._fit(blocks):
            if current and self._tokens(_join([*current, block])) > self._max_tokens:
                parts.append(current)
                current = self._overlap(current)
                if self._tokens(_join([*current, block])) > self._max_tokens:
                    current = []
            current.append(block)
        parts.append(current)
        return parts

    def _fit(self, blocks: list[_Block]) -> list[_Block]:
        """Splits paragraphs that alone exceed the size limit. Tables stay whole."""
        fitted = []
        for block in blocks:
            if block.is_table or self._tokens(block.text) <= self._max_tokens:
                fitted.append(block)
            else:
                fitted.extend(
                    _Block(piece, block.page_start, block.page_end)
                    for piece in self._splitter.split_text(block.text)
                )
        return fitted

    def _overlap(self, part: list[_Block]) -> list[_Block]:
        carried: list[_Block] = []
        for block in reversed(part):
            if block.is_table or self._tokens(_join([block, *carried])) > self._overlap_tokens:
                break
            carried.insert(0, block)
        return carried

    def _tokens(self, text: str) -> int:
        return len(self._encoding.encode(text))


def _split_into_sections(pages: list[Page]) -> list[_Section]:
    sections: list[_Section] = []
    for page in pages:
        for line in page.text.splitlines():
            heading = _NUMBERED_HEADING.match(line.strip())
            if heading:
                number, title = heading.groups()
                sections.append(_Section(number, title.strip("* "), page.number, page.number))
            elif sections:
                sections[-1].lines.append((page.number, line))
                if line.strip():
                    sections[-1].page_end = page.number
    return sections


def _attach_lead_ins(blocks: list[_Block]) -> list[_Block]:
    attached: list[_Block] = []
    for block in blocks:
        previous = attached[-1] if attached else None
        if previous and not previous.is_table and _LEAD_IN.match(previous.text.splitlines()[-1]):
            attached[-1] = _Block(
                f"{previous.text}\n\n{block.text}",
                previous.page_start,
                block.page_end,
                block.is_table,
            )
        else:
            attached.append(block)
    return attached


def _join(blocks: list[_Block]) -> str:
    return "\n\n".join(block.text for block in blocks)


def _ancestors(number: str) -> list[str]:
    parts = number.split(".")
    return [".".join(parts[: i + 1]) for i in range(len(parts))]


def _document_line(entry: ManifestEntry) -> str:
    period = f"effective {entry.effective_from.isoformat()}"
    if entry.effective_to is not None:
        period += f" to {entry.effective_to.isoformat()}"
    kind = "summary deck, " if entry.kind == "summary_deck" else ""
    return (
        f"{entry.title} ({entry.document_id} {entry.document_version}, "
        f"{kind}{entry.status}, {period})"
    )
