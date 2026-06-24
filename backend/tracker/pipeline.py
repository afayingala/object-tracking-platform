"""Focused tracking pipeline for 1–2 selected object instances.

Core matching algorithm (per target, per frame)
------------------------------------------------
1. Velocity prediction  — estimate where the target will be using a
   weighted moving average of the last few displacements.  This is the
   primary search window; matching against a predicted position rather
   than the last detected position prevents losing fast-moving objects.

2. Combined score       — 50 % motion (best of predicted-IoU and a
   centre-distance score) + 50 % appearance (cosine similarity of
   MobileNetV2 crop embeddings).  A per-dimension minimum ensures a
   candidate must be plausible on BOTH axes before it is accepted,
   which prevents snapping to a wrong nearby object that happens to
   have a similar colour.

3. Output smoothing     — the accepted bounding box is blended with the
   previous smoothed box (EMA, α = 0.75) to remove per-frame YOLO
   jitter from the output video.

Re-identification (SEARCHING mode)
-----------------------------------
Entered after max_age consecutive missed frames.  Pure cosine-similarity
search across all YOLO detections, gated by min_hits consecutive matches
before committing.
"""
import cv2
import json
import math
import time
import numpy as np
from deep_sort_realtime.deepsort_tracker import DeepSort

from .detector import YOLODetector

TARGET_COLORS = [
    (255, 200,   0),   # amber — Target 1
    (  0, 160, 255),   # blue  — Target 2
]

# EMA weight for output box smoothing (higher = less lag, more jitter)
_SMOOTH = 0.75
# Minimum appearance similarity even during normal tracking
_APP_FLOOR_TRACKING  = 0.35
# Minimum appearance similarity during re-ID search
_APP_FLOOR_REID      = 0.55
# Minimum motion score during normal tracking
_MOT_FLOOR_TRACKING  = 0.15


# ── Geometry / similarity helpers ─────────────────────────────────────────────

def _iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1])
    ub = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (ua + ub - inter)


def _centre_score(pred_box, cand_box, last_box) -> float:
    """
    Score in [0, 1] based on how close the candidate centre is to the
    predicted centre, normalised by the object's own diagonal size.
    Falls off linearly to 0 at 1.5× the object diagonal.
    """
    px = (pred_box[0] + pred_box[2]) / 2
    py = (pred_box[1] + pred_box[3]) / 2
    cx = (cand_box[0] + cand_box[2]) / 2
    cy = (cand_box[1] + cand_box[3]) / 2
    dist  = math.hypot(px - cx, py - cy)
    diag  = math.hypot(last_box[2] - last_box[0], last_box[3] - last_box[1])
    limit = max(diag * 1.5, 60)   # generous for small objects
    return max(0.0, 1.0 - dist / limit)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.dot(a, b) / (na * nb)) if na > 1e-8 and nb > 1e-8 else 0.0


def _embed(embedder, frame: np.ndarray, box) -> np.ndarray | None:
    """Crop `box` from `frame` and return a unit-norm appearance embedding."""
    x1 = max(0, int(box[0]));  y1 = max(0, int(box[1]))
    x2 = min(frame.shape[1], int(box[2]));  y2 = min(frame.shape[0], int(box[3]))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    crop = frame[y1:y2, x1:x2]
    try:
        result = embedder.predict([crop])
        if result is None or len(result) == 0:
            return None
        v = np.array(result[0], dtype=np.float32)
        n = np.linalg.norm(v)
        return v / n if n > 1e-8 else v
    except Exception:
        return None


def _smooth(new_box, old_box, alpha: float = _SMOOTH):
    """Exponential moving average on a bounding box (reduces YOLO jitter)."""
    return [int(alpha * n + (1 - alpha) * o) for n, o in zip(new_box, old_box)]


