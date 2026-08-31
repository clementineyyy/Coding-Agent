from __future__ import annotations

import json
import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os

from harness.config import Config
from harness.webui.stream_agent import StreamAgent

app = FastAPI(title="Coding Agent WebUI")

# Serve static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# In-memory session store
_sessions: dict[str, StreamAgent] = {}
_config = None


@app.get("/")
async def serve_frontend():
    """Serve the main WebUI frontend."""
    return FileResponse(os.path.join(static_dir, "index.html"))


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.load()
    return _config


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/files")
async def list_files(path: str = "."):
    config = get_config()
    base = Path(config.workspace).resolve()
    target = (base / path).resolve()
    if not str(target).startswith(str(base)):
        return JSONResponse({"error": "path outside workspace"}, status_code=403)
    if not target.is_dir():
        return JSONResponse({"error": "not a directory"}, status_code=400)
    entries = []
    for entry in sorted(target.iterdir()):
        entries.append({
            "name": entry.name,
            "type": "directory" if entry.is_dir() else "file",
            "path": str(entry.relative_to(base)),
        })
    return {"entries": entries, "path": path}


@app.get("/api/files/read")
async def read_file(path: str = Query(...)):
    config = get_config()
    base = Path(config.workspace).resolve()
    target = (base / path).resolve()
    if not str(target).startswith(str(base)):
        return JSONResponse({"error": "path outside workspace"}, status_code=403)
    if not target.is_file():
        return JSONResponse({"error": "not a file"}, status_code=400)
    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"path": path, "content": content}


@app.get("/api/config")
async def get_config_endpoint():
    cfg = get_config()
    return {
        "model": cfg.model,
        "base_url": cfg.base_url,
        "max_steps": cfg.max_steps,
        "sandbox_backend": cfg.sandbox_backend,
        "workspace": str(cfg.workspace),
    }


@app.post("/api/config")
async def update_config(data: dict):
    cfg = get_config()
    if "model" in data:
        cfg.model = data["model"]
    if "base_url" in data:
        cfg.base_url = data["base_url"]
    if "max_steps" in data:
        cfg.max_steps = int(data["max_steps"])
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    config = get_config()
    agent = StreamAgent(config)
    session_id = id(agent)
    _sessions[session_id] = agent
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "chat":
                async def push(event: dict):
                    await websocket.send_text(json.dumps(event, ensure_ascii=False))
                try:
                    await agent.chat(msg["content"], push)
                except Exception as e:
                    await push({"type": "error", "content": str(e)})
            elif msg.get("type") == "stop":
                await agent.stop()
    except WebSocketDisconnect:
        pass
    finally:
        _sessions.pop(session_id, None)