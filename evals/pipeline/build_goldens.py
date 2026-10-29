"""Build the pipeline eval's golden questions: each question with the sections it should cite.

Run from the repo root:  uv run --project backend python evals/pipeline/build_goldens.py

Takes the retriever goldens' Answer questions, so the levels line up question by question, and
adds the questions expecting a Clarification, Abstention or Refusal. Each Answer question gets
citation targets, one per supporting passage, that the pipeline eval matches its citations
against. Nothing is retrieved here: the pipeline retrieves live. See ADR 0006.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from hr_assist.corpus.manifest import load_manifest
from hr_assist.settings import REPO_ROOT

EVAL_QUESTIONS = REPO_ROOT / "evals" / "eval_questions.json"
RETRIEVAL_GOLDENS = REPO_ROOT / "evals" / "retrieval" / "goldens_v1.jsonl"
OUTPUT = Path(__file__).resolve().parent / "goldens_v1.jsonl"

# The eval questions file's expected behaviour, as the Answerer's Response Type.
RESPONSE_TYPES = {
    "answer": "answer",
    "clarify": "clarification",
    "abstain": "abstention",
    "refuse": "refusal",
}

# Questions citing these documents are left out, with the reason.
EXCLUDED_DOCUMENTS = {
    "NDS-TEST-INJ-010": (
        "an injected memo that isn't in the Corpus, so the retriever never returns it; "
        "the application level tests it"
    ),
}

# The same patterns as the generation goldens' gold_chunks: a section starts with a section
# number ("6.3, Table 6.3") or a slide ("Slide 6 ...").
_SECTION_NUMBER = re.compile(r"\d+(?:\.\d+)*")
_SLIDE = re.compile(r"Slide\s+(\d+)", re.IGNORECASE)


def citation_target(passage: dict) -> dict | None:
    """The Document ID with the passage's section number or slide, or None if it names neither."""
    section = passage["section"].strip()
    if slide := _SLIDE.match(section):
        return {"document_id": passage["document_id"], "slide": int(slide.group(1))}
    if number := _SECTION_NUMBER.match(section):
        return {"document_id": passage["document_id"], "section": number.group(0)}
    return None


def build_goldens() -> tuple[list[dict], list[str]]:
    """The goldens, and a line for each passage that can't be cited."""
    text = EVAL_QUESTIONS.read_text(encoding="utf-8")
    # The project writes "section 6.1", never the section sign.
    if "§" in text:
        sys.exit(f"{EVAL_QUESTIONS.name} contains the section sign; write 'section' instead")
    questions = json.loads(text)
    ids = [q["question_id"] for q in questions]
    if len(ids) != len(set(ids)):
        sys.exit(f"Duplicate question IDs in {EVAL_QUESTIONS.name}")

    statuses = {entry.document_id: entry.status for entry in load_manifest()}
    answer_ids = {
        json.loads(line)["additional_metadata"]["question_id"]
        for line in RETRIEVAL_GOLDENS.read_text().splitlines()
    }

    goldens, unreachable = [], []
    for question in sorted(questions, key=lambda q: q["question_id"]):
        question_id = question["question_id"]
        expects_answer = question["expected_behaviour"] == "answer"
        if expects_answer and question_id not in answer_ids:
            continue
        if set(question["source_document_ids"]) & EXCLUDED_DOCUMENTS.keys():
            continue
        unknown = set(question["source_document_ids"]) - statuses.keys()
        if unknown:
            sys.exit(f"{question_id}: unknown source documents {sorted(unknown)}")

        targets, unreachable_here = [], []
        if expects_answer:
            if not question["gold_answer"] or not question["supporting_passages"]:
                sys.exit(f"{question_id}: no gold answer or supporting passages")
            for passage in question["supporting_passages"]:
                target = citation_target(passage)
                # Retrieval searches only current documents (ADR 0007).
                if target and statuses[passage["document_id"]] == "current":
                    if target not in targets:
                        targets.append(target)
                else:
                    unreachable_here.append(f"{passage['document_id']} {passage['section']}")
            if not targets:
                sys.exit(f"{question_id}: no supporting passage can be cited")
        unreachable += [f"{question_id}: {u}" for u in unreachable_here]

        goldens.append(
            {
                "input": question["question"],
                "expected_output": question["gold_answer"],
                "context": [p["quote"] for p in question["supporting_passages"]],
                "additional_metadata": {
                    "question_id": question_id,
                    "category": question["category"],
                    "difficulty": question["difficulty"],
                    "expected_response_type": RESPONSE_TYPES[question["expected_behaviour"]],
                    "as_of_date": question["as_of_date"],
                    "source_document_ids": question["source_document_ids"],
                    "source_sections": question["source_sections"],
                    "must_mention": question["must_mention"],
                    "must_not_claim": question["must_not_claim"],
                    "citation_targets": targets,
                    "unreachable_passages": unreachable_here,
                },
            }
        )
    if len(answer_ids) != sum(
        g["additional_metadata"]["expected_response_type"] == "answer" for g in goldens
    ):
        sys.exit(f"Not every Answer question in {RETRIEVAL_GOLDENS.name} was kept")
    return goldens, unreachable


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    goldens, unreachable = build_goldens()
    args.output.write_text(
        "".join(json.dumps(g, ensure_ascii=False, separators=(",", ":")) + "\n" for g in goldens)
    )
    # A pretty-printed copy for reading; the evals load the JSONL file.
    args.output.with_suffix(".json").write_text(
        json.dumps(goldens, indent=2, ensure_ascii=False) + "\n"
    )
    counts: dict[str, int] = {}
    for golden in goldens:
        response_type = golden["additional_metadata"]["expected_response_type"]
        counts[response_type] = counts.get(response_type, 0) + 1
    for response_type, count in counts.items():
        print(f"{response_type}: {count}")
    for line in unreachable:
        print(f"Can't be cited: passage {line}")
    written = args.output.resolve().relative_to(REPO_ROOT)
    print(f"Wrote {len(goldens)} pipeline goldens to {written}, and a readable copy in .json")


if __name__ == "__main__":
    main()