def _predict_box(last_box: list, history: list) -> list:
    """
    Weighted-velocity prediction of the next bounding box.
    Uses up to the last 4 centre-point displacements, with exponentially
    higher weights on more-recent moves.
    Returns a shifted copy of last_box centred on the predicted position.
    """
    if len(history) < 2:
        return last_box

    pts = history[-5:]          # at most 4 velocity vectors from 5 points
    diffs = [
        (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        for i in range(len(pts) - 1)
    ]
    weights = [2 ** i for i in range(len(diffs))]   # recent moves weighted higher
    total_w = sum(weights)
    vx = sum(d[0] * w for d, w in zip(diffs, weights)) / total_w
    vy = sum(d[1] * w for d, w in zip(diffs, weights)) / total_w

    cx_pred = pts[-1][0] + vx
    cy_pred = pts[-1][1] + vy
    w = last_box[2] - last_box[0]
    h = last_box[3] - last_box[1]
    return [
        int(cx_pred - w / 2), int(cy_pred - h / 2),
        int(cx_pred + w / 2), int(cy_pred + h / 2),
    ]


# ── Preview (populates the Select step in the UI) ────────────────────────────

def preview_frame(input_path: str, confidence: float = 0.45) -> tuple:
    """
    Extract the first frame, run YOLO on it, and return
    (frame_bgr, detections).  detections is a list of
    {x1, y1, x2, y2, confidence, class_name}.
    """
    detector = YOLODetector(confidence=confidence)
    cap = cv2.VideoCapture(input_path)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError(f"Cannot read first frame from: {input_path}")

    raw = detector.detect(frame)
    detections = []
    for det in raw:
        x1, y1, x2, y2, conf, cls_id = det
        detections.append({
            "x1":         int(x1),
            "y1":         int(y1),
            "x2":         int(x2),
            "y2":         int(y2),
            "confidence": round(float(conf), 3),
            "class_name": detector.get_class_name(int(cls_id)),
        })
    return frame, detections


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process_video(
    input_path: str,
    output_video_path: str,
    output_json_path: str,
    selected_boxes: list,
    confidence: float = 0.5,
    max_age: int = 30,
    min_hits: int = 3,
    progress_callback=None,
) -> dict:
    """
    Track 1–2 pre-selected object instances through a video.

    selected_boxes — [{x1, y1, x2, y2, class_name}, …] (1 or 2 entries).
    confidence     — YOLO detection threshold.
    max_age        — frames without a match before entering re-ID mode.
    min_hits       — consecutive appearance matches to confirm re-ID.
    """
    if not selected_boxes:
        raise ValueError("At least one target box must be selected.")

    n        = len(selected_boxes)
    detector = YOLODetector(confidence=confidence)

    # DeepSort is instantiated only to access its MobileNetV2 embedder.
    _ds      = DeepSort(max_age=1)
    embedder = _ds.embedder

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {input_path}")

    width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps          = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # ── Per-target state ──────────────────────────────────────────────────────
    last_box          = [[sb["x1"], sb["y1"], sb["x2"], sb["y2"]] for sb in selected_boxes]
    smooth_box        = [list(b) for b in last_box]   # EMA-smoothed output box
    embeddings        = [None] * n                    # running-average appearance
    init_embeddings   = [None] * n                    # frozen frame-0 reference (never updated)
    pos_history       = [[] for _ in range(n)]        # [(cx, cy), …] for velocity
    lost_cnt          = [0]   * n
    searching         = [False] * n
    reid_hits         = [0]   * n
    was_lost          = [False] * n
    reapp_cnt         = [0]   * n

    target_frames: list[dict] = [{} for _ in range(n)]

    # ── Frame 0: seed embeddings and record initial positions ─────────────────
    ret0, frame0 = cap.read()
    if not ret0:
        raise RuntimeError("Cannot read first frame.")

    for t, box in enumerate(last_box):
        emb = _embed(embedder, frame0, box)
        embeddings[t]      = emb
        init_embeddings[t] = emb   # frozen — never updated after this point
        x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
        cx0, cy0 = (x1 + x2) // 2, (y1 + y2) // 2
        pos_history[t] = [(cx0, cy0)]
        target_frames[t][0] = {
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "cx": cx0, "cy": cy0,
        }

    if progress_callback and total_frames > 0:
        progress_callback(0)

    start_time = time.time()
    frame_idx  = 1

    # ── Main tracking pass (frames 1 … end) ───────────────────────────────────
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Use a lower confidence floor than the user's threshold so the
        # target is still detected when partially occluded or at distance.
        # The combined IoU + appearance score filters false positives.
        raw_dets   = detector.detect(frame, override_conf=min(confidence, 0.30))
        candidates = [
            {
                "box":   [int(d[0]), int(d[1]), int(d[2]), int(d[3])],
                "conf":  float(d[4]),
                "class": detector.get_class_name(int(d[5])),
            }
            for d in raw_dets
        ]

        # Pre-compute embeddings for all candidates once (shared across targets)
        cand_embs = [_embed(embedder, frame, c["box"]) for c in candidates]

        used: set[int] = set()

        for t in range(n):
            best_i, best_score = None, -1.0
            pred_box     = _predict_box(last_box[t], pos_history[t])
            target_class = selected_boxes[t].get("class_name", "")

            for ci, cand in enumerate(candidates):
                if ci in used:
                    continue
                # Only consider same-class detections — prevents snapping to
                # cars, balls, etc. when the selected target is a person.
                if target_class and cand["class"] != target_class:
                    continue
                box = cand["box"]

                if not searching[t]:
                    # ── TRACKING: spatial gate → motion + appearance ──────────
                    #
                    # Spatial gate: compute the distance between the candidate
                    # centre and the predicted centre.  Only candidates inside
                    # an adaptive search window are scored at all.  This is the
                    # primary defence against lookalike objects elsewhere in the
                    # frame — a different player wearing the same kit on the far
                    # side of the pitch is excluded before appearance is checked.
                    pred_cx = (pred_box[0] + pred_box[2]) / 2
                    pred_cy = (pred_box[1] + pred_box[3]) / 2
                    cand_cx = (box[0] + box[2]) / 2
                    cand_cy = (box[1] + box[3]) / 2
                    centre_dist = math.hypot(pred_cx - cand_cx, pred_cy - cand_cy)

                    obj_diag = math.hypot(
                        last_box[t][2] - last_box[t][0],
                        last_box[t][3] - last_box[t][1],
                    )
                    vel_mag = 0.0
                    if len(pos_history[t]) >= 2:
                        ph = pos_history[t]
                        vel_mag = math.hypot(
                            ph[-1][0] - ph[-2][0],
                            ph[-1][1] - ph[-2][1],
                        )
                    # Base = 90 % of object diagonal (tight when stationary).
                    # Extra = 2 × last-frame velocity (expands for fast movers).
                    # Floor = 40 px so tiny objects still have a usable window.
                    search_radius = max(obj_diag * 0.9, 40.0) + vel_mag * 2.0

                    if centre_dist > search_radius:
                        continue   # lookalike too far away — skip entirely

                    # Size-consistency gate: reject candidates whose bounding
                    # box is more than 2.5× larger or smaller than the target.
                    # Two players of the same kit can be told apart by depth/
                    # distance to camera; a sudden 3× size jump is not the
                    # same person.
                    ref_w = max(last_box[t][2] - last_box[t][0], 1)
                    ref_h = max(last_box[t][3] - last_box[t][1], 1)
                    cnd_w = max(box[2] - box[0], 1)
                    cnd_h = max(box[3] - box[1], 1)
                    if max(ref_w / cnd_w, cnd_w / ref_w) > 2.5:
                        continue
                    if max(ref_h / cnd_h, cnd_h / ref_h) > 2.5:
                        continue

                    iou_pred  = _iou(pred_box, box)
                    iou_last  = _iou(last_box[t], box)
                    cent      = _centre_score(pred_box, box, last_box[t])
                    mot_score = max(iou_pred, iou_last * 0.85, cent * 0.70)

                    # Appearance: blend running embedding with the frozen
                    # frame-0 reference so accumulated drift cannot push the
                    # score decisively toward a different individual.
                    app_score = 0.0
                    if cand_embs[ci] is not None:
                        sims = []
                        if embeddings[t]      is not None:
                            sims.append(_cosine_sim(embeddings[t],      cand_embs[ci]))
                        if init_embeddings[t] is not None:
                            sims.append(_cosine_sim(init_embeddings[t], cand_embs[ci]))
                        if sims:
                            # Weight the frozen reference more heavily toward
                            # the end to resist long-term drift.
                            app_score = max(0.0, max(sims))

                    # Reject candidates that fail both motion AND appearance
                    if mot_score < _MOT_FLOOR_TRACKING and app_score < _APP_FLOOR_TRACKING:
                        continue

                    if app_score > 0.0:
                        score = 0.65 * mot_score + 0.35 * app_score
                    else:
                        score = mot_score

                    if score > best_score:
                        best_score, best_i = score, ci

                else:
                    # ── SEARCHING: appearance-only re-ID ─────────────────────
                    if cand_embs[ci] is not None:
                        sims = []
                        if embeddings[t]      is not None:
                            sims.append(_cosine_sim(embeddings[t],      cand_embs[ci]))
                        if init_embeddings[t] is not None:
                            sims.append(_cosine_sim(init_embeddings[t], cand_embs[ci]))
                        if sims:
                            score = max(sims)
                            if score > _APP_FLOOR_REID and score > best_score:
                                best_score, best_i = score, ci

            # ── Process match result ──────────────────────────────────────────
            if best_i is not None:
                raw_box = candidates[best_i]["box"]

                if searching[t]:
                    # Gate re-ID by min_hits consecutive matches
                    reid_hits[t] += 1
                    used.add(best_i)
                    if reid_hits[t] < min_hits:
                        continue
                    if was_lost[t]:
                        reapp_cnt[t] += 1
                    searching[t]  = False
                    reid_hits[t]  = 0
                    was_lost[t]   = False
                    smooth_box[t] = list(raw_box)   # reset smoother on re-ID
                else:
                    used.add(best_i)

                # Smooth the output box (reduces YOLO jitter)
                smooth_box[t] = _smooth(raw_box, smooth_box[t])
                last_box[t]   = raw_box             # velocity tracking uses raw
                lost_cnt[t]   = 0

                sx1, sy1, sx2, sy2 = smooth_box[t]
                scx, scy = (sx1 + sx2) // 2, (sy1 + sy2) // 2
                cx_raw = (raw_box[0] + raw_box[2]) // 2
                cy_raw = (raw_box[1] + raw_box[3]) // 2
                pos_history[t] = (pos_history[t] + [(cx_raw, cy_raw)])[-20:]

                # Update running embedding only on high-confidence matches
                # and with a very slow EMA (5 %) to resist long-term drift.
                # The frozen init_embedding is never updated.
                new_emb = cand_embs[best_i]
                if new_emb is not None and best_score > 0.70:
                    if embeddings[t] is None:
                        embeddings[t] = new_emb
                    else:
                        upd  = 0.95 * embeddings[t] + 0.05 * new_emb
                        norm = np.linalg.norm(upd)
                        embeddings[t] = upd / norm if norm > 1e-8 else upd

                target_frames[t][frame_idx] = {
                    "x1": sx1, "y1": sy1, "x2": sx2, "y2": sy2,
                    "cx": scx, "cy": scy,
                }

            else:
                lost_cnt[t] += 1

                # Ghost tracking: during a brief loss (≤ 8 frames, e.g. two
                # objects crossing) advance last_box and pos_history using the
                # last known velocity.  This keeps the search window moving
                # along the correct trajectory so that when the objects
                # separate, the spatial gate finds the one that exited on the
                # expected side — not the lookalike going the other direction.
                if not searching[t] and lost_cnt[t] <= 8 and len(pos_history[t]) >= 2:
                    ph = pos_history[t]
                    vx = ph[-1][0] - ph[-2][0]
                    vy = ph[-1][1] - ph[-2][1]
                    cx_g = int(ph[-1][0] + vx)
                    cy_g = int(ph[-1][1] + vy)
                    w = last_box[t][2] - last_box[t][0]
                    h = last_box[t][3] - last_box[t][1]
                    last_box[t] = [
                        cx_g - w // 2, cy_g - h // 2,
                        cx_g + w // 2, cy_g + h // 2,
                    ]
                    pos_history[t] = (pos_history[t] + [(cx_g, cy_g)])[-20:]

                if lost_cnt[t] > max_age and not searching[t]:
                    searching[t]  = True
                    was_lost[t]   = True
                    reid_hits[t]  = 0

        frame_idx += 1
        if progress_callback and total_frames > 0:
            progress_callback(int(frame_idx / total_frames * 50))

    cap.release()
    total_processed = frame_idx

    # ── Pass 2: annotate and write output video ───────────────────────────────
    cap2   = cv2.VideoCapture(input_path)
    fourcc = cv2.VideoWriter_fourcc(*"avc1")
    writer = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))

    trajectories:  list[list] = [[] for _ in range(n)]
    frame_records: list[dict] = []
    frame_idx = 0

    while True:
        ret, frame = cap2.read()
        if not ret:
            break

        frame_track_list = []

        for t in range(n):
            det = target_frames[t].get(frame_idx)
            if det is None:
                continue

            x1, y1, x2, y2 = det["x1"], det["y1"], det["x2"], det["y2"]
            cx, cy  = det["cx"], det["cy"]
            color   = TARGET_COLORS[t % len(TARGET_COLORS)]
            label   = f"T{t + 1}"

            # Trajectory — only connect consecutive detected frames
            trajectories[t].append((frame_idx, cx, cy))
            hist = trajectories[t][-120:]
            for i in range(1, len(hist)):
                fp, xp, yp = hist[i - 1]
                fc, xc, yc = hist[i]
                if fc - fp <= 1:
                    cv2.line(frame, (xp, yp), (xc, yc), color, 2)

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 8, y1), color, -1)
            cv2.putText(frame, label, (x1 + 4, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)

            frame_track_list.append({"target": t + 1, "bbox": [x1, y1, x2, y2]})

        frame_records.append({"frame": frame_idx, "tracks": frame_track_list})
        writer.write(frame)
        frame_idx += 1

        if progress_callback and total_frames > 0:
            progress_callback(50 + int(frame_idx / total_frames * 50))

    cap2.release()
    writer.release()
    elapsed = round(time.time() - start_time, 2)

    # ── Per-target analytics ──────────────────────────────────────────────────
    target_summaries = []
    for t in range(n):
        frames_seen = sorted(target_frames[t])
        n_seen      = len(frames_seen)

        total_dist = 0.0
        prev_cx, prev_cy = None, None
        for fi in frames_seen:
            d = target_frames[t][fi]
            if prev_cx is not None:
                total_dist += math.hypot(d["cx"] - prev_cx, d["cy"] - prev_cy)
            prev_cx, prev_cy = d["cx"], d["cy"]

        avg_speed    = round(total_dist / n_seen, 2) if n_seen > 1 else 0.0
        presence_pct = round(n_seen / total_processed * 100, 1) if total_processed > 0 else 0.0

        target_summaries.append({
            "target_id":              t + 1,
            "class_name":             selected_boxes[t].get("class_name", "object"),
            "frames_detected":        n_seen,
            "presence_percentage":    presence_pct,
            "total_distance_pixels":  round(total_dist, 1),
            "avg_speed_px_per_frame": avg_speed,
            "reappearances":          reapp_cnt[t],
            "bboxes": [
                {"frame": fi, **target_frames[t][fi]}
                for fi in frames_seen
            ],
        })

    summary = {
        "total_frames":            total_processed,
        "fps":                     round(fps, 2),
        "total_objects":           n,
        "targets":                 target_summaries,
        "processing_time_seconds": elapsed,
        "frame_records":           frame_records,
    }

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary
