from datetime import date

from pydantic import BaseModel, ConfigDict

from hr_assist.corpus.manifest import DocumentKind, DocumentStatus


class ChunkMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_id: str
    document_version: str
    title: str
    document_kind: DocumentKind
    status: DocumentStatus
    effective_from: date
    effective_to: date | None
    section_number: str
    section_title: str
    section_path: list[str]
    page_start: int
    page_end: int
    chunking_version: str


class Chunk(BaseModel):
    """A piece of a Source Document as embedded: header lines, a blank line, then the body."""

    id: str
    text: str
    metadata: ChunkMetadata

    @property
    def body(self) -> str:
        return self.text.split("\n\n", 1)[-1]
