from hr_assist.corpus import Chunk, ManifestEntry
from hr_assist.ingestion.chunking import ChunkingStrategy, StructureV1
from hr_assist.ingestion.normaliser import normalise
from hr_assist.ingestion.parser import Parser, PdfParser


def build_chunks(
    entries: list[ManifestEntry],
    parser: Parser | None = None,
    strategy: ChunkingStrategy | None = None,
) -> list[Chunk]:
    """Turns every Source Document in the manifest into chunks, ready to embed."""
    parser = parser or PdfParser()
    strategy = strategy or StructureV1()
    chunks: list[Chunk] = []
    for entry in entries:
        chunks.extend(strategy.chunk(entry, normalise(parser.parse(entry))))
    return chunks
