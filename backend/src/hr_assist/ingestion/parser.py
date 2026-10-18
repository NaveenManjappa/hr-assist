from dataclasses import dataclass
from typing import Protocol

from hr_assist.corpus import ManifestEntry


@dataclass(frozen=True)
class Page:
    number: int
    text: str


class Parser(Protocol):
    def parse(self, entry: ManifestEntry) -> list[Page]: ...


class PdfParser:
    """Loads each PDF page as Markdown, which keeps headings and pipe tables (ADR 0001)."""

    def parse(self, entry: ManifestEntry) -> list[Page]:
        from langchain_pymupdf4llm import PyMuPDF4LLMLoader

        documents = PyMuPDF4LLMLoader(entry.path, mode="page").load()
        return [Page(number=doc.metadata["page"] + 1, text=doc.page_content) for doc in documents]
