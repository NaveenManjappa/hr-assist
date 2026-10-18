from hr_assist.corpus import Chunk, ManifestEntry
from hr_assist.ingestion.chunking import ChunkingStrategy, StructureV1
from hr_assist.ingestion.normaliser import check_running_header, check_title_slide, normalise
from hr_assist.ingestion.parser import DeckParser, Page, PdfParser


def build_chunks(
    entries: list[ManifestEntry], strategy: ChunkingStrategy | None = None
) -> list[Chunk]:
    """Turns every Source Document in the manifest into chunks, ready to embed."""
    strategy = strategy or StructureV1()
    chunks: list[Chunk] = []
    for entry in entries:
        chunks.extend(strategy.chunk(entry, _load(entry)))
    return chunks


def _load(entry: ManifestEntry) -> list[Page]:
    """Parses a Summary Deck or a PDF and checks it is the document the manifest says it is."""
    if entry.kind == "summary_deck":
        slides = DeckParser().parse(entry)
        check_title_slide(entry, slides)
        return slides
    pages = PdfParser().parse(entry)
    check_running_header(entry, pages)
    return normalise(pages)
