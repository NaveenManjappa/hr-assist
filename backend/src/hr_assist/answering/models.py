from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from hr_assist.corpus import DocumentStatus

ResponseType = Literal["answer", "clarification", "abstention", "refusal"]


class AssistantReply(BaseModel):
    """The structured output the chat model must return."""

    response_type: ResponseType = Field(description="The kind of reply, chosen by the rules.")
    message: str = Field(description="The reply shown to the Employee, in plain English.")
    cited_sources: list[int] = Field(
        default_factory=list,
        description="Numbers of the sources the message relies on. Empty unless answering.",
    )


class GeneratedReply(BaseModel):
    reply: AssistantReply
    token_usage: dict[str, int]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    as_of_date: date | None = None

    @model_validator(mode="after")
    def _ends_with_a_question(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("the last message must be the Employee's question")
        return self


class Citation(BaseModel):
    document_id: str
    document_version: str
    title: str
    section: str
    page_start: int
    page_end: int
    snippet: str
    status: DocumentStatus


class ChatResponse(BaseModel):
    response_type: ResponseType
    message: str
    citations: list[Citation]
