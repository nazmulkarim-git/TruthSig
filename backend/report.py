from __future__ import annotations

import datetime
import hashlib
import json
import os
from typing import Any, Dict, List, Tuple

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image


def _safe_text(v: Any, max_len: int = 400) -> str:
    if v is None:
        return ""
    s = str(v)
    s = s.replace("\x00", "").strip()
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


def _as_dict(maybe: Any) -> Dict[str, Any]:
    if maybe is None:
        return {}
    if isinstance(maybe, dict):
        return maybe
    if isinstance(maybe, str):
        try:
            obj = json.loads(maybe)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _hash_result_for_id(result: Dict[str, Any]) -> str:
    payload = {
        "filename": result.get("filename"),
        "media_type": result.get("media_type"),
        "sha256": result.get("sha256"),
        "bytes": result.get("bytes"),
        "provenance_state": result.get("provenance_state"),
        "c2pa": result.get("c2pa"),
        "metadata": result.get("metadata"),
        "derived_timeline": result.get("derived_timeline"),
        "metadata_consistency": result.get("metadata_consistency"),
        "tools": result.get("tools"),
    }
    s = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def _kv_table(data: Dict[str, Any], col_widths: Tuple[float, float] = (2.2 * inch, 4.8 * inch)) -> Table:
    rows = []
    for k, v in data.items():
        rows.append([_safe_text(k, 80), _safe_text(v, 800)])
    t = Table(rows, colWidths=list(col_widths))
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.whitesmoke, colors.white]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def _bullets(title: str, items: List[str], style_title: ParagraphStyle, style_body: ParagraphStyle) -> List[Any]:
    out: List[Any] = []
    out.append(Paragraph(_safe_text(title, 120), style_title))
    if items:
        html = "<br/>".join(f"• {_safe_text(x, 300)}" for x in items)
    else:
        html = "• (none)"
    out.append(Paragraph(html, style_body))
    return out

def _add_image(story: List[Any], path: str, caption: str, width: float = 4.8 * inch) -> None:
    if not path:
        return
    if not os.path.exists(path):
        return
    try:
        img = Image(path, width=width, height=width * 0.6)
        story.append(img)
        story.append(Paragraph(_safe_text(caption, 160), ParagraphStyle("ts_caption", fontSize=8, leading=10)))
        story.append(Spacer(1, 0.12 * inch))
    except Exception:
        return



