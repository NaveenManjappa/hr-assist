from datetime import date
from importlib.resources import files

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from hr_assist.answering.models import ChatMessage
from hr_assist.corpus import Chunk, ChunkMetadata

PROMPT_VERSION = "v7"

_KIND_LABELS = {
    "policy_document": "Policy Document",
    "summary_deck": "Summary Deck",
    "test_fixture": "Test Fixture",
}

# The system prompt lives in prompts/answer.md, read from the installed package so it works from
# any working folder. Bump PROMPT_VERSION whenever you change it.
_SYSTEM = (
    files("hr_assist").joinpath("prompts", "answer.md").read_text(encoding="utf-8").rstrip("\n")
)


def build_prompt(
    as_of_date: date, chunks: list[Chunk], history: list[ChatMessage]
) -> list[BaseMessage]:
    """The system prompt with numbered sources, followed by the recent conversation."""
    sources = "\n\n".join(_format_source(n, chunk) for n, chunk in enumerate(chunks, start=1))
    system = _SYSTEM.format(as_of_date=as_of_date.isoformat(), sources=sources or "(none found)")
    turns: list[BaseMessage] = [
        HumanMessage(m.content) if m.role == "user" else AIMessage(m.content) for m in history
    ]
    return [SystemMessage(system), *turns]


def _format_source(number: int, chunk: Chunk) -> str:
    m = chunk.metadata
    period = f"effective {m.effective_from.isoformat()}"
    period += f" to {m.effective_to.isoformat()}" if m.effective_to else " (no end date)"
    return (
        f"[{number}] {m.title} ({m.document_id} {m.document_version}), "
        f"{_KIND_LABELS[m.document_kind]}, {m.status}, {period}\n"
        f"{_location(m)}\n"
        f"{chunk.body}"
    )


def _location(m: ChunkMetadata) -> str:
    if m.slide is not None:
        return f"Slide {m.slide}: {m.section_title}"
    pages = f"p.{m.page_start}" if m.page_start == m.page_end else f"pp.{m.page_start}-{m.page_end}"
    return f"Section: {' > '.join(m.section_path)}, {pages}"
