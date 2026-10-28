"""Build the generation eval's golden questions: each question with its gold chunks.

Run from the repo root:  uv run --project backend python evals/generation/build_goldens.py

Takes the same questions as the retriever goldens, and for each one finds the chunks of the
sections its supporting passages cite, by Document ID and section number (or slide), in chunks
built offline the way ingestion builds them. The chunks are frozen into goldens_v1.jsonl, so the
generation eval hands the Answerer the same evidence on every run. See ADR 0006.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from hr_assist.corpus import Chunk
from hr_assist.corpus.manifest import load_manifest
from hr_assist.ingestion import STRATEGIES, build_chunks
from hr_assist.settings import REPO_ROOT

EVAL_QUESTIONS = REPO_ROOT / "evals" / "eval_questions.json"
RETRIEVAL_GOLDENS = REPO_ROOT / "evals" / "retrieval" / "goldens_v1.jsonl"
OUTPUT = Path(__file__).resolve().parent / "goldens_v1.jsonl"

# A passage's section starts with a section number ("6.3, Table 6.3") or a slide ("Slide 6 ...").
_SECTION_NUMBER = re.compile(r"\d+(?:\.\d+)*")
_SLIDE = re.compile(r"Slide\s+(\d+)", re.IGNORECASE)


def gold_chunks(passage: dict, chunks: list[Chunk]) -> list[Chunk]:
    """Every chunk of the passage's section, subsections included, in document order."""
    section = passage["section"].strip()
    of_document = [
        c for c in chunks if c.metadata.document_id == passage["document_id"]
    ]
    if slide := _SLIDE.match(section):
        return [c for c in of_document if c.metadata.slide == int(slide.group(1))]
    if number := _SECTION_NUMBER.match(section):
        prefix = number.group(0)
        return [
            c
            for c in of_document
            if c.metadata.section_number
            and (
                c.metadata.section_number == prefix
                or c.metadata.section_number.startswith(f"{prefix}.")
            )
        ]
    return []


def build_goldens(chunking_version: str) -> tuple[list[dict], list[str]]:
    """The goldens, and a line for each passage whose section names no chunk."""
    questions = {
        q["question_id"]: q
        for q in json.loads(EVAL_QUESTIONS.read_text(encoding="utf-8"))
    }
    # The same questions as the retriever goldens, so the two levels line up question by question.
    question_ids = [
        json.loads(line)["additional_metadata"]["question_id"]
        for line in RETRIEVAL_GOLDENS.read_text().splitlines()
    ]
    chunks = build_chunks(load_manifest(), STRATEGIES[chunking_version]())

    goldens, unresolved = [], []
    for question_id in question_ids:
        question = questions[question_id]
        selected: dict[str, Chunk] = {}
        unresolved_here = []
        for passage in question["supporting_passages"]:
            found = gold_chunks(passage, chunks)
            if not found:
                unresolved_here.append(f"{passage['document_id']} {passage['section']}")
            selected.update((c.id, c) for c in found if c.id not in selected)
        if not selected:
            sys.exit(f"{question_id}: no chunk found for any supporting passage")
        unresolved += [f"{question_id}: {u}" for u in unresolved_here]
        goldens.append(
            {
                "input": question["question"],
                "expected_output": question["gold_answer"],
                "context": [p["quote"] for p in question["supporting_passages"]],
                "retrieval_context": [c.text for c in selected.values()],
                "additional_metadata": {
                    "question_id": question_id,
                    "category": question["category"],
                    "difficulty": question["difficulty"],
                    "source_document_ids": question["source_document_ids"],
                    "source_sections": question["source_sections"],
                    "as_of_date": question["as_of_date"],
                    "must_mention": question["must_mention"],
                    "must_not_claim": question["must_not_claim"],
                    "chunking_version": chunking_version,
                    "unresolved_passages": unresolved_here,
                    # The fake retriever hands the Answerer these, metadata included.
                    "chunks": [c.model_dump(mode="json") for c in selected.values()],
                },
            }
        )
    return goldens, unresolved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chunking", default="chunking_v2", choices=sorted(STRATEGIES))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    goldens, unresolved = build_goldens(args.chunking)
    args.output.write_text(
        "".join(
            json.dumps(g, ensure_ascii=False, separators=(",", ":")) + "\n"
            for g in goldens
        )
    )
    # A pretty-printed copy for reading; the evals load the JSONL file.
    args.output.with_suffix(".json").write_text(
        json.dumps(goldens, indent=2, ensure_ascii=False) + "\n"
    )
    counts: dict[int, int] = {}
    for golden in goldens:
        n = len(golden["retrieval_context"])
        counts[n] = counts.get(n, 0) + 1
    for n, count in sorted(counts.items()):
        print(f"{count} questions with {n} gold chunk{'s' if n > 1 else ''}")
    for line in unresolved:
        print(f"No chunk for passage {line}")
    written = args.output.resolve().relative_to(REPO_ROOT)
    print(
        f"Wrote {len(goldens)} generation goldens ({args.chunking}) to {written}, "
        "and a readable copy in .json"
    )


if __name__ == "__main__":
    main()
