# Project: Weft (YC Fall 2026 × Moss Builder Sprint - Track 2)

## 1. Objective & Scope
Building a production-grade, zero-latency multi-agent collaborative workspace to solve the "Black Box" bottleneck in agent workflows. 

## 2. Core Architecture
*   **The Problem:** Traditional multi-agent systems rely on cloud vector DBs (300ms+ network hops), leaving agents deaf to state changes during long execution turns.
*   **The Solution:** Using Moss `SessionIndex` for sub-10ms in-process shared memory. This enables the "Researcher" agent to emit an `ABORT_TASK` signal that the "Writer" agent intercepts mid-turn to dynamically pivot its output.
*   **Tech Stack:** Python/FastAPI (Backend), Next.js/Tailwind (Frontend), LiveKit WebRTC (Agent-to-UI Data Channels), Gemini 3.6 Flash via HiDevs API (LLM reasoning).

## 3. Current State
*   Frontend (Next.js) is built with a Notion-style split canvas displaying real-time agent thought streams and a Moss Shared Memory panel.
*   Backend (FastAPI) has LiveKit token generation and the Moss in-process memory bus implemented.
*   **Immediate Pending Task:** Update `weft-backend/app/agents.py` to handle HTTP 429 rate limits from the Gemini API using an exponential backoff loop. Ensure the Researcher agent reliably writes the `ABORT_TASK` signal to Moss, and the Writer agent intercepts it to strike out legacy text on the live frontend canvas via LiveKit data channels.