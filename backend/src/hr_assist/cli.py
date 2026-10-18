import argparse
from collections import Counter
from pathlib import Path

from hr_assist.corpus import load_manifest
from hr_assist.corpus.manifest import DEFAULT_MANIFEST
from hr_assist.settings import Settings


def ingest(manifest: Path) -> None:
    from hr_assist.ingestion import StructureV1, build_chunks
    from hr_assist.ingestion.index import rebuild_index

    settings = Settings()
    strategy = StructureV1()
    if strategy.version != settings.chunking_version:
        raise SystemExit(
            f"CHUNKING_VERSION is {settings.chunking_version}, "
            f"but ingestion builds {strategy.version}"
        )

    chunks = build_chunks(load_manifest(manifest), strategy=strategy)
    for (document_id, version), count in Counter(
        (c.metadata.document_id, c.metadata.document_version) for c in chunks
    ).items():
        print(f"{document_id} {version}: {count} chunks")

    rebuild_index(chunks, settings)
    print(f"Rebuilt {settings.collection_name} with {len(chunks)} chunks")


def main() -> None:
    parser = argparse.ArgumentParser(prog="hr-assist")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest_command = commands.add_parser("ingest", help="Rebuild the index from the manifest")
    ingest_command.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    if args.command == "ingest":
        ingest(args.manifest)
