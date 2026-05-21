"""Video processing pipeline: YOLOv8 detection + Deep SORT tracking."""
# pylint: disable=no-member  # cv2 is a C extension; Pylint cannot introspect its members
import cv2
import json
import math
import time
from deep_sort_realtime.deepsort_tracker import DeepSort

from .detector import YOLODetector

# Palette of distinct colors for track IDs
COLORS = [
    (255, 56, 56), (255, 157, 151), (255, 112, 31), (255, 178, 29),
    (207, 210, 49), (72, 249, 10), (146, 204, 23), (61, 219, 134),
    (26, 147, 52), (0, 212, 187), (44, 153, 168), (0, 194, 255),
    (52, 69, 147), (100, 115, 255), (0, 24, 236), (132, 56, 255),
    (82, 0, 133), (203, 56, 255), (255, 149, 200), (255, 55, 199),
]


def _color_for_id(track_id) -> tuple:
    return COLORS[int(track_id) % len(COLORS)]


# Sports ball is hard to detect during motion blur; run YOLO at this floor
# for that class while keeping the user's threshold for everything else.
_BALL_CONF_FLOOR = 0.30

# Classes where only one physical object can exist at any moment.
# The stitch ignores spatial distance for these — a kicked ball can reappear
# anywhere — and the detector caps them at one detection per frame to prevent
# false positives from spawning phantom parallel tracks.
_SINGLE_INSTANCE_CLASSES = {"sports ball", "frisbee"}


