import pytest

from hr_assist.corpus import Chunk, ManifestEntry, ManifestError, load_manifest
from hr_assist.ingestion import build_chunks

TABLE_3_1_ROWS = [
    "|Less than 3 years|27|8|35|262.5|",
    "|3 years or more, less than 5 years|28|8|36|270.0|",
    "|5 years or more|29|8|37|277.5|",
]


@pytest.fixture(scope="module")
def corpus_chunks() -> list[Chunk]:
    return build_chunks(load_manifest())


def manifest_entry(document_id: str) -> ManifestEntry:
    [entry] = [e for e in load_manifest() if e.document_id == document_id]
    return entry


def chunk_for_section(chunks: list[Chunk], document_id: str, section_number: str) -> Chunk:
    [chunk] = [
        c
        for c in chunks
        if c.metadata.document_id == document_id and c.metadata.section_number == section_number
    ]
    return chunk


def test_section_3_1_of_the_leave_standard_is_one_chunk_holding_table_3_1(
    corpus_chunks: list[Chunk],
) -> None:
    chunk = chunk_for_section(corpus_chunks, "NDS-HR-LAS-002", "3.1")

    for row in TABLE_3_1_ROWS:
        assert row in chunk.text.replace("**", "")
    assert chunk.metadata.section_title == "Entitlement"
    assert chunk.metadata.section_path == ["3 Annual leave", "3.1 Entitlement"]
    assert (chunk.metadata.page_start, chunk.metadata.page_end) == (5, 5)


def test_section_6_1_of_the_handbook_holds_table_6_1_intact(corpus_chunks: list[Chunk]) -> None:
    chunk = chunk_for_section(corpus_chunks, "NDS-HR-HB-001", "6.1")
    text = chunk.text.replace("**", "")

    assert "Table 6.1 — Annual leave entitlement for full-time employees" in text
    for row in [
        "|Less than 3 years|27|8|35|",
        "|3 years or more, but less than 5 years|28|8|36|",
        "|5 years or more|29|8|37|",
    ]:
        assert row in text


def test_chunks_carry_document_facts_from_the_manifest(corpus_chunks: list[Chunk]) -> None:
    metadata = chunk_for_section(corpus_chunks, "NDS-HR-LAS-002", "3.1").metadata

    assert metadata.document_version == "v1.2"
    assert metadata.title == "Leave and Absence Standard"
    assert metadata.document_kind == "policy_document"
    assert metadata.status == "current"
    assert str(metadata.effective_from) == "2026-10-01"
    assert metadata.effective_to is None
    assert metadata.chunking_version == "structure_v1"


def test_embedded_text_starts_with_the_document_and_section_header(
    corpus_chunks: list[Chunk],
) -> None:
    chunk = chunk_for_section(corpus_chunks, "NDS-HR-LAS-002", "3.1")

    assert chunk.text.startswith(
        "Leave and Absence Standard (NDS-HR-LAS-002 v1.2, current, effective 2026-10-01)\n"
        "3 Annual leave > 3.1 Entitlement\n"
    )


def test_running_header_and_footer_are_removed(corpus_chunks: list[Chunk]) -> None:
    for chunk in corpus_chunks:
        assert "|  NDS-HR-LAS-002  |" not in chunk.text
        assert "Northstar Digital Services Ltd.**" not in chunk.text
        assert "Page 5 of 15" not in chunk.text


def test_a_section_crossing_a_page_break_spans_both_pages(corpus_chunks: list[Chunk]) -> None:
    company_sick_pay = chunk_for_section(corpus_chunks, "NDS-HR-HB-001", "7.5").metadata

    assert (company_sick_pay.page_start, company_sick_pay.page_end) == (28, 29)


