import os
from typing import Any, Dict, Tuple

from backend import engine
from backend import fusion
from backend import forensics
from backend.utils import sha256_file


def _summarize_c2pa(c2pa: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(c2pa, dict) or not c2pa:
        return {"present": False, "validation": "UNKNOWN"}

    status = c2pa.get("_status")
    if status in {"missing_c2patool", "error", "parse_error"}:
        return {
            "present": False,
            "validation": "UNAVAILABLE",
            "status": status,
        }

    raw = str(c2pa).lower()
    present = "manifest" in raw or "c2pa" in raw
    validation = "UNKNOWN"
    if "valid" in raw or "verified" in raw or "passed" in raw:
        validation = "VALID"
    if "invalid" in raw or "failed" in raw or "broken" in raw:
        validation = "FAILED"

    return {
        "present": present,
        "validation": validation,
        "signer": c2pa.get("signer") if isinstance(c2pa.get("signer"), str) else None,
        "issuer": c2pa.get("issuer") if isinstance(c2pa.get("issuer"), str) else None,
        "status": status,
    }


def _container_anomalies(ffprobe: Dict[str, Any]) -> Dict[str, Any]:
    if not ffprobe or ffprobe.get("_status") in {"missing_ffprobe", "error", "parse_error"}:
        return {
            "status": "NOT_AVAILABLE",
            "notes": "ffprobe unavailable; container anomaly checks skipped.",
        }

    notes = []
    anomalies = []
    streams = ffprobe.get("streams") or []
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    if len(video_streams) > 1:
        anomalies.append("Multiple video streams detected.")
    if not ffprobe.get("format", {}).get("duration"):
        anomalies.append("Missing container duration metadata.")

    status = "ANOMALY" if anomalies else "OK"
    if anomalies:
        notes.extend(anomalies)
    else:
        notes.append("No structural anomalies detected.")
    return {"status": status, "notes": notes, "anomalies": anomalies}


def _one_line_rationale(trust_score: int, label: str, top_reasons: list[str]) -> str:
    reason = top_reasons[0] if top_reasons else "No dominant signals detected."
    return f"{label} trust ({trust_score}/100): {reason}"


def analyze_media_file(path: str, filename: str) -> Dict[str, Any]:
    media_type = engine.detect_media_type(path)
    metadata = engine.extract_exiftool(path)
    ffprobe = engine.extract_ffprobe(path) if media_type == "video" else {}
    c2pa = engine.extract_c2pa(path)

    provenance_state, summary = engine.classify_provenance(c2pa, metadata)
    ai_disclosure = engine.ai_disclosure_from_metadata(metadata)
    transformations = engine.transformation_hints(metadata, ffprobe)
    derived_timeline = engine.derived_timeline(metadata)
    metadata_consistency = engine.metadata_consistency(metadata)
    metadata_completeness = engine.metadata_completeness(metadata)
    tools = engine.tool_versions()

    duration_s = None
    if isinstance(ffprobe, dict):
        duration_raw = (ffprobe.get("format") or {}).get("duration")
        if duration_raw:
            try:
                duration_s = float(duration_raw)
            except ValueError:
                duration_s = None

    if media_type == "image":
        visual = {"type": "image", "results": forensics.image_ela(path)}
    elif media_type == "video":
        visual = {
            "type": "video",
            "results": forensics.video_forensics(path, duration_s=duration_s),
        }
    else:
        visual = {
            "type": "unknown",
            "results": {
                "status": "NOT_AVAILABLE",
                "explanation": "Unsupported media type for visual forensics.",
            },
        }

    container_anomalies = _container_anomalies(ffprobe)
    c2pa_summary = _summarize_c2pa(c2pa)

    fusion_result = fusion.fuse_signals(
        provenance_state=provenance_state,
        c2pa_summary=c2pa_summary,
        metadata_completeness=metadata_completeness,
        metadata_consistency=metadata_consistency,
        ai_disclosure=ai_disclosure,
        transformation_hints=transformations,
        container_anomalies=container_anomalies,
        visual_forensics=visual.get("results", {}),
    )

    trust_score = fusion_result["trust_score"]
    label = fusion_result["label"]
    top_reasons = fusion_result["top_reasons"]

    analysis = {
        "filename": filename,
        "media_type": media_type,
        "bytes": os.path.getsize(path),
        "sha256": sha256_file(path),
        "provenance_state": provenance_state,
        "summary": summary,
        "c2pa": c2pa,
        "c2pa_summary": c2pa_summary,
        "metadata": metadata,
        "ffprobe": ffprobe,
        "ai_disclosure": ai_disclosure,
        "transformations": transformations,
        "derived_timeline": derived_timeline,
        "metadata_consistency": metadata_consistency,
        "metadata_completeness": metadata_completeness,
        "tools": tools,
        "container_anomalies": container_anomalies,
        "forensics": visual,
        "trust_score": trust_score,
        "label": label,
        "top_reasons": top_reasons,
        "signals": fusion_result["signals"],
        "provenance_flags": fusion_result["provenance_flags"],
    }

    analysis["one_line_rationale"] = _one_line_rationale(trust_score, label, top_reasons)
    analysis["raw_extracts"] = {
        "metadata": metadata,
        "ffprobe": ffprobe,
        "c2pa": c2pa,
    }

    return analysis