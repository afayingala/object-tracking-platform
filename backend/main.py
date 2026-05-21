import os
import uuid
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from tracker.pipeline import process_video

app = FastAPI(title="Object Tracking Platform API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}

# In-memory job store: job_id -> { status, progress, summary, error }
jobs: dict[str, dict] = {}
# WebSocket connections: job_id -> list of WebSocket
ws_connections: dict[str, list] = {}


class ProcessConfig(BaseModel):
    confidence: float = 0.5
    max_age: int = 90
    min_hits: int = 1


async def _broadcast(job_id: str, message: dict):
    for ws in ws_connections.get(job_id, []):
        try:
            await ws.send_json(message)
        except Exception:
            pass


def _run_pipeline(job_id: str, input_path: str, config: ProcessConfig):
    output_video = str(OUTPUT_DIR / f"{job_id}_output.mp4")
    output_json = str(OUTPUT_DIR / f"{job_id}_data.json")

    def progress_cb(pct: int):
        jobs[job_id]["progress"] = pct
        # Schedule broadcast on the event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    _broadcast(job_id, {"type": "progress", "progress": pct}), loop
                )
        except Exception:
            pass

    try:
        jobs[job_id]["status"] = "processing"
        summary = process_video(
            input_path=input_path,
            output_video_path=output_video,
            output_json_path=output_json,
            confidence=config.confidence,
            max_age=config.max_age,
            min_hits=config.min_hits,
            progress_callback=progress_cb,
        )
        jobs[job_id]["status"] = "done"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["summary"] = {
            "total_frames": summary["total_frames"],
            "fps": summary["fps"],
            "total_objects": summary["total_objects"],
            "class_counts": summary["class_counts"],
            "avg_track_duration_frames": summary["avg_track_duration_frames"],
            "processing_time_seconds": summary["processing_time_seconds"],
        }
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    _broadcast(job_id, {"type": "done", "summary": jobs[job_id]["summary"]}),
                    loop,
                )
        except Exception:
            pass
    except Exception:
        import traceback
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = traceback.format_exc()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Object Tracking Platform API"}


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}. Use MP4, AVI, MOV, or MKV.")

    video_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{video_id}{ext}"

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return {"video_id": video_id, "filename": file.filename, "path": str(save_path)}


@app.post("/api/process/{video_id}")
async def start_processing(
    video_id: str,
    config: ProcessConfig,
    background_tasks: BackgroundTasks,
):
    # Find uploaded file
    matches = list(UPLOAD_DIR.glob(f"{video_id}.*"))
    if not matches:
        raise HTTPException(404, "Video not found. Upload it first.")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "progress": 0, "summary": None, "error": None}

    background_tasks.add_task(_run_pipeline, job_id, str(matches[0]), config)

    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return job


@app.get("/api/results/{job_id}")
def get_results(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    if job["status"] != "done":
        raise HTTPException(400, f"Job is not complete. Status: {job['status']}")
    return job["summary"]


@app.get("/api/download/video/{job_id}")
def download_video(job_id: str):
    path = OUTPUT_DIR / f"{job_id}_output.mp4"
    if not path.exists():
        raise HTTPException(404, "Output video not found.")
    return FileResponse(str(path), media_type="video/mp4")


@app.get("/api/download/json/{job_id}")
def download_json(job_id: str):
    path = OUTPUT_DIR / f"{job_id}_data.json"
    if not path.exists():
        raise HTTPException(404, "Output JSON not found.")
    return FileResponse(str(path), media_type="application/json", filename="tracking_data.json")


@app.websocket("/ws/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    ws_connections.setdefault(job_id, []).append(websocket)
    try:
        # Send current status immediately on connect
        job = jobs.get(job_id)
        if job:
            await websocket.send_json({"type": "status", **job})
        while True:
            await asyncio.sleep(1)
            job = jobs.get(job_id)
            if not job:
                break
            if job["status"] in ("done", "error"):
                await websocket.send_json({"type": "status", **job})
                break
    except WebSocketDisconnect:
        pass
    finally:
        ws_connections.get(job_id, []).remove(websocket)
