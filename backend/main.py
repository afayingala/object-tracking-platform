import os
import json
import base64
import uuid
import asyncio
import cv2
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from tracker.pipeline import process_video, preview_frame

app = FastAPI(title="Object Tracking Platform API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5175", "http://localhost:3000"],
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
    confidence: float = 0.60
    max_age: int = 90
    min_hits: int = 3
    selected_boxes: list[dict] = []   # [{x1,y1,x2,y2,class_name}, …] — 1 or 2 entries


async def _broadcast(job_id: str, message: dict):
    for ws in ws_connections.get(job_id, []):
        try:
            await ws.send_json(message)
        except Exception:
            pass


def _run_pipeline(job_id: str, input_path: str, config: ProcessConfig):
    output_video = str(OUTPUT_DIR / f"{job_id}_output.mp4")
    output_json  = str(OUTPUT_DIR / f"{job_id}_data.json")

    def progress_cb(pct: int):
        jobs[job_id]["progress"] = pct
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
            selected_boxes=config.selected_boxes,
            confidence=config.confidence,
            max_age=config.max_age,
            min_hits=config.min_hits,
            progress_callback=progress_cb,
        )
        jobs[job_id]["status"]   = "done"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["summary"]  = {
            "total_frames":            summary["total_frames"],
            "fps":                     summary["fps"],
            "total_objects":           summary["total_objects"],
            "targets":                 summary["targets"],
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
        jobs[job_id]["error"]  = traceback.format_exc()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Object Tracking Platform API v2"}


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}. Use MP4, AVI, MOV, or MKV.")

    video_id  = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{video_id}{ext}"

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return {"video_id": video_id, "filename": file.filename, "path": str(save_path)}


@app.get("/api/preview/{video_id}")
async def preview_video(video_id: str):
    """
    Extract the first frame, run YOLO detection, and return the frame as a
    base64-encoded JPEG together with the list of detected bounding boxes.
    The frontend uses this to let the user click and select target objects.
    """
    matches = list(UPLOAD_DIR.glob(f"{video_id}.*"))
    if not matches:
        raise HTTPException(404, "Video not found. Upload it first.")

    frame, detections = preview_frame(str(matches[0]))

    _, buf     = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    frame_b64  = base64.b64encode(buf.tobytes()).decode("utf-8")

    return JSONResponse({
        "frame":      frame_b64,
        "width":      frame.shape[1],
        "height":     frame.shape[0],
        "detections": detections,
    })


@app.post("/api/process/{video_id}")
async def start_processing(
    video_id: str,
    config: ProcessConfig,
    background_tasks: BackgroundTasks,
):
    if not config.selected_boxes:
        raise HTTPException(400, "No target boxes selected. Select at least one object.")

    matches = list(UPLOAD_DIR.glob(f"{video_id}.*"))
    if not matches:
        raise HTTPException(404, "Video not found. Upload it first.")

    job_id        = str(uuid.uuid4())
    jobs[job_id]  = {"status": "queued", "progress": 0, "summary": None, "error": None}

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


class Zone(BaseModel):
    name: str
    x1: float
    y1: float
    x2: float
    y2: float

class ZoneAnalysisRequest(BaseModel):
    zones: list[Zone]


@app.post("/api/zone-analysis/{job_id}")
def run_zone_analysis(job_id: str, request: ZoneAnalysisRequest):
    path = OUTPUT_DIR / f"{job_id}_data.json"
    if not path.exists():
        raise HTTPException(404, "Tracking data not found.")

    with open(path) as f:
        data = json.load(f)

    fps = data["fps"]
    results = []

    for target in data["targets"]:
        target_zones = []
        for zone in request.zones:
            zx1 = min(zone.x1, zone.x2)
            zy1 = min(zone.y1, zone.y2)
            zx2 = max(zone.x1, zone.x2)
            zy2 = max(zone.y1, zone.y2)

            in_zone = False
            frames_in_zone = 0
            visit_count = 0
            events = []

            for bbox in target["bboxes"]:
                cx, cy = bbox["cx"], bbox["cy"]
                currently_in = zx1 <= cx <= zx2 and zy1 <= cy <= zy2

                if currently_in:
                    frames_in_zone += 1
                    if not in_zone:
                        visit_count += 1
                        in_zone = True
                        events.append({"type": "enter", "frame": bbox["frame"], "time_s": round(bbox["frame"] / fps, 2)})
                else:
                    if in_zone:
                        events.append({"type": "exit", "frame": bbox["frame"], "time_s": round(bbox["frame"] / fps, 2)})
                    in_zone = False

            target_zones.append({
                "zone_name": zone.name,
                "frames_in_zone": frames_in_zone,
                "dwell_seconds": round(frames_in_zone / fps, 2),
                "visit_count": visit_count,
                "events": events,
            })

        results.append({
            "target_id": target["target_id"],
            "class_name": target["class_name"],
            "zones": target_zones,
        })

    return {"fps": fps, "targets": results}


@app.websocket("/ws/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    ws_connections.setdefault(job_id, []).append(websocket)
    try:
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
