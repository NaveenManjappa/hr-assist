"""Build the retriever eval's golden questions from the question and gold answer files.

Run from the repo root:  python evals/retrieval/build_goldens.py

Joins 07_RAG_Evaluation_Questions.csv to 08_RAG_Evaluation_Gold_Answers.jsonl by question_id,
checks they agree, and writes goldens_v1.jsonl in the shape DeepEval loads as Goldens. Only
the standard library is used, so it runs with any Python 3.
"""

import csv
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_CSV = REPO_ROOT / "evals" / "07_RAG_Evaluation_Questions.csv"
GOLD_ANSWERS_JSONL = REPO_ROOT / "evals" / "08_RAG_Evaluation_Gold_Answers.jsonl"
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
# Fields the questions CSV shares with the gold answers file; they must agree.
SHARED_FIELDS = [
    "question",
    "category",
    "difficulty",
    "expected_behaviour",
    "expected_answer",
    "source_sections",
]


def build_goldens() -> list[dict]:
    with QUESTIONS_CSV.open(encoding="utf-8-sig", newline="") as file:
        questions = {row["question_id"]: row for row in csv.DictReader(file)}
    gold = {
        record["question_id"]: record
        for record in map(json.loads, GOLD_ANSWERS_JSONL.read_text().splitlines())
    }
    if questions.keys() != gold.keys():
        sys.exit(
            f"Question IDs differ: only in questions {sorted(questions.keys() - gold.keys())}, "
            f"only in gold answers {sorted(gold.keys() - questions.keys())}"
        )

    known_documents = set(re.findall(r"document_id:\s*(\S+)", MANIFEST.read_text()))
    goldens = []
    for question_id, question in sorted(questions.items()):
        answer = gold[question_id]
        for field in SHARED_FIELDS:
            if question[field] != answer[field]:
                sys.exit(f"{question_id}: {field} differs between the two files")
        if answer["expected_behaviour"] != "answer" or answer["category"] in EXCLUDED_CATEGORIES:
            continue
        if not answer["gold_answer"] or not answer["supporting_passages"]:
            sys.exit(f"{question_id}: no gold answer or supporting passages")
        unknown = set(answer["source_document_ids"]) - known_documents
        if unknown:
            sys.exit(f"{question_id}: unknown source documents {sorted(unknown)}")
        goldens.append(
            {
                "input": answer["question"],
                "expected_output": answer["gold_answer"],
                "context": [passage["quote"] for passage in answer["supporting_passages"]],
                "additional_metadata": {
                    "question_id": question_id,
                    "category": answer["category"],
                    "difficulty": answer["difficulty"],
                    "source_document_ids": answer["source_document_ids"],
                    # The source files write "§6.1"; spell it out as the rest of the project does.
                    "source_sections": answer["source_sections"].replace("§", "section "),
                },
            }
        )
    return goldens


def main() -> None:
    goldens = build_goldens()
    OUTPUT.write_text(
        "".join(json.dumps(g, ensure_ascii=False, separators=(",", ":")) + "\n" for g in goldens)
    )
    categories: dict[str, int] = {}
    for golden in goldens:
        category = golden["additional_metadata"]["category"]
        categories[category] = categories.get(category, 0) + 1
    for category, count in categories.items():
        print(f"{category}: {count}")
    print(f"Wrote {len(goldens)} retrieval goldens to {OUTPUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
