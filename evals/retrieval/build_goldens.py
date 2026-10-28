"""Build the retriever eval's golden questions from the eval questions file.

Run from the repo root:  python evals/retrieval/build_goldens.py

Reads evals/eval_questions.json, checks it, and writes goldens_v1.jsonl in the shape DeepEval
loads as Goldens. Only the standard library is used, so it runs with any Python 3.
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_QUESTIONS = REPO_ROOT / "evals" / "eval_questions.json"
MANIFEST = REPO_ROOT / "data" / "manifest.yaml"
OUTPUT = Path(__file__).resolve().parent / "goldens_v1.jsonl"

# Answerable categories that don't test the retriever as it is today, with the reason.
EXCLUDED_CATEGORIES = {
    "versioning_temporal": "needs an as-of-date filter, which retrieval doesn't have yet",
    "privacy_injection_robustness": (
        "cites NDS-TEST-INJ-010, an injected memo that isn't in the Corpus, so it tests the "
        "Answerer's resistance to it, not retrieval"
    ),
}


def build_goldens() -> list[dict]:
    text = EVAL_QUESTIONS.read_text(encoding="utf-8")
    # The project writes "section 6.1", never the section sign.
    if "\u00a7" in text:
        sys.exit(f"{EVAL_QUESTIONS.name} contains the section sign; write 'section' instead")
    questions = json.loads(text)
    ids = [q["question_id"] for q in questions]
    if len(ids) != len(set(ids)):
        sys.exit(f"Duplicate question IDs in {EVAL_QUESTIONS.name}")

    known_documents = set(re.findall(r"document_id:\s*(\S+)", MANIFEST.read_text()))
    goldens = []
    for question in sorted(questions, key=lambda q: q["question_id"]):
        question_id = question["question_id"]
        if (
            question["expected_behaviour"] != "answer"
            or question["category"] in EXCLUDED_CATEGORIES
        ):
            continue
        if not question["gold_answer"] or not question["supporting_passages"]:
            sys.exit(f"{question_id}: no gold answer or supporting passages")
        unknown = set(question["source_document_ids"]) - known_documents
        if unknown:
            sys.exit(f"{question_id}: unknown source documents {sorted(unknown)}")
        goldens.append(
            {
                "input": question["question"],
                "expected_output": question["gold_answer"],
                "context": [passage["quote"] for passage in question["supporting_passages"]],
                "additional_metadata": {
                    "question_id": question_id,
                    "category": question["category"],
                    "difficulty": question["difficulty"],
                    "source_document_ids": question["source_document_ids"],
                    "source_sections": question["source_sections"],
                },
            }
        )
    return goldens


def main() -> None:
    goldens = build_goldens()
    OUTPUT.write_text(
        "".join(json.dumps(g, ensure_ascii=False, separators=(",", ":")) + "\n" for g in goldens)
    )
    # A pretty-printed copy for reading; the evals load the JSONL file.
    OUTPUT.with_suffix(".json").write_text(json.dumps(goldens, indent=2, ensure_ascii=False) + "\n")
    categories: dict[str, int] = {}
    for golden in goldens:
        category = golden["additional_metadata"]["category"]
        categories[category] = categories.get(category, 0) + 1
    for category, count in categories.items():
        print(f"{category}: {count}")
    written = OUTPUT.relative_to(REPO_ROOT)
    print(f"Wrote {len(goldens)} retrieval goldens to {written}, and a readable copy in .json")


if __name__ == "__main__":
    main()
