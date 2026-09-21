import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.moss_store import moss_bus
from app.agents import call_hidevs_llm

app = FastAPI(title="Weft Backend Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class InitSessionRequest(BaseModel):
    session_id: str
    goal: str

@app.post("/api/session/init")
async def init_session(req: InitSessionRequest):
    res = await moss_bus.init_session(req.session_id)
    return res

@app.websocket("/ws/{session_id}")
async def agent_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    await moss_bus.init_session(session_id)
    
    try:
        # 1. Researcher starts initial work
        await websocket.send_json({
            "type": "agent_thought",
            "agent": "researcher",
            "text": "Scanning competitive landscape for AI coding assistants: Cursor, GitHub Copilot, Replit..."
        })
        await asyncio.sleep(2)

        # 2. Writer starts initial draft
        await websocket.send_json({
            "type": "canvas_update",
            "content": "# Competitive Analysis: AI Developer Tools\n\n## 1. Executive Summary\nAnalyzing legacy benchmarks for GitHub Copilot & Cursor 1.0..."
        })
        await websocket.send_json({
            "type": "agent_thought",
            "agent": "writer",
            "text": "Drafting Section 1 based on baseline 2025 specs..."
        })
        await asyncio.sleep(2.5)

        # 3. Researcher uncovers breaking update -> Writes ABORT signal to Moss (<3ms)
        sig = await moss_bus.write_signal(
            session_id=session_id,
            sender="researcher",
            signal_type="ABORT_TASK",
            message="Cursor 2.0 & Weft In-Process Memory architecture just validated. Obsoleted legacy comparison benchmarks."
        )
        
        await websocket.send_json({
            "type": "moss_signal",
            "signal": sig.dict()
        })
        await asyncio.sleep(1)

        # 4. Writer polls Moss index mid-loop, detects ABORT signal immediately (<5ms)
        await websocket.send_json({
            "type": "agent_thought",
            "agent": "writer",
            "text": f"🚨 [SIGNAL DETECTED: {sig.signal_type} in {sig.latency_ms}ms] Halting Section 1 draft immediately! Reprioritizing towards real-time in-process memory benchmarks."
        })
        await asyncio.sleep(1.5)

        # 5. Writer updates the main document canvas dynamically
        updated_text = (
            "# Competitive Analysis: AI Developer Tools & In-Process RAG\n\n"
            "## 1. The Real-Time Shift\n"
            "Traditional cloud vector DBs fail real-time multi-agent loops due to 300ms+ network hops. "
            "Weft leverages in-process shared memory (Moss) to achieve sub-5ms task coordination and dynamic task preemption."
        )
        await websocket.send_json({
            "type": "canvas_update",
            "content": updated_text
        })
        
        # Keep connection open
        while True:
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        pass