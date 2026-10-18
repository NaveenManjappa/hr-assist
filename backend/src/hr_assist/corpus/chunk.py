from datetime import date

from pydantic import BaseModel, ConfigDict, model_validator

from hr_assist.corpus.manifest import DocumentKind, DocumentStatus


class ChunkMetadata(BaseModel):
    """Where a chunk sits: a numbered section and pages of a PDF, or one slide of a deck."""

    model_config = ConfigDict(extra="ignore")

    document_id: str
    document_version: str
    title: str
    document_kind: DocumentKind
    status: DocumentStatus
    effective_from: date
    effective_to: date | None
    section_number: str | None
    section_title: str
    section_path: list[str]
    page_start: int | None = None
    page_end: int | None = None
    slide: int | None = None
    chunking_version: str

    @model_validator(mode="after")
    def _located_by_pages_or_slide(self) -> "ChunkMetadata":
        has_pages = self.page_start is not None and self.page_end is not None
        if has_pages == (self.slide is not None):
            raise ValueError("a chunk is located by pages or by a slide, not both or neither")
        return self


class Chunk(BaseModel):
    """A piece of a Source Document as embedded: header lines, a blank line, then the body."""

    id: str
    text: str
    metadata: ChunkMetadata

    @property
    def body(self) -> str:
        return self.text.split("\n\n", 1)[-1]