def _stitch_tracks(
    track_records: dict,
    gap_tolerance: int,
    max_pixel_dist: float,
    overlap_tolerance: int = 0,
) -> dict:
    """
    Greedy chain stitching: merge fragment tracks of the same class that are
    within gap_tolerance frames (forward) or overlap_tolerance frames (backward)
    and within max_pixel_dist pixels of the predecessor's last known position.

    overlap_tolerance allows merging when a new Deep SORT track is confirmed
    while the old track is still coasting (small negative gap).

    Returns id_remap: {raw_track_id -> canonical_track_id}.
    Canonical ID is always the earliest fragment in each chain.
    """
    if not track_records:
        return {}

    # Group fragments by class
    by_class: dict[str, list] = {}
    for t in track_records.values():
        by_class.setdefault(t["class"], []).append(t)

    # Start with identity mapping
    id_remap: dict[int, int] = {tid: tid for tid in track_records}

    for cls_tracks in by_class.values():
        # Process in chronological order
        cls_tracks.sort(key=lambda t: t["first_frame"])

        # Single-instance detection: if no two raw tracks of this class ever
        # overlap in time, only one physical object can exist at any moment.
        # For such classes (e.g. a sports ball) the object may reappear anywhere
        # in the frame after a kick or occlusion, so spatial distance is not a
        # meaningful constraint — skip it and stitch on time alone.
        is_single_instance = True
        for _i in range(len(cls_tracks)):
            for _j in range(_i + 1, len(cls_tracks)):
                a, b = cls_tracks[_i], cls_tracks[_j]
                if max(a["first_frame"], b["first_frame"]) <= min(a["last_frame"], b["last_frame"]):
                    is_single_instance = False
                    break
            if not is_single_instance:
                break
        # Also force single-instance for known classes: a kicked ball can
        # reappear anywhere, so spatial distance is never a valid stitch constraint.
        force_single = bool(cls_tracks) and cls_tracks[0]["class"] in _SINGLE_INSTANCE_CLASSES
        if is_single_instance or force_single:
            # One physical object: no distance constraint, full gap budget.
            effective_dist = float("inf")
            effective_gap = gap_tolerance
        else:
            # Multiple objects of the same class share the pitch.  A generous
            # gap or distance allows fragments from *different* people to be
            # merged when they happen to be near the same position.
            # Tight gap  = only stitch brief occlusions (≤ max_age frames).
            # Tight dist = 10 % of diagonal keeps spatially close strangers apart.
            effective_dist = max_pixel_dist * 0.4
            effective_gap = max(gap_tolerance // 10, 5)

        # Live chain metadata: canonical_id -> {last_frame, last_cx, last_cy}
        # Updated after every merge so transitive chains work correctly.
        chain: dict[int, dict] = {
            t["id"]: {
                "last_frame": t["last_frame"],
                "last_cx": t["bboxes"][-1]["cx"] if t["bboxes"] else 0,
                "last_cy": t["bboxes"][-1]["cy"] if t["bboxes"] else 0,
            }
            for t in cls_tracks
        }

        for j in range(1, len(cls_tracks)):
            tb = cls_tracks[j]
            first_cx = tb["bboxes"][0]["cx"] if tb["bboxes"] else 0
            first_cy = tb["bboxes"][0]["cy"] if tb["bboxes"] else 0

            best_root = None
            best_last_frame = -1

            # Search all earlier fragments for the best predecessor
            for i in range(j):
                ta = cls_tracks[i]
                root_a = id_remap[ta["id"]]
                meta = chain[root_a]

                gap = tb["first_frame"] - meta["last_frame"]
                if gap > effective_gap:
                    continue
                # For single-instance classes any backward overlap is a tracking
                # artifact — there is only one physical object, so waive the limit.
                if not force_single and gap < -overlap_tolerance:
                    continue

                dist = math.hypot(meta["last_cx"] - first_cx, meta["last_cy"] - first_cy)
                if dist <= effective_dist and meta["last_frame"] > best_last_frame:
                    best_last_frame = meta["last_frame"]
                    best_root = root_a

            if best_root is not None:
                # Merge tb into best_root chain
                id_remap[tb["id"]] = best_root
                # Update canonical metadata so future fragments can extend this chain
                if tb["last_frame"] > chain[best_root]["last_frame"]:
                    chain[best_root]["last_frame"] = tb["last_frame"]
                    if tb["bboxes"]:
                        chain[best_root]["last_cx"] = tb["bboxes"][-1]["cx"]
                        chain[best_root]["last_cy"] = tb["bboxes"][-1]["cy"]

    return id_remap


def process_video(
    input_path: str,
    output_video_path: str,
    output_json_path: str,
    confidence: float = 0.5,
    max_age: int = 30,
    min_hits: int = 3,
    progress_callback=None,
) -> dict:
    """
    Full detection + tracking pipeline with post-hoc track stitching.
    Pass 1: run YOLO + Deep SORT, collect raw per-frame detections.
    Stitch: merge fragmented tracks of the same class via greedy chain matching.
    Pass 2: redraw video with canonical (stitched) IDs and trajectories.
    Returns a summary dict with stats.
    """
    detector = YOLODetector(confidence=confidence)
    tracker = DeepSort(max_age=max_age, n_init=min_hits)

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {input_path}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # ── Pass 1: detect + track, collect raw data ──────────────────────────────
    # raw_frames: frame_idx -> list of {id, class, x1,y1,x2,y2, cx,cy}
    raw_frames: dict[int, list] = {}
    track_records: dict[int, dict] = {}

    start_time = time.time()
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Run at ball-sensitive floor so motion-blur frames still reach Deep SORT;
        # non-ball classes are filtered back up to the user's threshold.
        detections_raw = detector.detect(frame, override_conf=min(confidence, _BALL_CONF_FLOOR))

        ds_input = []
        _best_single: dict[str, tuple] = {}
        for det in detections_raw:
            x1, y1, x2, y2, conf, cls_id = det
            class_name = detector.get_class_name(int(cls_id))
            if conf < confidence and class_name not in _SINGLE_INSTANCE_CLASSES:
                continue
            w, h = x2 - x1, y2 - y1
            entry = ([x1, y1, w, h], conf, class_name)
            if class_name in _SINGLE_INSTANCE_CLASSES:
                # Keep only the highest-confidence detection per frame so
                # misidentified objects never create phantom parallel tracks.
                if class_name not in _best_single or conf > _best_single[class_name][1]:
                    _best_single[class_name] = entry
            else:
                ds_input.append(entry)
        ds_input.extend(_best_single.values())

        tracks = tracker.update_tracks(ds_input, frame=frame)

        frame_dets = []
        for track in tracks:
            if not track.is_confirmed():
                continue
            if track.time_since_update > 0:
                continue

            track_id = int(track.track_id)
            ltrb = track.to_ltrb()
            x1, y1, x2, y2 = int(ltrb[0]), int(ltrb[1]), int(ltrb[2]), int(ltrb[3])
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            class_name = track.get_det_class() or "object"

            frame_dets.append({
                "id": track_id, "class": class_name,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "cx": cx, "cy": cy,
            })

            if track_id not in track_records:
                track_records[track_id] = {
                    "id": track_id, "class": class_name,
                    "first_frame": frame_idx, "last_frame": frame_idx,
                    "bboxes": [],
                }
            track_records[track_id]["last_frame"] = frame_idx
            track_records[track_id]["bboxes"].append({
                "frame": frame_idx,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "cx": cx, "cy": cy,
            })

        raw_frames[frame_idx] = frame_dets
        frame_idx += 1

        if progress_callback and total_frames > 0:
            # Pass 1 = first 50 % of reported progress
            progress_callback(int(frame_idx / total_frames * 50))

    cap.release()

    # ── Stitch ────────────────────────────────────────────────────────────────
    # gap_tolerance: 10× max_age covers occlusions up to ~10 s at 30 fps.
    # pixel_dist: 25 % of the diagonal — allows fast-moving objects to reappear
    # nearby without merging spatially distant distinct objects of the same class.
    # overlap_tolerance: 3 frames handles detection jitter where Deep SORT
    # confirms a new track just before the old coast window fully expires.
    stitch_gap = max_age * 10
    stitch_dist = 0.25 * math.hypot(width, height)
    id_remap = _stitch_tracks(track_records, stitch_gap, stitch_dist, overlap_tolerance=3)

    # ── Pass 2: redraw video with canonical IDs ───────────────────────────────
    cap2 = cv2.VideoCapture(input_path)
    fourcc = cv2.VideoWriter_fourcc(*"avc1")
    writer = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))

    # Trajectory history keyed by canonical ID: id -> [(frame_idx, cx, cy)]
    trajectories: dict[int, list] = {}
    # Canonical track records (for summary)
    canonical_records: dict[int, dict] = {}
    frame_records: list[dict] = []

    frame_idx = 0
    while True:
        ret, frame = cap2.read()
        if not ret:
            break

        frame_dets = raw_frames.get(frame_idx, [])
        frame_track_list = []

        for det in frame_dets:
            raw_id = det["id"]
            can_id = id_remap.get(raw_id, raw_id)
            x1, y1, x2, y2 = det["x1"], det["y1"], det["x2"], det["y2"]
            cx, cy = det["cx"], det["cy"]
            class_name = det["class"]
            color = _color_for_id(can_id)

            # Accumulate trajectory
            if can_id not in trajectories:
                trajectories[can_id] = []
            trajectories[can_id].append((frame_idx, cx, cy))

            # Accumulate canonical record
            if can_id not in canonical_records:
                canonical_records[can_id] = {
                    "id": can_id, "class": class_name,
                    "first_frame": frame_idx, "last_frame": frame_idx,
                    "bboxes": [],
                }
            canonical_records[can_id]["last_frame"] = frame_idx
            canonical_records[can_id]["bboxes"].append({
                "frame": frame_idx,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "cx": cx, "cy": cy,
            })

            # Draw bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # Draw label
            label = f"ID:{can_id} {class_name}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
            cv2.putText(frame, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

            # Draw trajectory — skip segments where frames are not consecutive
            hist = trajectories[can_id][-120:]
            for i in range(1, len(hist)):
                f_prev, xp, yp = hist[i - 1]
                f_curr, xc, yc = hist[i]
                if f_curr - f_prev <= 1:
                    cv2.line(frame, (xp, yp), (xc, yc), color, 2)

            frame_track_list.append({
                "id": can_id, "class": class_name,
                "bbox": [x1, y1, x2, y2],
            })

        frame_records.append({"frame": frame_idx, "tracks": frame_track_list})
        writer.write(frame)
        frame_idx += 1

        if progress_callback and total_frames > 0:
            # Pass 2 = second 50 % of reported progress
            progress_callback(50 + int(frame_idx / total_frames * 50))

    cap2.release()
    writer.release()

    elapsed = round(time.time() - start_time, 2)

    # Summary uses canonical records (post-stitch)
    class_counts: dict[str, int] = {}
    for rec in canonical_records.values():
        c = rec["class"]
        class_counts[c] = class_counts.get(c, 0) + 1

    durations = [
        r["last_frame"] - r["first_frame"] + 1
        for r in canonical_records.values()
    ]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0

    summary = {
        "total_frames": frame_idx,
        "fps": round(fps, 2),
        "total_objects": len(canonical_records),
        "class_counts": class_counts,
        "avg_track_duration_frames": avg_duration,
        "processing_time_seconds": elapsed,
        "tracks": list(canonical_records.values()),
        "frame_records": frame_records,
    }

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary
