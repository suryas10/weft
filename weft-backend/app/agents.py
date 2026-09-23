"""
agents.py — Weft Multi-Agent Orchestration Engine
==================================================
Key upgrades in this revision
──────────────────────
1. Exponential back-off on Gemini/HiDevs HTTP 429 rate-limit responses
   (max 5 retries, initial delay 1 s, cap 32 s, with ±25 % jitter).

2. handle_signal() — central Moss signal router used in the
   run_multiagent_workflow generation loop:
     • INJECT_FACT  → console log only   (soft-interrupt, non-blocking)
     • PAUSE        → console log only   (soft-interrupt, non-blocking)
     • ABORT_TASK   → raises AbortSignalRaised, breaks the loop,
                       broadcasts canvas_pivot via LiveKit data channel
                       so the Next.js UI can strike-through stale text
                       and render the freshly-pivoted draft.

3. run_multiagent_workflow() — replaces the old asyncio.gather with a
   structured orchestration loop that polls Moss every 100 ms on every
   iteration and routes signals through handle_signal().

4. run_agent_worker() is kept as the FastAPI entry-point, now calling
   run_multiagent_workflow() instead of the old gather.
"""

import asyncio
import json
import logging
import os
import random
from typing import Optional

from pathlib import Path

import httpx
from dotenv import load_dotenv
from livekit.api import DataPacket, LiveKitAPI, SendDataRequest

from app.moss_store import Signal, moss_bus

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger("weft.agents")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# ── Environment ────────────────────────────────────────────────────────────────────────

HIDEVS_API_KEY = os.getenv("HIDEVS_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://llm.hidevs.xyz/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.6-flash")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")

# ── Retry / back-off config ─────────────────────────────────────────────────────────────

_MAX_RETRIES = 5          # maximum number of 429-retry attempts
_BACKOFF_BASE = 1.0       # initial wait in seconds
_BACKOFF_CAP = 32.0       # maximum wait cap in seconds
_JITTER_FACTOR = 0.25     # ±25 % random jitter

# ── System prompts ───────────────────────────────────────────────────────────────────────

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


# ── Custom exception for abort escalation ───────────────────────────────────────────

class AbortSignalRaised(Exception):
    """Raised by handle_signal when an ABORT_TASK signal is routed.

    Carries the original Moss Signal so the orchestration loop can
    surface reason, sender, and latency metadata to the UI and logs.
    """
    def __init__(self, signal: Signal) -> None:
        super().__init__(signal.message)
        self.signal = signal


# ── LiveKit helpers ────────────────────────────────────────────────────────────────────

def _livekit_http_url() -> str:
    url = LIVEKIT_URL
    if url.startswith("wss://"):
        url = "https://" + url[len("wss://"):]
    elif url.startswith("ws://"):
        url = "http://" + url[len("ws://"):]
    return url


async def publish_to_room(room_name: str, payload: dict) -> None:
    """Broadcast a JSON payload to every participant in a LiveKit room."""
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


# ── LLM wrapper with exponential back-off on HTTP 429 ────────────────────────────

async def call_hidevs_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Call Gemini 3.6 Flash via the HiDevs API gateway.

    Implements full-jitter exponential back-off for HTTP 429 (Too Many Requests):
      wait = min(BASE * 2^attempt, CAP) * uniform(1 - JITTER, 1 + JITTER)

    After _MAX_RETRIES exhausted, returns a structured fallback string so the
    rest of the workflow continues gracefully instead of raising.
    """
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

    attempt = 0
    last_status: Optional[int] = None

    while attempt <= _MAX_RETRIES:
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

            if resp.status_code == 429:
                last_status = 429
                # Full-jitter back-off: spread load across the retry window
                raw_delay = min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_CAP)
                jitter = raw_delay * _JITTER_FACTOR
                delay = raw_delay + random.uniform(-jitter, jitter)
                logger.warning(
                    "Gemini 429 rate-limit hit (attempt %d/%d). "
                    "Back-off %.2fs before retry.",
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue

            # Non-429, non-200 — return fallback immediately, no retry
            last_status = resp.status_code
            logger.error("LLM request failed with status %d.", resp.status_code)
            return (
                f"[Fallback] Competitive scan incomplete (LLM status {resp.status_code}). "
                "Treat 2024–2025 copilot benchmarks as potentially obsolete versus 2026."
            )

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # network errors, timeouts, decode failures
            logger.exception("LLM request raised an exception: %s", exc)
            return (
                "[Fallback] Live research unavailable. Baseline 2025 copilot share figures "
                "are likely stale relative to Cursor 2.0 and in-process agent memory systems."
            )

    # Exhausted all retries on repeated 429s
    logger.error(
        "Gemini API exhausted all %d retries (last status %s). Returning fallback.",
        _MAX_RETRIES,
        last_status,
    )
    return (
        f"[Fallback — 429 after {_MAX_RETRIES} retries] "
        "Live Gemini data unavailable due to rate limiting. "
        "Moss in-process memory is the only reliable data source right now."
    )


# ── Moss signal router ─────────────────────────────────────────────────────────────────────

async def handle_signal(
    signal: Signal,
    session_id: str,
    room_name: str,
    current_canvas: str,
) -> None:
    """
    Central router for Moss signals, called from run_multiagent_workflow.

    Routing table
    ─────────────
    INJECT_FACT  → console log (soft-interrupt). Proves the architecture
                   handles mid-turn fact injection without breaking flow.

    PAUSE        → console log (soft-interrupt). Proves the architecture
                   handles pause signals without terminating workers.

    ABORT_TASK   → active execution:
                   1. Publishes moss_signal to the Weft UI panel.
                   2. Publishes canvas_pivot so the Next.js canvas can
                      strike-through stale content and await the fresh draft.
                   3. Raises AbortSignalRaised to break the caller's loop.

    Any other type is logged as a warning and silently ignored.
    """
    sig_type = signal.signal_type.upper()

    # — Soft interrupt: INJECT_FACT ──────────────────────────────────────────────────
    if sig_type == "INJECT_FACT":
        logger.info(
            "[INJECT_FACT] Soft-interrupt | session=%s sender=%s | %s",
            session_id,
            signal.sender,
            signal.message,
        )
        # Non-blocking — generation loop continues uninterrupted.
        return

    # — Soft interrupt: PAUSE ────────────────────────────────────────────────────────
    if sig_type == "PAUSE":
        logger.info(
            "[PAUSE] Soft-interrupt | session=%s sender=%s | %s",
            session_id,
            signal.sender,
            signal.message,
        )
        # Non-blocking — generation loop continues uninterrupted.
        return

    # — Hard interrupt: ABORT_TASK ────────────────────────────────────────────────
    if sig_type == "ABORT_TASK":
        logger.warning(
            "[ABORT_TASK] Hard-interrupt | session=%s sender=%s latency=%.2fms | %s",
            session_id,
            signal.sender,
            signal.latency_ms,
            signal.message,
        )

        # Step 1: surface the signal in the Moss panel on the UI
        await publish_to_room(
            room_name,
            {
                "type": "moss_signal",
                "signal": signal.model_dump(),
            },
        )

        # Step 2: broadcast canvas_pivot so Next.js can:
        #   • strike-through the stale_content (legacy draft)
        #   • show a "pivoting…" indicator while the fresh draft arrives
        await publish_to_room(
            room_name,
            {
                "type": "canvas_pivot",
                "reason": signal.message,
                "stale_content": current_canvas,
                "sender": signal.sender,
                "latency_ms": signal.latency_ms,
            },
        )

        # Step 3: raise to break the orchestration loop
        raise AbortSignalRaised(signal)

    # — Unknown signal type ────────────────────────────────────────────────────────
    logger.warning(
        "[UNKNOWN SIGNAL] type='%s' sender='%s' | Ignoring.",
        signal.signal_type,
        signal.sender,
    )


# ── Abort-aware LLM call ──────────────────────────────────────────────────────────────────

async def llm_until_abort(
    session_id: str, system_prompt: str, user_prompt: str
) -> tuple[Optional[str], Optional[Signal]]:
    """Run an LLM call while polling Moss every 50 ms; cancel immediately on ABORT_TASK."""
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


# ── Researcher worker ─────────────────────────────────────────────────────────────────────

async def researcher_worker(session_id: str, room_name: str, goal: str) -> None:
    """
    Researcher agent: queries Gemini for competitive intelligence, evaluates
    source freshness, and writes ABORT_TASK to Moss if stale data is detected.
    All LLM calls are protected by the exponential back-off in call_hidevs_llm.
    """
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


# ── Writer worker ──────────────────────────────────────────────────────────────────────────

async def writer_worker(
    session_id: str, room_name: str, goal: str
) -> tuple[str, Optional[Signal]]:
    """
    Writer agent: drafts a Competitive Analysis Report section-by-section,
    reading Moss memory on each iteration and halting immediately on ABORT_TASK.

    Returns (final_canvas, aborted_signal) so the orchestration loop can
    track the most recent canvas content when routing signals.
    """
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
                "Lead with the real-time / in-process memory shift. "
                "Do not rely on stale 2024–2025 share tables."
            ),
        )
        if pivoted:
            canvas = pivoted.strip()
            await publish_to_room(
                room_name, {"type": "canvas_update", "content": canvas}
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

    return canvas, aborted


# ── Orchestration loop with handle_signal routing ─────────────────────────────────

async def run_multiagent_workflow(
    session_id: str,
    room_name: str,
    goal: str,
) -> None:
    """
    Primary orchestration loop for a Weft session.

    Architecture
    ────────────
    1. Initialise Moss SessionIndex.
    2. Spawn Researcher and Writer as concurrent asyncio Tasks.
    3. Poll Moss every 100 ms for live signals.
    4. Route each new signal through handle_signal():
         • INJECT_FACT / PAUSE  → console-log only (soft-interrupt proof)
         • ABORT_TASK           → AbortSignalRaised is caught here:
             a. Both worker tasks are cancelled cleanly.
             b. The canvas_pivot LiveKit broadcast was already sent inside
                handle_signal(), telling Next.js to strike-through legacy text.
             c. A final Moss-grounded pivot draft is generated and published
                as canvas_update to replace the stale content.
    5. Workflow ends when both workers finish, or after the pivot is published.
    """
    logger.info(
        "[ORCHESTRATOR] Starting | session=%s room=%s",
        session_id,
        room_name,
    )

    # current_canvas is updated by the Writer task; we pass snapshots to
    # handle_signal so canvas_pivot carries the most recent stale content.
    current_canvas: str = "# Competitive Analysis Report\n\n"

    researcher_task: asyncio.Task = asyncio.create_task(
        researcher_worker(session_id, room_name, goal),
        name=f"researcher_{session_id}",
    )
    writer_task: asyncio.Task = asyncio.create_task(
        writer_worker(session_id, room_name, goal),
        name=f"writer_{session_id}",
    )

    # Track seen signal ids to avoid routing duplicate Moss entries
    _seen_signal_ids: set[str] = set()

    try:
        while not (researcher_task.done() and writer_task.done()):
            # — Poll Moss for any new signal ────────────────────────────────────
            signal: Optional[Signal] = await moss_bus.detect_abort(session_id)

            if signal and signal.id not in _seen_signal_ids:
                _seen_signal_ids.add(signal.id)
                try:
                    await handle_signal(
                        signal=signal,
                        session_id=session_id,
                        room_name=room_name,
                        current_canvas=current_canvas,
                    )
                    # INJECT_FACT / PAUSE return here — loop continues.

                except AbortSignalRaised as abort_exc:
                    logger.warning(
                        "[ORCHESTRATOR] AbortSignalRaised — cancelling workers "
                        "and executing canvas pivot. Reason: %s",
                        abort_exc.signal.message,
                    )

                    # Cancel both workers
                    researcher_task.cancel()
                    writer_task.cancel()
                    for t in (researcher_task, writer_task):
                        try:
                            await t
                        except (asyncio.CancelledError, Exception):
                            pass

                    # Pivot: fetch Moss memory and generate the fresh report
                    logger.info("[ORCHESTRATOR] Executing canvas pivot.")
                    memory_hits, _ = await moss_bus.query_memory(
                        session_id,
                        "ABORT_TASK obsolete competitive 2026 Cursor in-process memory",
                    )
                    pivoted, _ = await llm_until_abort(
                        session_id,
                        WRITER_SYSTEM,
                        (
                            "The previous draft is obsolete. Rewrite the FULL "
                            "Competitive Analysis Report in Markdown. "
                            "Pivot immediately based on this Moss memory:\n"
                            f"{chr(10).join(memory_hits)}\n"
                            f"Abort reason: {abort_exc.signal.message}\n"
                            "Lead with the real-time / in-process memory shift. "
                            "Do not rely on stale 2024–2025 share tables."
                        ),
                    )
                    if pivoted:
                        await publish_to_room(
                            room_name,
                            {"type": "canvas_update", "content": pivoted.strip()},
                        )
                    logger.info("[ORCHESTRATOR] Canvas pivot complete | session=%s", session_id)
                    return  # Workflow complete

            # Update current_canvas snapshot if writer task has returned
            if writer_task.done() and not writer_task.cancelled():
                exc = writer_task.exception() if not writer_task.cancelled() else None
                if exc is None:
                    result = writer_task.result()
                    if isinstance(result, tuple) and len(result) == 2:
                        current_canvas = result[0] or current_canvas

            await asyncio.sleep(0.1)  # 100 ms orchestration poll interval

    except asyncio.CancelledError:
        # Parent task cancelled — propagate cancellation to workers
        researcher_task.cancel()
        writer_task.cancel()
        for t in (researcher_task, writer_task):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        raise

    # Both workers finished without abort — report any uncaught worker errors
    for t in (researcher_task, writer_task):
        if not t.cancelled() and t.exception():
            logger.error(
                "[ORCHESTRATOR] Worker '%s' raised: %s",
                t.get_name(),
                t.exception(),
            )

    logger.info("[ORCHESTRATOR] Workflow complete | session=%s", session_id)


# ── FastAPI entry-point ──────────────────────────────────────────────────────────────────────

async def run_agent_worker(session_id: str, room_name: str, goal: str) -> None:
    """
    LiveKit agent worker entry-point, called by FastAPI /api/session/init.

    Initialises the Moss SessionIndex for the session and delegates to the
    run_multiagent_workflow orchestration loop.
    """
    await moss_bus.init_session(session_id)
    await run_multiagent_workflow(session_id, room_name, goal)
