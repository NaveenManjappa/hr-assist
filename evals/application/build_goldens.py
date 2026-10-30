"""Build the application eval's golden questions and Clarification follow-up conversations.

Run from the repo root:  uv run --project backend python evals/application/build_goldens.py

Takes a stratified sample of the pipeline goldens, 3 Answer questions per category and every
question expecting another Response Type, plus the questions about an injected memo, which the
pipeline leaves out. Those four get hand-written expected outputs (expected_output_overrides.json),
because their gold answers name a Test Fixture the app has never seen. Each Clarification question
also becomes a conversation that ends with the Employee's reply (clarification_follow_ups.json).
See ADR 0006.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from hr_assist.corpus.manifest import load_manifest
from hr_assist.settings import REPO_ROOT

HERE = Path(__file__).resolve().parent
EVAL_QUESTIONS = REPO_ROOT / "evals" / "eval_questions.json"
PIPELINE_BUILD = REPO_ROOT / "evals" / "pipeline" / "build_goldens.py"
PIPELINE_GOLDENS = REPO_ROOT / "evals" / "pipeline" / "goldens_v1.jsonl"
OVERRIDES = HERE / "expected_output_overrides.json"
FOLLOW_UPS = HERE / "clarification_follow_ups.json"
OUTPUT = HERE / "goldens_v1.jsonl"
CONVERSATIONS_OUTPUT = HERE / "conversations_v1.jsonl"

# The pipeline builder's citation targets and Response Types, so the levels can't drift apart. It
# is loaded by path because both scripts are called build_goldens.
_spec = importlib.util.spec_from_file_location("pipeline_build_goldens", PIPELINE_BUILD)
assert _spec and _spec.loader
pipeline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pipeline)

INJECTED_MEMO = "NDS-TEST-INJ-010"
ANSWERS_PER_CATEGORY = 3
DIFFICULTY_ORDER = {"hard": 0, "medium": 1, "easy": 2}
# Expected size of each selection group; the build fails if the source data changes them.
GROUP_SIZES = {"answer": 21, "clarification": 7, "abstention": 8, "refusal": 5, "injected_memo": 4}
# Words that would mean an override still points at the Test Fixture.
FIXTURE_WORDS = (INJECTED_MEMO, "fixture", "sample")


def load_json_checked(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    # The project writes "section 6.1", never the section sign.
    if "§" in text:
        sys.exit(f"{path.name} contains the section sign; write 'section' instead")
    return json.loads(text)


def select(pipeline_goldens: list[dict]) -> dict[str, list[dict]]:
    """The pipeline goldens in each selection group, by a fixed rule."""
    groups: dict[str, list[dict]] = {}
    by_category: dict[str, list[dict]] = {}
    for golden in pipeline_goldens:
        meta = golden["additional_metadata"]
        if meta["expected_response_type"] == "answer":
            by_category.setdefault(meta["category"], []).append(golden)
        else:
            groups.setdefault(meta["expected_response_type"], []).append(golden)
    # Hardest first within each category, then by question ID.
    groups["answer"] = [
        golden
        for category in sorted(by_category)
        for golden in sorted(
            by_category[category],
            key=lambda g: (
                DIFFICULTY_ORDER[g["additional_metadata"]["difficulty"]],
                g["additional_metadata"]["question_id"],
            ),
        )[:ANSWERS_PER_CATEGORY]
    ]
    return groups


def injected_memo_golden(question: dict, override: dict, statuses: dict[str, str]) -> dict:
    """A pipeline-shaped golden for a question about the injected memo, with its override."""
    targets = []
    unreachable = []
    for passage in question["supporting_passages"]:
        if passage["document_id"] == INJECTED_MEMO:
            continue
        target = pipeline.citation_target(passage)
        if target and statuses[passage["document_id"]] == "current":
            if target not in targets:
                targets.append(target)
        else:
            unreachable.append(f"{passage['document_id']} {passage['section']}")
    response_type = pipeline.RESPONSE_TYPES[question["expected_behaviour"]]
    if response_type == "answer" and not targets:
        sys.exit(f"{question['question_id']}: no supporting passage can be cited")
    return {
        "input": question["question"],
        "expected_output": override["expected_output"],
        "context": [p["quote"] for p in question["supporting_passages"]],
        "additional_metadata": {
            "question_id": question["question_id"],
            "category": question["category"],
            "difficulty": question["difficulty"],
            "expected_response_type": response_type,
            "as_of_date": question["as_of_date"],
            "source_document_ids": question["source_document_ids"],
            "source_sections": question["source_sections"],
            "must_mention": question["must_mention"],
            "must_not_claim": question["must_not_claim"],
            "citation_targets": targets,
            "unreachable_passages": unreachable,
            "expected_output_override_reason": override["reason"],
        },
    }


def conversation(follow_up: dict, question: dict, statuses: dict[str, str]) -> dict:
    """The Clarification question, a frozen Clarification, and the Employee's reply."""
    question_id = follow_up["question_id"]
    targets = []
    for source in follow_up["sources"]:
        if source["document_id"] not in statuses:
            sys.exit(f"{question_id}: unknown source document {source['document_id']}")
        target = pipeline.citation_target(source)
        if not target or statuses[source["document_id"]] != "current":
            sys.exit(f"{question_id}: follow-up source {source} can't be cited")
        if target not in targets:
            targets.append(target)
    return {
        "scenario": (
            f"The Employee asks a question HR Assist can't answer without knowing "
            f"{follow_up['missing_detail']}, is asked for it, and replies."
        ),
        "turns": [
            {"role": "user", "content": question["question"]},
            {"role": "assistant", "content": question["expected_answer"]},
            {"role": "user", "content": follow_up["follow_up"]},
        ],
        "expected_outcome": follow_up["expected_outcome"],
        "additional_metadata": {
            "question_id": question_id,
            "category": question["category"],
            "expected_response_type": "answer",
            "as_of_date": follow_up["as_of_date"],
            "sources": follow_up["sources"],
            "citation_targets": targets,
        },
    }


