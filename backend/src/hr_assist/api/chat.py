from fastapi import APIRouter, Request

from hr_assist.answering import Answerer, ChatRequest, ChatResponse

router = APIRouter()


@router.post("/api/chat")
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    answerer: Answerer = request.app.state.answerer
    return await answerer.answer(body)
