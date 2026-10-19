from fastapi import APIRouter, Request

from hr_assist.answering import Answerer, ChatRequest, ChatResponse
from hr_assist.api.rate_limit import RateLimiter
from hr_assist.settings import Settings

router = APIRouter()


@router.post("/api/chat")
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    # Checked here, after FastAPI has validated the body, so invalid requests don't count.
    rate_limiter: RateLimiter = request.app.state.rate_limiter
    rate_limiter.admit(client_ip(request))
    answerer: Answerer = request.app.state.answerer
    return await answerer.answer(body)


def client_ip(request: Request) -> str:
    """Reads the client from X-Forwarded-For, counting the trusted proxy hops from the right.

    Each proxy appends the address it received the request from, so only the rightmost
    entries are trustworthy. Anything further left was sent by the client and is ignored.
    """
    settings: Settings = request.app.state.settings
    hops = settings.trusted_proxy_hops
    forwarded = [
        entry.strip()
        for entry in request.headers.get("x-forwarded-for", "").split(",")
        if entry.strip()
    ]
    if hops > 0 and forwarded:
        return forwarded[max(len(forwarded) - hops, 0)]
    return request.client.host if request.client else "unknown"