def build_goldens() -> tuple[dict[str, list[dict]], list[dict]]:
    """The single-turn goldens by selection group, and the conversations."""
    questions_list = load_json_checked(EVAL_QUESTIONS)
    ids = [q["question_id"] for q in questions_list]
    if len(ids) != len(set(ids)):
        sys.exit(f"Duplicate question IDs in {EVAL_QUESTIONS.name}")
    questions = {q["question_id"]: q for q in questions_list}
    statuses = {entry.document_id: entry.status for entry in load_manifest()}
    pipeline_goldens = [json.loads(line) for line in PIPELINE_GOLDENS.read_text().splitlines()]

    groups = select(pipeline_goldens)

    overrides = load_json_checked(OVERRIDES)
    memo_ids = sorted(
        q["question_id"] for q in questions_list if INJECTED_MEMO in q["source_document_ids"]
    )
    if sorted(overrides) != memo_ids:
        sys.exit(
            f"{OVERRIDES.name} must override exactly the {INJECTED_MEMO} questions: {memo_ids}"
        )
    groups["injected_memo"] = []
    for question_id in memo_ids:
        override = overrides[question_id]
        found = [w for w in FIXTURE_WORDS if w.lower() in override["expected_output"].lower()]
        if found:
            sys.exit(f"{question_id}: override still mentions {found}")
        unknown = (
            set(questions[question_id]["source_document_ids"]) - statuses.keys() - {INJECTED_MEMO}
        )
        if unknown:
            sys.exit(f"{question_id}: unknown source documents {sorted(unknown)}")
        groups["injected_memo"].append(
            injected_memo_golden(questions[question_id], override, statuses)
        )

    sizes = {group: len(groups.get(group, [])) for group in GROUP_SIZES}
    if sizes != GROUP_SIZES:
        sys.exit(f"Selection group sizes {sizes}, expected {GROUP_SIZES}")
    for group, goldens in groups.items():
        for golden in goldens:
            golden["additional_metadata"]["selection_group"] = group
            # Kept for readers of the results; the judge's steps are the same for every question.
            golden["additional_metadata"]["evaluation_rubric"] = questions[
                golden["additional_metadata"]["question_id"]
            ]["evaluation_rubric"]
            if not golden["expected_output"].strip():
                sys.exit(f"{golden['additional_metadata']['question_id']}: no expected output")
            meta = golden["additional_metadata"]
            if meta["expected_response_type"] == "answer" and not meta["citation_targets"]:
                sys.exit(f"{meta['question_id']}: an Answer question with no citation target")

    follow_ups = load_json_checked(FOLLOW_UPS)
    clarification_ids = sorted(
        g["additional_metadata"]["question_id"] for g in groups["clarification"]
    )
    if sorted(f["question_id"] for f in follow_ups) != clarification_ids:
        sys.exit(
            f"{FOLLOW_UPS.name} needs one follow-up per Clarification question: {clarification_ids}"
        )
    conversations = [
        conversation(f, questions[f["question_id"]], statuses)
        for f in sorted(follow_ups, key=lambda f: f["question_id"])
    ]
    for c in conversations:
        if not c["expected_outcome"].strip() or not c["turns"][-1]["content"].strip():
            sys.exit(
                f"{c['additional_metadata']['question_id']}: empty follow-up or expected outcome"
            )
    return groups, conversations


def write(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records)
    )
    # A pretty-printed copy for reading; the evals load the JSONL file.
    path.with_suffix(".json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--conversations-output", type=Path, default=CONVERSATIONS_OUTPUT)
    args = parser.parse_args()

    groups, conversations = build_goldens()
    goldens = sorted(
        (g for group in groups.values() for g in group),
        key=lambda g: g["additional_metadata"]["question_id"],
    )
    write(args.output, goldens)
    write(args.conversations_output, conversations)
    for group in GROUP_SIZES:
        chosen = ", ".join(g["additional_metadata"]["question_id"][-3:] for g in groups[group])
        print(f"{group}: {len(groups[group])} ({chosen})")
    for output, count, kind in (
        (args.output, len(goldens), "application goldens"),
        (args.conversations_output, len(conversations), "follow-up conversations"),
    ):
        written = output.resolve().relative_to(REPO_ROOT)
        print(f"Wrote {count} {kind} to {written}, and a readable copy in .json")


if __name__ == "__main__":
    main()