def test_each_part_of_a_split_section_carries_its_own_pages(corpus_chunks: list[Chunk]) -> None:
    joiners_and_leavers = [
        c.metadata
        for c in corpus_chunks
        if c.metadata.document_id == "NDS-HR-LAS-002" and c.metadata.section_number == "3.5"
    ]

    assert [(m.page_start, m.page_end) for m in joiners_and_leavers] == [(6, 7), (7, 7)]


def test_a_manifest_version_that_disagrees_with_the_pdf_header_fails_ingestion() -> None:
    entry = manifest_entry("NDS-HR-LV-006").model_copy(update={"document_version": "v1.1"})

    with pytest.raises(ManifestError, match=r"NDS-HR-LV-006 v1\.1.*v1\.0"):
        build_chunks([entry])


@pytest.mark.parametrize(
    ("document_id", "contents_pages"),
    [
        ("NDS-HR-HB-001", range(4, 11)),
        ("NDS-HR-LAS-002", [3]),
        ("NDS-FIN-EXP-003", [3]),
        ("NDS-SEC-ITG-004", [3]),
        ("NDS-HR-HFW-005", [3]),
    ],
)
def test_contents_pages_produce_no_chunks(
    corpus_chunks: list[Chunk], document_id: str, contents_pages: range | list[int]
) -> None:
    chunks = [c for c in corpus_chunks if c.metadata.document_id == document_id]

    assert chunks
    for chunk in chunks:
        assert chunk.metadata.page_start not in contents_pages
        assert ".  .  .  .  ." not in chunk.text


def test_superseded_policy_chunks_carry_their_status_and_effective_period(
    corpus_chunks: list[Chunk],
) -> None:
    chunks = [c for c in corpus_chunks if c.metadata.document_id == "NDS-HR-LV-006"]

    assert chunks
    for chunk in chunks:
        assert chunk.metadata.status == "superseded"
        assert str(chunk.metadata.effective_from) == "2025-01-01"
        assert str(chunk.metadata.effective_to) == "2026-09-30"
        assert chunk.text.startswith(
            "Leave Policy (NDS-HR-LV-006 v1.0, superseded, effective 2025-01-01 to 2026-09-30)\n"
        )


def test_the_superseded_policy_header_and_footer_are_removed(corpus_chunks: list[Chunk]) -> None:
    for chunk in corpus_chunks:
        if chunk.metadata.document_id == "NDS-HR-LV-006":
            assert "SUPERSEDED — NOT FOR CURRENT POLICY DECISIONS" not in chunk.text
            assert "Internal (ARCHIVED)" not in chunk.text
            assert "ARCHIVED Leave Policy  |" not in chunk.text


def test_an_oversized_section_is_split_without_cutting_its_table(
    corpus_chunks: list[Chunk],
) -> None:
    parts = [
        c
        for c in corpus_chunks
        if c.metadata.document_id == "NDS-HR-HB-001" and c.metadata.section_number == "6.3"
    ]
    table_rows = [
        "|Working pattern|FTE|",
        "|0.6|157.5|6 days x 7.5 = 45.0|112.5|",
        "|0.8|210.0|6 days x 7.5 = 45.0|165.0|",
        "|0.8|210.0|8 days x 6 = 48.0|162.0|",
    ]

    assert len(parts) > 1
    [holding_table] = [c for c in parts if "Table 6.3" in c.text]
    for row in table_rows:
        assert row in holding_table.text.replace("**", "")
    for part in parts:
        assert all(line.endswith("|") for line in part.body.splitlines() if line.startswith("|"))


def test_no_table_is_split_across_chunks(corpus_chunks: list[Chunk]) -> None:
    for chunk in corpus_chunks:
        lines = chunk.body.splitlines()
        table_starts = [
            i
            for i, line in enumerate(lines)
            if line.startswith("|") and (i == 0 or not lines[i - 1].startswith("|"))
        ]
        for start in table_starts:
            assert lines[start + 1].startswith("|---"), (
                f"{chunk.metadata.document_id} §{chunk.metadata.section_number} "
                f"starts mid-table: {lines[start][:60]}"
            )
