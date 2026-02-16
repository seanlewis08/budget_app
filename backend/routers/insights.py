"""
Financial Insights — AI-powered financial analysis with streaming responses.

Cost optimizations:
- Sonnet for initial analysis (nuanced reasoning), Haiku for follow-up chat (~4x cheaper)
- Anthropic prompt caching on the system prompt (90% cheaper on repeated input tokens)
- Server-side snapshot cache with 5-minute TTL (avoids redundant DB queries)

Endpoints:
- POST /api/insights/analyze  — Full financial analysis (streaming SSE, Sonnet)
- POST /api/insights/chat     — Follow-up questions with context (streaming SSE, Haiku)
- GET  /api/insights/snapshot  — Raw financial snapshot data (JSON)
"""

import os
import json
import time
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.financial_advisor import build_financial_snapshot, format_snapshot_for_prompt

logger = logging.getLogger(__name__)

router = APIRouter()

SAVINGS_GOAL = 20_000.0  # Default savings goal

# Model selection: Sonnet for deep analysis, Haiku for quick follow-ups
MODEL_ANALYZE = "claude-sonnet-4-5-20250929"   # ~$3/M in, $15/M out
MODEL_CHAT    = "claude-haiku-4-5-20251001"    # ~$0.80/M in, $4/M out

# Snapshot cache: avoid re-querying the DB for every chat message
_snapshot_cache = {
    "text": None,
    "data": None,
    "timestamp": 0,
}
CACHE_TTL_SECONDS = 300  # 5 minutes


# ── Schemas ──


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class AnalyzeRequest(BaseModel):
    context: str = ""  # Optional user context for personalized analysis


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    context: str = ""  # Carry forward the user context into chat


# ── Helpers ──


def _get_inv_db():
    """Try to get the investments DB session. Returns None if not available."""
    try:
        from ..investments_database import SessionLocal as InvSessionLocal
        return InvSessionLocal()
    except Exception:
        return None


def _get_snapshot(db: Session, force_refresh: bool = False) -> tuple[dict, str]:
    """
    Get the financial snapshot, using a 5-minute TTL cache.
    Returns (snapshot_dict, formatted_text).
    """
    now = time.time()
    if (
        not force_refresh
        and _snapshot_cache["text"] is not None
        and (now - _snapshot_cache["timestamp"]) < CACHE_TTL_SECONDS
    ):
        return _snapshot_cache["data"], _snapshot_cache["text"]

    inv_db = _get_inv_db()
    try:
        snapshot = build_financial_snapshot(db, inv_db, savings_goal=SAVINGS_GOAL)
        text = format_snapshot_for_prompt(snapshot)
    finally:
        if inv_db:
            inv_db.close()

    _snapshot_cache["data"] = snapshot
    _snapshot_cache["text"] = text
    _snapshot_cache["timestamp"] = now

    return snapshot, text


def _build_system_prompt(financial_data_text: str) -> str:
    """Build the system prompt with embedded financial data."""
    return f"""You are a personal financial advisor analyzing real financial data for a user who wants to save $20,000 by the end of the current year.

You have access to their complete financial picture below. Use the ACTUAL numbers — never make up data or use placeholder amounts.

{financial_data_text}

ANALYSIS GUIDELINES:
- Be specific: cite actual dollar amounts, category names, and percentages from the data above
- Be conversational and encouraging, but direct about problems
- Use markdown formatting: ## for section headers, **bold** for key numbers, bullet lists for recommendations
- When suggesting cuts, calculate the annual impact (monthly × 12)
- For the savings goal, show the math: what they need per month vs what they're actually saving
- If they're off track, prioritize recommendations by dollar impact (biggest savings first)
- Consider both expense reduction AND income optimization
- Factor in credit card debt — paying that down IS saving money
- If investment data is available, comment on portfolio health briefly

STRUCTURE YOUR ANALYSIS AS:
## Spending Summary
## Recurring Charges Audit
## Cash Flow Health
## Budget Scorecard
## Savings Goal Tracker
## Personalized Recommendations"""


def _stream_anthropic(
    system_prompt: str,
    messages: list[dict],
    model: str = MODEL_ANALYZE,
    max_tokens: int = 4096,
    use_prompt_caching: bool = False,
):
    """
    Generator that yields SSE events from Anthropic streaming API.

    When use_prompt_caching=True, marks the system prompt with cache_control
    so repeated calls (follow-up chat) pay 90% less for the system tokens.
    """
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        yield f"data: {json.dumps({'type': 'error', 'content': 'Anthropic API key not configured. Add ANTHROPIC_API_KEY to your .env file.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    client = anthropic.Anthropic(api_key=api_key)

    # Build the system parameter — with or without prompt caching
    if use_prompt_caching:
        system_param = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    else:
        system_param = system_prompt

    try:
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system_param,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                event_data = json.dumps({"type": "text", "content": text})
                yield f"data: {event_data}\n\n"

        yield "data: [DONE]\n\n"

    except anthropic.APIError as e:
        error_msg = f"Anthropic API error: {str(e)}"
        logger.error(error_msg)
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg)
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
        yield "data: [DONE]\n\n"


# ── Endpoints ──


@router.post("/analyze")
def analyze_finances(data: AnalyzeRequest, db: Session = Depends(get_db)):
    """
    Generate a full financial analysis using Claude Sonnet (streaming SSE).

    Uses the heavier model for the initial deep analysis where nuanced
    reasoning, math, and structured advice matter most.
    """
    _, financial_text = _get_snapshot(db, force_refresh=True)

    system_prompt = _build_system_prompt(financial_text)

    user_prompt = (
        "Please analyze my finances and give me a comprehensive, personalized report. "
        "Focus on actionable advice to help me reach my $20,000 savings goal by year-end."
    )
    if data.context.strip():
        user_prompt += f"\n\nADDITIONAL CONTEXT FROM USER:\n{data.context.strip()}"

    messages = [{"role": "user", "content": user_prompt}]

    return StreamingResponse(
        _stream_anthropic(
            system_prompt,
            messages,
            model=MODEL_ANALYZE,
            max_tokens=4096,
            use_prompt_caching=False,  # First call — no cache benefit yet
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat")
def chat_followup(data: ChatRequest, db: Session = Depends(get_db)):
    """
    Handle follow-up questions using Claude Haiku (streaming SSE).

    Uses the lighter model since follow-up questions are typically simpler
    pattern-matching on data already analyzed. Prompt caching ensures the
    system prompt (which is identical across calls) costs 90% less.

    Cost comparison per follow-up (approx):
    - Before:  Sonnet, no caching  → ~$0.04/call
    - After:   Haiku + caching     → ~$0.003/call  (>10x cheaper)
    """
    _, financial_text = _get_snapshot(db)  # Uses TTL cache

    system_prompt = _build_system_prompt(financial_text)
    if data.context.strip():
        system_prompt += f"\n\nADDITIONAL CONTEXT FROM USER:\n{data.context.strip()}"

    # Build messages: history + new user message
    messages = []
    for msg in data.history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": data.message})

    return StreamingResponse(
        _stream_anthropic(
            system_prompt,
            messages,
            model=MODEL_CHAT,
            max_tokens=2048,  # Follow-ups are shorter
            use_prompt_caching=True,  # Same system prompt every time
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/snapshot")
def get_snapshot(db: Session = Depends(get_db)):
    """Return the raw financial snapshot as JSON (useful for debugging)."""
    snapshot, _ = _get_snapshot(db, force_refresh=True)
    return snapshot
