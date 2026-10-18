import re
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from langchain_text_splitters import RecursiveCharacterTextSplitter

from hr_assist.corpus import Chunk, ChunkMetadata, ManifestEntry
from hr_assist.ingestion.parser import Page

_NUMBERED_HEADING = re.compile(r"^#{1,6}\s+(?:\*\*)?(\d+(?:\.\d+)*)\s+(.+?)(?:\*\*)?\s*$")
_CHUNK_NAMESPACE = uuid.UUID("5b0f8a52-7d0e-4c4e-9a43-2f9a8d0a1c11")


class ChunkingStrategy(Protocol):
    version: str

    def chunk(self, entry: ManifestEntry, pages: list[Page]) -> list[Chunk]: ...


@dataclass
class _Section:
    number: str
    title: str
    page_start: int
    page_end: int
    lines: list[str] = field(default_factory=list)

    @property
    def body(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "\n".join(self.lines)).strip()


class StructureV1:
    """One chunk per numbered section, split further only when a section is oversized.

    The PDFs use heading levels inconsistently (3.1 is `##`, 3.3 is `#`), so the section
    hierarchy comes from the section numbers. Unnumbered headings such as worked examples stay
    inside the section they belong to. Everything before the first numbered section (cover,
    document control, contents) is dropped.
    """

    version = "structure_v1"

    def __init__(self, max_tokens: int = 500, overlap_tokens: int = 60) -> None:
        self._splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="o200k_base", chunk_size=max_tokens, chunk_overlap=overlap_tokens
        )

    def chunk(self, entry: ManifestEntry, pages: list[Page]) -> list[Chunk]:
        sections = _split_into_sections(pages)
        titles = {section.number: f"{section.number} {section.title}" for section in sections}
        chunks = []
        for section in sections:
            if not section.body:
                continue
            path = [titles[n] for n in _ancestors(section.number) if n in titles]
            header = f"{_document_line(entry)}\n{' > '.join(path)}"
            for part, body in enumerate(self._splitter.split_text(section.body)):
                chunks.append(
                    Chunk(
                        id=str(
                            uuid.uuid5(
                                _CHUNK_NAMESPACE,
                                f"{entry.document_id}|{entry.document_version}|"
                                f"{section.number}|{part}",
                            )
                        ),
                        text=f"{header}\n\n{body}",
                        metadata=ChunkMetadata(
                            document_id=entry.document_id,
                            document_version=entry.document_version,
                            title=entry.title,
                            document_kind=entry.kind,
                            status=entry.status,
                            effective_from=entry.effective_from,
                            effective_to=entry.effective_to,
                            section_number=section.number,
                            section_title=section.title,
                            section_path=path,
                            page_start=section.page_start,
                            page_end=section.page_end,
                            chunking_version=self.version,
                        ),
                    )
                )
        return chunks


def _split_into_sections(pages: list[Page]) -> list[_Section]:
    sections: list[_Section] = []
    for page in pages:
        for line in page.text.splitlines():
            heading = _NUMBERED_HEADING.match(line.strip())
            if heading:
                number, title = heading.groups()
                sections.append(_Section(number, title.strip("* "), page.number, page.number))
            elif sections:
                sections[-1].lines.append(line)
                if line.strip():
                    sections[-1].page_end = page.number
    return sections


def _ancestors(number: str) -> list[str]:
    parts = number.split(".")
    return [".".join(parts[: i + 1]) for i in range(len(parts))]


def _document_line(entry: ManifestEntry) -> str:
    period = f"effective {entry.effective_from.isoformat()}"
    if entry.effective_to is not None:
        period += f" to {entry.effective_to.isoformat()}"
    return f"{entry.title} ({entry.document_id} {entry.document_version}, {entry.status}, {period})"
