import pytest

from hr_assist.corpus import Chunk, load_manifest
from hr_assist.ingestion import build_chunks

TABLE_3_1_ROWS = [
    "|Less than 3 years|27|8|35|262.5|",
    "|3 years or more, less than 5 years|28|8|36|270.0|",
    "|5 years or more|29|8|37|277.5|",
]


@pytest.fixture(scope="module")
def corpus_chunks() -> list[Chunk]:
    return build_chunks(load_manifest())


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
    joiners_and_leavers = [
        c.metadata
        for c in corpus_chunks
        if c.metadata.document_id == "NDS-HR-LAS-002" and c.metadata.section_number == "3.5"
    ]

    assert joiners_and_leavers
    assert {(m.page_start, m.page_end) for m in joiners_and_leavers} == {(6, 7)}
