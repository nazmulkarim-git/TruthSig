from __future__ import annotations

from typing import Any, Dict, List, Tuple


Signal = Dict[str, Any]


def _signal(
    *,
    key: str,
    label: str,
    value: Any,
    severity: str,
    weight: float,
    evidence: Any,
    explanation: str,
    status: str,
) -> Signal:
    return {
        "key": key,
        "label": label,
        "value": value,
        "severity": severity,
        "weight": weight,
        "evidence": evidence,
        "explanation": explanation,
        "status": status,
    }


def _clamp(score: float) -> int:
    if score < 0:
        return 0
    if score > 100:
        return 100
    return int(round(score))


def _label_for_score(score: int) -> str:
    if score >= 75:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    return "LOW"


def _top_reasons(signals: List[Signal], limit: int = 3) -> List[str]:
    ranked = sorted(signals, key=lambda s: abs(float(s.get("weight") or 0)), reverse=True)
    reasons: List[str] = []
    for s in ranked:
        expl = s.get("explanation") or s.get("label")
        if expl:
            reasons.append(str(expl))
        if len(reasons) >= limit:
            break
    return reasons


def fuse_signals(
    *,
    provenance_state: str,
    c2pa_summary: Dict[str, Any],
    metadata_completeness: Dict[str, Any],
    metadata_consistency: Dict[str, Any],
    ai_disclosure: Dict[str, Any],
    transformation_hints: Dict[str, Any],
    container_anomalies: Dict[str, Any],
    visual_forensics: Dict[str, Any],
) -> Dict[str, Any]:
    signals: List[Signal] = []

    score = 50.0
    provenance_flags = {
        "present": False,
        "valid": False,
        "broken": False,
        "state": provenance_state,
    }

    if provenance_state == "VERIFIED_ORIGINAL":
        provenance_flags.update({"present": True, "valid": True})
        signals.append(
            _signal(
                key="provenance.verified",
                label="Provenance verified",
                value=provenance_state,
                severity="POSITIVE",
                weight=25,
                evidence=c2pa_summary,
                explanation="C2PA provenance was present and verified, increasing trust.",
                status="OK",
            )
        )
        score += 25
    elif provenance_state == "ALTERED_OR_BROKEN_PROVENANCE":
        provenance_flags.update({"present": True, "broken": True})
        signals.append(
            _signal(
                key="provenance.broken",
                label="Broken or altered provenance",
                value=provenance_state,
                severity="HIGH",
                weight=-30,
                evidence=c2pa_summary,
                explanation="C2PA provenance was present but indicates a broken or altered trust chain.",
                status="FAIL",
            )
        )
        score -= 30
    else:
        signals.append(
            _signal(
                key="provenance.absent",
                label="No cryptographic provenance",
                value=provenance_state,
                severity="INFO",
                weight=-5,
                evidence=c2pa_summary,
                explanation="No C2PA manifest was detected; absence does not imply manipulation.",
                status="WARN",
            )
        )
        score -= 5

    meta_score = metadata_completeness.get("score_0_to_3")
    if meta_score is not None:
        delta = (int(meta_score) - 1) * 4
        signals.append(
            _signal(
                key="metadata.completeness",
                label="Metadata completeness",
                value=meta_score,
                severity="INFO",
                weight=delta,
                evidence=metadata_completeness,
                explanation="Metadata completeness influences visibility into capture context.",
                status="OK" if meta_score >= 2 else "WARN",
            )
        )
        score += delta

    consistency_status = metadata_consistency.get("status")
    if consistency_status == "CONSISTENT":
        signals.append(
            _signal(
                key="metadata.consistency",
                label="Metadata consistency",
                value=consistency_status,
                severity="POSITIVE",
                weight=6,
                evidence=metadata_consistency,
                explanation="Metadata fields are internally consistent.",
                status="OK",
            )
        )
        score += 6
    elif consistency_status == "INCONSISTENT_OR_MISSING":
        signals.append(
            _signal(
                key="metadata.consistency",
                label="Metadata inconsistencies or gaps",
                value=consistency_status,
                severity="MEDIUM",
                weight=-8,
                evidence=metadata_consistency,
                explanation="Metadata inconsistencies or missing device identifiers reduce confidence.",
                status="WARN",
            )
        )
        score -= 8

    ai_declared = (ai_disclosure or {}).get("declared")
    if ai_declared == "POSSIBLE":
        signals.append(
            _signal(
                key="ai.disclosure",
                label="Possible AI disclosure",
                value=ai_declared,
                severity="MEDIUM",
                weight=-10,
                evidence=ai_disclosure,
                explanation="Metadata includes AI-related markers; this may indicate generated or edited content.",
                status="WARN",
            )
        )
        score -= 10
    elif ai_declared == "NO":
        signals.append(
            _signal(
                key="ai.disclosure",
                label="No AI disclosure markers",
                value=ai_declared,
                severity="INFO",
                weight=2,
                evidence=ai_disclosure,
                explanation="No AI markers were found in available metadata.",
                status="OK",
            )
        )
        score += 2

    if transformation_hints:
        hints_note = transformation_hints.get("notes") or []
        if transformation_hints.get("screenshot_likelihood") == "HIGH":
            signals.append(
                _signal(
                    key="transform.screenshot",
                    label="Screenshot likelihood high",
                    value=transformation_hints.get("screenshot_likelihood"),
                    severity="MEDIUM",
                    weight=-8,
                    evidence=transformation_hints,
                    explanation="Signals suggest screen capture or export, which can strip provenance.",
                    status="WARN",
                )
            )
            score -= 8
        elif transformation_hints.get("screenshot_likelihood") == "LOW":
            signals.append(
                _signal(
                    key="transform.screenshot",
                    label="Screenshot likelihood low",
                    value=transformation_hints.get("screenshot_likelihood"),
                    severity="INFO",
                    weight=3,
                    evidence=transformation_hints,
                    explanation="Device metadata suggests native capture rather than screenshot.",
                    status="OK",
                )
            )
            score += 3

        if transformation_hints.get("forwarded_or_reencoded") == "POSSIBLE":
            signals.append(
                _signal(
                    key="transform.reencode",
                    label="Possible re-encoding",
                    value=transformation_hints.get("forwarded_or_reencoded"),
                    severity="MEDIUM",
                    weight=-6,
                    evidence=hints_note,
                    explanation="Container metadata suggests re-encoding or forwarding.",
                    status="WARN",
                )
            )
            score -= 6

    if container_anomalies:
        status = container_anomalies.get("status")
        if status == "ANOMALY":
            signals.append(
                _signal(
                    key="container.anomalies",
                    label="Container anomalies",
                    value=status,
                    severity="MEDIUM",
                    weight=-7,
                    evidence=container_anomalies,
                    explanation="Container or stream structure shows anomalies.",
                    status="WARN",
                )
            )
            score -= 7
        elif status == "OK":
            signals.append(
                _signal(
                    key="container.anomalies",
                    label="Container structure normal",
                    value=status,
                    severity="INFO",
                    weight=2,
                    evidence=container_anomalies,
                    explanation="No notable container anomalies detected.",
                    status="OK",
                )
            )
            score += 2
        elif status == "NOT_AVAILABLE":
            signals.append(
                _signal(
                    key="container.anomalies",
                    label="Container checks unavailable",
                    value=status,
                    severity="INFO",
                    weight=0,
                    evidence=container_anomalies,
                    explanation=container_anomalies.get("notes") or "Container checks unavailable.",
                    status="NOT_AVAILABLE",
                )
            )

    if visual_forensics:
        v_status = visual_forensics.get("status")
        if v_status == "SUSPICIOUS":
            signals.append(
                _signal(
                    key="visual.forensics",
                    label="Visual anomaly signals",
                    value=v_status,
                    severity="HIGH",
                    weight=-18,
                    evidence=visual_forensics,
                    explanation="Visual forensics detected elevated anomaly scores.",
                    status="WARN",
                )
            )
            score -= 18
        elif v_status == "CLEAR":
            signals.append(
                _signal(
                    key="visual.forensics",
                    label="No strong visual anomalies",
                    value=v_status,
                    severity="INFO",
                    weight=4,
                    evidence=visual_forensics,
                    explanation="Visual forensics did not detect strong anomalies.",
                    status="OK",
                )
            )
            score += 4
        elif v_status == "NOT_AVAILABLE":
            signals.append(
                _signal(
                    key="visual.forensics",
                    label="Visual forensics unavailable",
                    value=v_status,
                    severity="INFO",
                    weight=0,
                    evidence=visual_forensics,
                    explanation=visual_forensics.get("explanation") or "Visual forensics unavailable.",
                    status="NOT_AVAILABLE",
                )
            )

    trust_score = _clamp(score)
    label = _label_for_score(trust_score)
    top_reasons = _top_reasons(signals)

    return {
        "trust_score": trust_score,
        "label": label,
        "top_reasons": top_reasons,
        "signals": signals,
        "provenance_flags": provenance_flags,
    }