def build_pdf_report(result: Any, out_path: str) -> None:
    # ---- Type safety ----
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except Exception as e:
            raise ValueError("build_pdf_report expected dict/JSON-string result") from e
    if not isinstance(result, dict):
        raise ValueError(f"build_pdf_report expected dict, got {type(result)}")

    styles = getSampleStyleSheet()
    title = ParagraphStyle("ts_title", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, alignment=TA_LEFT)
    h2 = ParagraphStyle("ts_h2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=14, alignment=TA_LEFT)
    body = ParagraphStyle("ts_body", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, leading=13, alignment=TA_LEFT)
    small = ParagraphStyle("ts_small", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=12, alignment=TA_LEFT)

    doc = SimpleDocTemplate(out_path, pagesize=LETTER, leftMargin=0.8 * inch, rightMargin=0.8 * inch, topMargin=0.8 * inch, bottomMargin=0.8 * inch)
    story: List[Any] = []

    story.append(Paragraph("TruthSig — Evidence Provenance Report", title))
    story.append(Paragraph("Cryptographic proof when available. No guessing.", small))
    story.append(Spacer(1, 0.2 * inch))

    # Decision context
    decision_context = (_as_dict(result.get("decision_context")).get("purpose")) or (
        "This report supports financial, legal, or editorial decision-making by separating cryptographically verifiable facts, technical observations, and unknowns."
    )
    story.append(Paragraph("Decision context", h2))
    story.append(Paragraph(_safe_text(decision_context, 600), body))
    story.append(Spacer(1, 0.15 * inch))

    # Report ID / integrity
    integrity = _as_dict(result.get("report_integrity"))
    analyzed_at = integrity.get("timestamp") or integrity.get("analyzed_at") or datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    report_hash = _hash_result_for_id(result)
    report_id = report_hash[:12]

    story.append(Paragraph("Executive summary", h2))
    summary = {
        "Report ID": report_id,
        "Analysis time (UTC)": analyzed_at,
        "Filename": result.get("filename"),
        "Media type": result.get("media_type"),
        "SHA-256 (file fingerprint)": result.get("sha256"),
        "Size (bytes)": result.get("bytes"),
        "Provenance status": result.get("provenance_state"),
        "Trust score": result.get("trust_score"),
        "Trust label": result.get("label"),
    }
    story.append(_kv_table(summary))
    story.append(Spacer(1, 0.18 * inch))

    one_line = result.get("one_line_rationale") or result.get("summary")
    if one_line:
        story.append(Paragraph("Summary verdict", h2))
        story.append(Paragraph(_safe_text(one_line, 600), body))
        story.append(Spacer(1, 0.1 * inch))

    top_reasons = result.get("top_reasons") or []
    if top_reasons:
        story += _bullets("Top reasons", list(top_reasons)[:3], h2, body)
        story.append(Spacer(1, 0.12 * inch))


    # What this report is / is not
    is_list = result.get("what_this_report_is") or [
        "A structured view of verifiable facts, derived technical observations, and unknowns",
        "A provenance and metadata summary intended to support human review",
    ]
    not_list = result.get("what_this_report_is_not") or [
        "A probability score of being fake",
        "A determination of authenticity or intent",
        "A detector of specific deepfake models",
    ]
    story += _bullets("What this report is", list(is_list), h2, body)
    story.append(Spacer(1, 0.08 * inch))
    story += _bullets("What this report is not", list(not_list), h2, body)
    story.append(Spacer(1, 0.18 * inch))

    # Provenance snapshot
    story.append(Paragraph("Provenance snapshot", h2))
    c2pa = _as_dict(result.get("c2pa_summary") or result.get("c2pa"))
    c2pa_present = bool(c2pa.get("present"))
    c2pa_kv = {
        "C2PA present": "Yes" if c2pa_present else "No",
        "C2PA validation": _safe_text(c2pa.get("validation") or c2pa.get("status")),
        "Signer / issuer": _safe_text(c2pa.get("signer") or c2pa.get("issuer")),
        "Assertions": _safe_text(c2pa.get("assertions")),
    }
    story.append(_kv_table(c2pa_kv))
    story.append(Spacer(1, 0.18 * inch))

    # Layer 2: Derived observations
    story.append(Paragraph("Layer 2 — Derived technical observations", h2))

    meta = _as_dict(result.get("metadata"))
    completeness = _as_dict(result.get("metadata_completeness"))
    score = completeness.get("score_0_to_3")
    details = completeness.get("notes")

    make = meta.get("EXIF:Make") or meta.get("Make")
    model = meta.get("EXIF:Model") or meta.get("Model")
    software = meta.get("EXIF:Software") or meta.get("XMP:CreatorTool") or meta.get("Software")

    obs = {
        "Metadata completeness (0–3)": score if score is not None else "",
        "Completeness details": _safe_text(details),
        "Camera make": make or "",
        "Camera model": model or "",
        "Software / creator tool": software or "",
    }
    story.append(_kv_table(obs))
    story.append(Spacer(1, 0.12 * inch))

    # Timeline (from derived_timeline)
    timeline = _as_dict(result.get("derived_timeline"))
    story.append(Paragraph("Forensic timeline (from metadata)", h2))
    if timeline.get("events"):
        timeline_rows = {e.get("key"): e.get("value") for e in timeline.get("events", [])}
        story.append(_kv_table(timeline_rows))
    else:
        story.append(_kv_table({"Notes": timeline.get("notes") or "No timeline signals available."}))
    story.append(Spacer(1, 0.12 * inch))

    # Video timeline markers
    forensics = _as_dict(result.get("forensics"))
    markers = (forensics.get("results") or {}).get("timeline_markers") or []
    if markers:
        story.append(Paragraph("Video timeline markers", h2))
        marker_rows = {
            f"T+{m.get('time_s', 0):.1f}s": f"Score {m.get('score', '')}"
            for m in markers[:6]
            if m.get("status") == "OK"
        }
        story.append(_kv_table(marker_rows))
        story.append(Spacer(1, 0.12 * inch))


    # Consistency (your API uses metadata_consistency)
    consistency = _as_dict(result.get("metadata_consistency"))
    story.append(Paragraph("Consistency checks", h2))
    story.append(_kv_table(consistency if consistency else {"Notes": "No consistency checks available."}))
    story.append(Spacer(1, 0.18 * inch))

    # Visual artifacts
    story.append(Paragraph("Visual artifacts", h2))
    if forensics.get("type") == "image":
        heatmap_path = (forensics.get("results") or {}).get("heatmap_path")
        _add_image(story, heatmap_path, "ELA heatmap (image)")
    elif forensics.get("type") == "video":
        flagged = (forensics.get("results") or {}).get("flagged_frames") or []
        for frame in flagged[:3]:
            _add_image(story, frame.get("thumbnail_path"), "Flagged frame")
            _add_image(story, frame.get("heatmap_path"), "Frame ELA heatmap")
    else:
        story.append(Paragraph("No visual artifacts available.", body))
        story.append(Spacer(1, 0.12 * inch))


    # Layer 3: Unknowns & limitations
    story.append(Paragraph("Layer 3 — Unknowns & limitations", h2))
    limitations = result.get("limitations") or [
        "Absence of cryptographic provenance is not evidence of manipulation; it limits verifiability.",
        "Metadata can be missing or altered by common workflows (screenshots, exports, messaging apps, social platforms).",
        "This report reflects the state of the provided file at the time of analysis.",
    ]
    story.append(Paragraph("<br/>".join(f"• {_safe_text(x, 400)}" for x in list(limitations)), body))
    story.append(Spacer(1, 0.18 * inch))

    # What would make verifiable
    story.append(Paragraph("What would increase verifiability", h2))
    wmv = result.get("what_would_make_verifiable") or [
        "Capture with a C2PA-enabled camera or app",
        "Preserve the original file without re-exporting",
        "Use platform-side sealing at the time of capture",
    ]
    story.append(Paragraph("<br/>".join(f"• {_safe_text(x, 400)}" for x in list(wmv)), body))
    story.append(Spacer(1, 0.18 * inch))

    # Chain of custody
    custody = result.get("chain_of_custody") or []
    if custody:
        story.append(Paragraph("Chain of custody", h2))
        custody_rows = {
            f"{_safe_text(e.get('event_type'), 40)} @ {_safe_text(e.get('created_at'), 40)}": _safe_text(
                (e.get("details_json") or e.get("details") or "")
            )
            for e in custody[:8]
        }
        story.append(_kv_table(custody_rows))
        story.append(Spacer(1, 0.18 * inch))


    # Report integrity block
    tools = result.get("tools") or {}
    integrity_kv = {
        "Report hash (SHA-256)": report_hash,
        "Analysis timestamp (UTC)": analyzed_at,
        "Tool versions": _safe_text(tools, 1200),
    }
    story.append(Paragraph("Report integrity", h2))
    story.append(_kv_table(integrity_kv))

    doc.build(story)
