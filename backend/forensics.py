from __future__ import annotations

import io
import math
import os
import tempfile
from typing import Any, Dict, List, Optional

from PIL import Image, ImageChops, ImageStat

from backend.utils import run_cmd, which

ARTIFACT_DIR = os.getenv("TRUTHSIG_ARTIFACT_DIR", "/tmp/truthsig_artifacts")


def _ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _safe_mean(stat: ImageStat.Stat) -> float:
    if not stat.mean:
        return 0.0
    return float(sum(stat.mean) / len(stat.mean))


def image_ela(path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    try:
        _ensure_dir(ARTIFACT_DIR)
        out_dir = _ensure_dir(output_dir or tempfile.mkdtemp(prefix="ela_", dir=ARTIFACT_DIR))
        with Image.open(path) as img:
            img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=85)
            buffer.seek(0)
            with Image.open(buffer) as recompressed:
                recompressed = recompressed.convert("RGB")
                diff = ImageChops.difference(img, recompressed)
                diff = diff.point(lambda x: min(255, x * 10))
                heatmap_path = os.path.join(out_dir, "ela_heatmap.png")
                diff.save(heatmap_path, "PNG")

                stat = ImageStat.Stat(diff)
                mean_diff = _safe_mean(stat)

        status = "SUSPICIOUS" if mean_diff >= 25.0 else "CLEAR"
        summary = f"ELA mean diff intensity: {mean_diff:.1f}"
        suspicious_note = (
            "Higher ELA intensity can indicate edits or heavy compression regions."
        )

        return {
            "status": status,
            "heatmap_path": heatmap_path,
            "heatmap_summary": summary,
            "suspicious_regions_note": suspicious_note,
            "mean_diff": mean_diff,
        }
    except Exception as exc:
        return {
            "status": "ERROR",
            "explanation": f"ELA failed: {exc}",
        }


def _duration_from_ffprobe(path: str) -> Optional[float]:
    if not which("ffprobe"):
        return None
    code, out, _ = run_cmd(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        timeout=20,
    )
    if code != 0 or not out:
        return None
    try:
        return float(out.strip())
    except ValueError:
        return None


def video_forensics(
    path: str,
    *,
    duration_s: Optional[float] = None,
    frame_count: int = 12,
) -> Dict[str, Any]:
    if not which("ffmpeg"):
        return {
            "status": "NOT_AVAILABLE",
            "explanation": "ffmpeg is not available on the server.",
        }

    duration = duration_s or _duration_from_ffprobe(path)
    if not duration or duration <= 0:
        return {
            "status": "NOT_AVAILABLE",
            "explanation": "Video duration unavailable; cannot sample frames reliably.",
        }

    _ensure_dir(ARTIFACT_DIR)
    out_dir = _ensure_dir(tempfile.mkdtemp(prefix="video_frames_", dir=ARTIFACT_DIR))
    step = duration / (frame_count + 1)
    timestamps = [step * (i + 1) for i in range(frame_count)]

    frame_thumbnails: List[str] = []
    frame_scores: List[float] = []
    flagged_frames: List[Dict[str, Any]] = []
    timeline_markers: List[Dict[str, Any]] = []

    for idx, ts in enumerate(timestamps):
        frame_path = os.path.join(out_dir, f"frame_{idx:02d}.jpg")
        code, _, err = run_cmd(
            [
                "ffmpeg",
                "-ss",
                f"{ts:.2f}",
                "-i",
                path,
                "-frames:v",
                "1",
                "-q:v",
                "2",
                frame_path,
                "-y",
            ],
            timeout=30,
        )
        if code != 0 or not os.path.exists(frame_path):
            timeline_markers.append(
                {"time_s": ts, "status": "ERROR", "note": err[:200] if err else "Frame extraction failed."}
            )
            continue

        frame_thumbnails.append(frame_path)
        ela = image_ela(frame_path, output_dir=out_dir)
        mean_diff = float(ela.get("mean_diff") or 0.0)
        frame_scores.append(mean_diff)
        marker = {
            "time_s": ts,
            "status": "OK",
            "score": mean_diff,
            "heatmap_path": ela.get("heatmap_path"),
            "thumbnail_path": frame_path,
        }
        timeline_markers.append(marker)

        if mean_diff >= 25.0:
            flagged_frames.append(
                {
                    "index": idx,
                    "time_s": ts,
                    "score": mean_diff,
                    "thumbnail_path": frame_path,
                    "heatmap_path": ela.get("heatmap_path"),
                }
            )

    flagged_frames = sorted(flagged_frames, key=lambda f: f.get("score", 0), reverse=True)[:3]

    avg_score = sum(frame_scores) / len(frame_scores) if frame_scores else 0.0
    status = "SUSPICIOUS" if avg_score >= 25.0 else "CLEAR"

    return {
        "status": status,
        "frame_thumbnails": frame_thumbnails,
        "frame_scores": frame_scores,
        "flagged_frames": flagged_frames,
        "timeline_markers": timeline_markers,
        "summary": f"Average ELA score across sampled frames: {avg_score:.1f}",
    }