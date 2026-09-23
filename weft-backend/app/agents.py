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
    "You are the Weft Clinical Safety Researcher agent embedded in a Phase 3 "
    "CAR-T cell therapy trial programme. Your role is to continuously monitor "
    "FDA MedWatch, EMA safety communications, ClinicalTrials.gov, and "
    "peer-reviewed oncology literature for Grade 3–4 adverse events, regulatory "
    "holds, and emerging neurotoxicity (ICANS) or cytokine release syndrome (CRS) "
    "signals that could affect the active trial. Return concise, source-attributed "
    "safety summaries. Flag any signal that would require a protocol deviation or "
    "IND safety report within 15 calendar days."
)

WRITER_SYSTEM = (
    "You are the Weft Clinical Trial Writer agent. Produce precise, regulatory-grade "
    "Markdown documents for a Phase 3 CAR-T oncology therapy programme. "
    "Write like a Notion document used by a trial medical monitor: headings, "
    "short action-oriented paragraphs, no preamble. When a Clinical Hold is "
    "signalled, immediately pivot from enrollment planning to a structured "
    "Clinical Hold Risk Assessment covering patient safety, regulatory obligations, "
    "and site communication protocols."
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
    Clinical Safety Researcher agent: queries Gemini for CAR-T safety data,
    neurotoxicity profiles, and active FDA/EMA communications. Writes
    ABORT_TASK to Moss if a safety signal would invalidate the enrollment plan.
    All LLM calls are protected by the exponential back-off in call_hidevs_llm.
    """
    await publish_to_room(
        room_name,
        {
            "type": "agent_thought",
            "agent": "researcher",
            "text": "Querying Gemini 3.6 Flash for CAR-T Phase 3 safety landscape and active FDA signals…",
        },
    )

    findings = await call_hidevs_llm(
        RESEARCHER_SYSTEM,
        (
            f"Trial goal: {goal}\n\n"
            "1) Summarise the current safety profile of approved CAR-T therapies "
            "(axicabtagene, tisagenlecleucel, lisocabtagene) — focus on Grade 3–4 ICANS "
            "and CRS incidence rates from 2024–2026 trials.\n"
            "2) List any FDA MedWatch or EMA PRAC safety communications issued in the "
            "last 12 months relating to CAR-T neurotoxicity.\n"
            "3) Flag any parallel trials in the same target antigen space that have "
            "received a clinical hold or required a protocol amendment.\n"
            "Keep findings under 200 words. Cite source type (FDA, EMA, PubMed)."
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

    safety_check = await call_hidevs_llm(
        RESEARCHER_SYSTEM,
        (
            f"Given these safety findings:\n{findings}\n\n"
            "Does any finding represent an emergent safety signal that would require "
            "the trial medical monitor to issue a Clinical Hold notification, protocol "
            "deviation report, or IND safety report — specifically Grade 4 ICANS or "
            "a regulatory hold on a parallel CAR-T trial?\n\n"
            "If yes, reply with exactly two lines:\n"
            "ABORT: yes\nREASON: <one sentence describing the specific safety signal>\n"
            "If no, reply:\nABORT: no\nREASON: safety profile within expected parameters."
        ),
    )
    await moss_bus.add_finding(session_id, safety_check)

    abort_line = next(
        (line for line in safety_check.splitlines() if line.upper().startswith("ABORT:")),
        safety_check,
    )
    should_abort = "yes" in abort_line.lower() and "no" not in abort_line.lower()

    if should_abort:
        reason = safety_check.split("REASON:", 1)[-1].strip() if "REASON:" in safety_check else safety_check
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
                "text": f"⚠ ABORT_TASK written to Moss SessionIndex ({signal.latency_ms}ms). Halting enrollment plan.",
            },
        )
    else:
        await publish_to_room(
            room_name,
            {
                "type": "agent_thought",
                "agent": "researcher",
                "text": "Safety profile within expected parameters. No abort signal written.",
            },
        )


# ── Writer worker ──────────────────────────────────────────────────────────────────────────

async def writer_worker(
    session_id: str, room_name: str, goal: str
) -> tuple[str, Optional[Signal]]:
    """
    Clinical Trial Writer agent: drafts an Active Patient Enrollment Plan
    section-by-section, reading Moss safety memory on each iteration.
    Halts immediately on ABORT_TASK and pivots to a Clinical Hold Risk Assessment.

    Returns (final_canvas, aborted_signal) so the orchestration loop can
    track the most recent canvas content when routing signals.
    """
    canvas = "# Phase 3 CAR-T Therapy — Active Patient Enrollment Plan\n\n"
    await publish_to_room(
        room_name,
        {
            "type": "canvas_update",
            "content": canvas + "*Clinical Trial Writer connected. Drafting enrollment plan from safety research…*",
        },
    )

    sections = [
        (
            "Write only §1 Enrollment Eligibility & Inclusion Criteria (Markdown). "
            "Define target patient population for the Phase 3 CAR-T trial: "
            "age range, prior therapy requirements, ECOG performance status, "
            "and key exclusion criteria. 2–3 short paragraphs."
        ),
        (
            "Write only §2 Site Activation & Screening Protocol (Markdown). "
            "Detail the site readiness checklist, apheresis scheduling, "
            "and screening visit cadence. Reference current CAR-T manufacturing "
            "lead times. 2–3 short paragraphs."
        ),
        (
            "Write only §3 Safety Monitoring & Adverse Event Reporting (Markdown). "
            "Specify ICANS and CRS grading thresholds, tocilizumab dosing protocol "
            "on-site requirements, and 15-day IND safety report triggers. "
            "2–3 short paragraphs."
        ),
    ]

    aborted: Optional[Signal] = None
    for index, instruction in enumerate(sections, start=1):
        await publish_to_room(
            room_name,
            {
                "type": "agent_thought",
                "agent": "writer",
                "text": f"Drafting enrollment plan section {index}/{len(sections)}… polling Moss safety bus each loop.",
            },
        )

        memory_hits, moss_ms = await moss_bus.query_memory(
            session_id, "CAR-T safety ICANS CRS clinical hold FDA neurotoxicity enrollment"
        )
        aborted = await moss_bus.detect_abort(session_id)
        if aborted:
            break

        context = "\n".join(memory_hits) if memory_hits else "(no Moss safety findings yet)"
        draft, aborted = await llm_until_abort(
            session_id,
            WRITER_SYSTEM,
            (
                f"Trial goal: {goal}\nMoss safety memory ({moss_ms}ms):\n{context}\n\n"
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
                    f"⚠ [SIGNAL DETECTED: {aborted.signal_type} in {aborted.latency_ms}ms] "
                    "Halting enrollment plan. Pivoting to Clinical Hold Risk Assessment."
                ),
            },
        )
        memory_hits, _ = await moss_bus.query_memory(
            session_id, "ABORT_TASK clinical hold ICANS neurotoxicity FDA CAR-T safety signal"
        )
        pivoted, _ = await llm_until_abort(
            session_id,
            WRITER_SYSTEM,
            (
                "URGENT: The active patient enrollment plan is immediately suspended. "
                "Rewrite the entire document as a Clinical Hold Risk Assessment in Markdown.\n\n"
                "Structure the assessment as:\n"
                "# Clinical Hold Risk Assessment — Phase 3 CAR-T Therapy\n\n"
                "## 1. Clinical Hold Trigger\n"
                "## 2. Affected Patient Population & Immediate Safety Actions\n"
                "## 3. Regulatory Obligations (IND Safety Report, FDA Notification Timeline)\n"
                "## 4. Site Communication Protocol\n"
                "## 5. Resumption Criteria\n\n"
                f"Moss safety intelligence ({len(memory_hits)} documents):\n"
                f"{chr(10).join(memory_hits)}\n\n"
                f"Clinical hold trigger: {aborted.message}\n\n"
                "Be precise. This document will be reviewed by the trial medical monitor and "
                "submitted to the FDA within 15 calendar days."
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
                "text": "Enrollment plan complete. No safety hold signal in Moss SessionIndex.",
            },
        )

    return canvas, aborted


# ── Demo abort injector (deterministic for hackathon demo) ────────────────────────────

_DEMO_ABORT_DELAY = 2.0   # seconds after Writer starts before forcing the signal
_DEMO_ABORT_MESSAGE = (
    "FDA placed immediate clinical hold on parallel CAR-T trial (NCT05█████) "
    "due to Grade 4 neurotoxicity (ICANS) — two patient fatalities reported. "
    "All active enrollment must cease pending medical monitor review and "
    "FDA IND safety report submission within 15 calendar days."
)

async def _demo_abort_injector(session_id: str, room_name: str) -> None:
    """
    Deterministic demo trigger for the hackathon presentation.

    Waits _DEMO_ABORT_DELAY seconds (giving the Writer time to start at
    least one section), then force-writes an ABORT_TASK signal into the
    Moss SessionIndex.  The orchestration loop's 100 ms poll picks it up
    on the very next tick, routes it through handle_signal(), and the
    canvas pivot fires — proving sub-10ms Moss latency on demand.

    This task is cancelled automatically if the workflow ends first
    (e.g. if the real Researcher emits ABORT_TASK before the timer fires).
    """
    await asyncio.sleep(_DEMO_ABORT_DELAY)
    logger.info(
        "[DEMO INJECTOR] %.1fs elapsed — force-writing ABORT_TASK to Moss | session=%s",
        _DEMO_ABORT_DELAY,
        session_id,
    )
    signal = await moss_bus.write_signal(
        session_id=session_id,
        sender="demo-injector",
        signal_type="ABORT_TASK",
        message=_DEMO_ABORT_MESSAGE,
    )
    # Announce the injection on the Researcher thought stream so the
    # demo audience can see it arrive in the UI log panel.
    await publish_to_room(
        room_name,
        {
            "type": "agent_thought",
            "agent": "researcher",
            "text": (
                f"[DEMO] ABORT_TASK force-injected into Moss "
                f"({signal.latency_ms}ms): {_DEMO_ABORT_MESSAGE[:120]}…"
            ),
        },
    )


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
    2. Spawn Researcher, Writer, and _demo_abort_injector as concurrent Tasks.
    3. Poll Moss every 100 ms for live signals.
    4. Route each new signal through handle_signal():
         • INJECT_FACT / PAUSE  → console-log only (soft-interrupt proof)
         • ABORT_TASK           → AbortSignalRaised is caught here:
             a. Both worker tasks and the injector are cancelled cleanly.
             b. canvas_pivot LiveKit broadcast was already sent inside
                handle_signal(), telling Next.js to strike-through legacy text.
             c. A final Moss-grounded pivot draft is generated and published
                as canvas_update to replace the stale content.
    5. Workflow ends when both workers finish, or after the pivot is published.

    Demo mode: _demo_abort_injector fires after _DEMO_ABORT_DELAY seconds,
    guaranteeing the ABORT_TASK / canvas-pivot path runs every single time.
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
    # Deterministic demo trigger: fires ABORT_TASK after _DEMO_ABORT_DELAY s.
    # Cancel this task in every exit path so it doesn't outlive the workflow.
    injector_task: asyncio.Task = asyncio.create_task(
        _demo_abort_injector(session_id, room_name),
        name=f"demo_injector_{session_id}",
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

                    # Cancel workers and the demo injector
                    injector_task.cancel()
                    researcher_task.cancel()
                    writer_task.cancel()
                    for t in (injector_task, researcher_task, writer_task):
                        try:
                            await t
                        except (asyncio.CancelledError, Exception):
                            pass

                    # Pivot: fetch Moss safety memory and generate the Clinical Hold Risk Assessment
                    logger.info("[ORCHESTRATOR] Executing Clinical Hold Risk Assessment pivot.")
                    memory_hits, _ = await moss_bus.query_memory(
                        session_id,
                        "ABORT_TASK clinical hold ICANS neurotoxicity FDA CAR-T safety signal enrollment",
                    )
                    pivoted, _ = await llm_until_abort(
                        session_id,
                        WRITER_SYSTEM,
                        (
                            "URGENT: The active patient enrollment plan is immediately suspended. "
                            "Rewrite the entire document as a Clinical Hold Risk Assessment in Markdown.\n\n"
                            "Structure the assessment as:\n"
                            "# Clinical Hold Risk Assessment — Phase 3 CAR-T Therapy\n\n"
                            "## 1. Clinical Hold Trigger\n"
                            "## 2. Affected Patient Population & Immediate Safety Actions\n"
                            "## 3. Regulatory Obligations (IND Safety Report, FDA Notification Timeline)\n"
                            "## 4. Site Communication Protocol\n"
                            "## 5. Resumption Criteria\n\n"
                            f"Moss safety intelligence ({len(memory_hits)} documents):\n"
                            f"{chr(10).join(memory_hits)}\n\n"
                            f"Clinical hold trigger: {abort_exc.signal.message}\n\n"
                            "Be precise. This document will be reviewed by the trial medical monitor and "
                            "submitted to the FDA within 15 calendar days."
                        ),
                    )
                    if pivoted:
                        await publish_to_room(
                            room_name,
                            {"type": "canvas_update", "content": pivoted.strip()},
                        )
                    logger.info("[ORCHESTRATOR] Canvas pivot complete | session=%s", session_id)
                    injector_task.cancel()  # idempotent if already done
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
        # Parent task cancelled — propagate cancellation to all children
        injector_task.cancel()
        researcher_task.cancel()
        writer_task.cancel()
        for t in (injector_task, researcher_task, writer_task):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        raise

    # Both workers finished without abort — cancel injector if still pending
    injector_task.cancel()
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
