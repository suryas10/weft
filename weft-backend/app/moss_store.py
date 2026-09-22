from pathlib import Path
from dotenv import load_dotenv
import json
import os
import time
import uuid
from typing import Dict, List, Optional

from moss import DocumentInfo, MossClient, QueryOptions, SessionIndex
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Signal(BaseModel):
    id: str
    sender: str
    signal_type: str
    message: str
    timestamp: float
    latency_ms: float


class MossMemoryLayer:
    """Real Moss in-process SessionIndex shared memory."""

    def __init__(self) -> None:
        project_id = os.getenv("MOSS_PROJECT_ID", "")
        project_key = os.getenv("MOSS_PROJECT_KEY", "")
        if not project_id or not project_key:
            raise RuntimeError("MOSS_PROJECT_ID and MOSS_PROJECT_KEY must be set")
        self.client = MossClient(project_id, project_key)
        self._indexes: Dict[str, SessionIndex] = {}

    async def init_session(self, session_id: str) -> dict:
        if session_id not in self._indexes:
            self._indexes[session_id] = await self.client.session(index_name=session_id)
        return {"session_id": session_id, "status": "initialized"}

    async def _index(self, session_id: str) -> SessionIndex:
        if session_id not in self._indexes:
            await self.init_session(session_id)
        return self._indexes[session_id]

    async def write_signal(
        self, session_id: str, sender: str, signal_type: str, message: str
    ) -> Signal:
        index = await self._index(session_id)
        started = time.perf_counter()
        signal_id = f"sig_{uuid.uuid4().hex[:12]}"
        payload = {
            "id": signal_id,
            "kind": "signal",
            "sender": sender,
            "signal_type": signal_type,
            "message": message,
            "timestamp": time.time(),
        }
        await index.add_docs(
            [
                DocumentInfo(
                    id=signal_id,
                    text=f"SIGNAL {signal_type}: {message}",
                    payload=json.dumps(payload),
                )
            ]
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return Signal(
            id=signal_id,
            sender=sender,
            signal_type=signal_type,
            message=message,
            timestamp=payload["timestamp"],
            latency_ms=latency_ms,
        )

    async def add_finding(self, session_id: str, text: str, source: str = "researcher") -> None:
        index = await self._index(session_id)
        doc_id = f"find_{uuid.uuid4().hex[:12]}"
        await index.add_docs(
            [
                DocumentInfo(
                    id=doc_id,
                    text=text,
                    payload=json.dumps({"kind": "finding", "source": source}),
                )
            ]
        )

    async def query_memory(self, session_id: str, query: str, top_k: int = 8) -> tuple[list[str], float]:
        index = await self._index(session_id)
        started = time.perf_counter()
        result = await index.query(query, QueryOptions(top_k=top_k))
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        docs = getattr(result, "docs", None) or []
        texts = [doc.text for doc in docs if getattr(doc, "text", None)]
        return texts, latency_ms

    async def detect_abort(self, session_id: str) -> Optional[Signal]:
        texts, latency_ms = await self.query_memory(
            session_id, "ABORT_TASK halt obsolete stale signal"
        )
        for text in texts:
            if "ABORT_TASK" not in text:
                continue
            message = text.split("ABORT_TASK:", 1)[-1].strip()
            return Signal(
                id="abort_detected",
                sender="moss",
                signal_type="ABORT_TASK",
                message=message or text,
                timestamp=time.time(),
                latency_ms=latency_ms,
            )
        return None

    async def query_signals(self, session_id: str, last_read_time: float = 0.0) -> List[Signal]:
        abort = await self.detect_abort(session_id)
        return [abort] if abort and abort.timestamp > last_read_time else []


moss_bus = MossMemoryLayer()
