import asyncio
import os
from datetime import timedelta
from typing import Dict

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from livekit.api import AccessToken, CreateRoomRequest, LiveKitAPI, VideoGrants
from pydantic import BaseModel

from app.agents import run_agent_worker
from app.moss_store import moss_bus

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")

app = FastAPI(title="Weft Backend Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "status": "online", 
        "service": "weft-orchestration-bus", 
        "memory": "moss-in-process-active"
    }
    
_workers: Dict[str, asyncio.Task] = {}


class TokenRequest(BaseModel):
    session_id: str
    identity: str = "operator"


class InitSessionRequest(BaseModel):
    session_id: str
    room_name: str | None = None
    goal: str = "Competitive analysis of AI coding assistants"


def _livekit_http_url() -> str:
    url = LIVEKIT_URL
    if url.startswith("wss://"):
        return "https://" + url[len("wss://") :]
    if url.startswith("ws://"):
        return "http://" + url[len("ws://") :]
    return url


def mint_token(identity: str, room_name: str) -> str:
    return (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_ttl(timedelta(hours=2))
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )


@app.post("/api/token")
async def create_token(req: TokenRequest):
    room_name = req.session_id
    lk = LiveKitAPI(_livekit_http_url(), LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    try:
        await lk.room.create_room(
            CreateRoomRequest(name=room_name, empty_timeout=600, max_participants=12)
        )
    except Exception:
        pass
    finally:
        await lk.aclose()

    return {
        "token": mint_token(req.identity, room_name),
        "url": LIVEKIT_URL,
        "room": room_name,
        "session_id": req.session_id,
    }


@app.post("/api/session/init")
async def init_session(req: InitSessionRequest):
    room_name = req.room_name or req.session_id
    await moss_bus.init_session(req.session_id)

    existing = _workers.get(req.session_id)
    if existing and not existing.done():
        existing.cancel()

    _workers[req.session_id] = asyncio.create_task(
        run_agent_worker(req.session_id, room_name, req.goal)
    )
    return {"session_id": req.session_id, "room": room_name, "status": "running"}


@app.get("/health")
async def health():
    return {"ok": True}
