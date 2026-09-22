import asyncio
import json
import os
from typing import Optional

from pathlib import Path

import httpx
from dotenv import load_dotenv
from livekit.api import DataPacket, LiveKitAPI, SendDataRequest

from app.moss_store import Signal, moss_bus

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

HIDEVS_API_KEY = os.getenv("HIDEVS_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://llm.hidevs.xyz/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.6-flash")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")

RESEARCHER_SYSTEM = (
    "You are the Weft Researcher agent. Investigate the competitive landscape of "
    "AI coding assistants (Cursor, GitHub Copilot, Windsurf, Replit, Claude Code). "
    "Return concise, factual findings. Flag obsolete or stale sources explicitly."
)

WRITER_SYSTEM = (
    "You are the Weft Writer agent. Produce polished Markdown for a Competitive "
    "Analysis Report. Write like a Notion document: headings, short paragraphs, "
    "no preamble."
)


def _livekit_http_url() -> str:
    url = LIVEKIT_URL
    if url.startswith("wss://"):
        url = "https://" + url[len("wss://") :]
    elif url.startswith("ws://"):
        url = "http://" + url[len("ws://") :]
    return url


async def publish_to_room(room_name: str, payload: dict) -> None:
    lk = LiveKitAPI(_livekit_http_url(), LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    try:
        request = SendDataRequest(
            room=room_name,
            data=json.dumps(payload).encode("utf-8"),
            kind=DataPacket.Kind.RELIABLE,
            topic="weft",
        )
        await lk.room.send_data(request)
    finally:
        await lk.aclose()


async def call_hidevs_llm(system_prompt: str, user_prompt: str) -> str:
    """Call Gemini 3.6 Flash via the HiDevs API gateway."""
    headers = {
        "Authorization": f"Bearer {HIDEVS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            return (
                f"[Fallback] Competitive scan incomplete (LLM status {resp.status_code}). "
                "Treat 2024–2025 copilot benchmarks as potentially obsolete versus 2026."
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        return (
            "[Fallback] Live research unavailable. Baseline 2025 copilot share figures "
            "are likely stale relative to Cursor 2.0 and in-process agent memory systems."
        )


async def llm_until_abort(
    session_id: str, system_prompt: str, user_prompt: str
) -> tuple[Optional[str], Optional[Signal]]:
    """Run an LLM call while polling Moss; cancel immediately on ABORT_TASK."""
    llm_task = asyncio.create_task(call_hidevs_llm(system_prompt, user_prompt))
    try:
        while not llm_task.done():
            signal = await moss_bus.detect_abort(session_id)
            if signal:
                llm_task.cancel()
                try:
                    await llm_task
                except (asyncio.CancelledError, Exception):
                    pass
                return None, signal
            await asyncio.sleep(0.05)
        return llm_task.result(), None
    except asyncio.CancelledError:
        llm_task.cancel()
        raise


async def researcher_worker(session_id: str, room_name: str, goal: str) -> None:
    await publish_to_room(
        room_name,
        {
            "type": "agent_thought",
            "agent": "researcher",
            "text": "Querying Gemini 3.6 Flash for live competitive intelligence…",
        },
    )

    findings = await call_hidevs_llm(
        RESEARCHER_SYSTEM,
        (
            f"Goal: {goal}\n"
            "1) Summarize current competitive positioning for AI coding assistants in 2026.\n"
            "2) Call out any datasets, market-share figures, or product versions that look obsolete.\n"
            "Keep it under 180 words."
        ),
    )
    await moss_bus.add_finding(session_id, findings)
    await publish_to_room(
        room_name,
        {
            "type": "agent_thought",
            "agent": "researcher",
            "text": findings[:500],
        },
    )

    freshness = await call_hidevs_llm(
        RESEARCHER_SYSTEM,
        (
            f"Given these findings:\n{findings}\n\n"
            "If any cited data, version, or benchmark is stale versus 2026 (for example "
            "pre-Cursor 2.0, Copilot 2024/2025 share tables, or cloud RAG latency assumptions), "
            "reply with exactly two lines:\n"
            "ABORT: yes\nREASON: <one sentence>\n"
            "Otherwise reply:\nABORT: no\nREASON: sources look current."
        ),
    )
    await moss_bus.add_finding(session_id, freshness)

    abort_line = next(
        (line for line in freshness.splitlines() if line.upper().startswith("ABORT:")),
        freshness,
    )
    should_abort = "yes" in abort_line.lower() and "no" not in abort_line.lower()

    if should_abort:
        reason = freshness.split("REASON:", 1)[-1].strip() if "REASON:" in freshness else freshness
        signal = await moss_bus.write_signal(
            session_id=session_id,
            sender="researcher",
            signal_type="ABORT_TASK",
            message=reason[:400],
        )
        await publish_to_room(
            room_name,
            {
                "type": "moss_signal",
                "signal": signal.model_dump(),
            },
        )
        await publish_to_room(
            room_name,
            {
                "type": "agent_thought",
                "agent": "researcher",
                "text": f"Pushed ABORT_TASK to Moss SessionIndex ({signal.latency_ms}ms).",
            },
        )
    else:
        await publish_to_room(
            room_name,
            {
                "type": "agent_thought",
                "agent": "researcher",
                "text": "Sources look current. No abort signal written.",
            },
        )


async def writer_worker(session_id: str, room_name: str, goal: str) -> None:
    canvas = "# Competitive Analysis Report\n\n"
    await publish_to_room(
        room_name,
        {
            "type": "canvas_update",
            "content": canvas + "*Writer connected. Drafting from live research…*",
        },
    )

    sections = [
        "Write only §1 Executive Summary (Markdown). 2 short paragraphs.",
        "Write only §2 Market landscape (Markdown). Compare 3 products. Use the latest facts you have.",
        "Write only §3 Architecture implications (Markdown). Contrast cloud vector DBs vs in-process shared memory.",
    ]

    aborted: Optional[Signal] = None
    for index, instruction in enumerate(sections, start=1):
        await publish_to_room(
            room_name,
            {
                "type": "agent_thought",
                "agent": "writer",
                "text": f"Generating section {index}/{len(sections)}… polling Moss each loop.",
            },
        )

        memory_hits, moss_ms = await moss_bus.query_memory(
            session_id, "competitive findings market share abort obsolete"
        )
        aborted = await moss_bus.detect_abort(session_id)
        if aborted:
            break

        context = "\n".join(memory_hits) if memory_hits else "(no Moss findings yet)"
        draft, aborted = await llm_until_abort(
            session_id,
            WRITER_SYSTEM,
            (
                f"Goal: {goal}\nMoss memory ({moss_ms}ms):\n{context}\n\n"
                f"{instruction}\nDo not repeat previous sections."
            ),
        )
        if aborted:
            break
        if draft:
            canvas = canvas.rstrip() + "\n\n" + draft.strip()
            await publish_to_room(
                room_name, {"type": "canvas_update", "content": canvas}
            )

    if aborted is None:
        aborted = await moss_bus.detect_abort(session_id)

    if aborted:
        await publish_to_room(
            room_name,
            {
                "type": "moss_signal",
                "signal": aborted.model_dump(),
            },
        )
        await publish_to_room(
            room_name,
            {
                "type": "agent_thought",
                "agent": "writer",
                "text": (
                    f"[SIGNAL DETECTED: {aborted.signal_type} in {aborted.latency_ms}ms] "
                    "Halting generation. Pivoting canvas from Moss memory."
                ),
            },
        )
        memory_hits, _ = await moss_bus.query_memory(
            session_id, "ABORT_TASK obsolete competitive 2026 Cursor in-process memory"
        )
        pivoted, _ = await llm_until_abort(
            session_id,
            WRITER_SYSTEM,
            (
                "The previous draft is obsolete. Rewrite the FULL Competitive Analysis Report "
                "in Markdown. Pivot immediately based on this Moss memory:\n"
                f"{chr(10).join(memory_hits)}\n"
                f"Abort reason: {aborted.message}\n"
                "Lead with the real-time / in-process memory shift. Do not rely on stale 2024–2025 share tables."
            ),
        )
        if pivoted:
            await publish_to_room(
                room_name, {"type": "canvas_update", "content": pivoted.strip()}
            )
    else:
        await publish_to_room(
            room_name,
            {
                "type": "agent_thought",
                "agent": "writer",
                "text": "Draft complete. No abort signal in Moss SessionIndex.",
            },
        )


async def run_agent_worker(session_id: str, room_name: str, goal: str) -> None:
    """LiveKit agent worker: Researcher + Writer loops sharing a Moss SessionIndex."""
    await moss_bus.init_session(session_id)
    await asyncio.gather(
        researcher_worker(session_id, room_name, goal),
        writer_worker(session_id, room_name, goal),
    )
