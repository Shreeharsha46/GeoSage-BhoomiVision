"""
Smart AI assistant (Stage 7.2).

Retrieval-based offline assistant answering factual questions about stored
analysis results. It uses only real database values and never calls paid
LLM APIs.

Answer format: deterministic, factual responses based on known records.
When information is missing, responds with a clear, non‑speculative message.
"""
from typing import Dict, Any
import re

def answer_question(analysis_record: Dict[str, Any], question: str) -> str:
    """Return a deterministic answer about a stored analysis.

    The answer uses only real fields from `analysis_record` (as stored by the
    pipeline) and never invents any measurement or confidence.
    """
    lower = question.lower()

    # Parse region index from questions like "why was region 3 flagged"
    region_index = None
    match = re.search(r'region\s+(\d+)', lower)
    if match:
        region_index = int(match.group(1))

    if "what changes were detected" in lower or "change percentage" in lower:
        change_pct = analysis_record.get("change_percentage")
        if change_pct is None:
            return "No change measurement exists for this analysis."
        return (f"The analysis detected a visual change of {change_pct}% of the "
                f"valid comparison area ({analysis_record.get('changed_pixels', '—')} "
                f"pixels out of {analysis_record.get('valid_pixels', '—')}).")

    if ("why was" in lower and ("region" in lower or "area" in lower) and "flagged" in lower):
        if region_index is None:
            return "I cannot find the specific region in the stored results."
        regions = analysis_record.get("regions", [])
        if not regions:
            return "No regions were detected in this analysis."
        region = None
        for r in regions:
            if r.get("index") == region_index:
                region = r
                break
        if not region:
            return f"Region {region_index} was not found in the analysis results."
        if region.get("explanation"):
            return region["explanation"]
        return f"No explanation was stored for region {region_index}."

    if "what is the boundary mismatch" in lower or "boundary mismatch" in lower:
        boundary = analysis_record.get("boundary_summary")
        if not boundary:
            return "No boundary comparison has been performed for this analysis."
        iou = boundary.get("iou")
        priority = boundary.get("priority")
        mismatch = (f"IoU: {iou}") if iou is not None else "IoU not recorded"
        return (f"The boundary mismatch has an IoU of {mismatch}; "
                f"screening priority: {priority}.")

    if "what land-use changes were observed" in lower:
        landuse = analysis_record.get("landuse", {})
        transitions = landuse.get("transitions")
        if not transitions:
            return "No land-use observations were stored for this analysis."
        parts = [f"{t['label']} changed from {t['old']*100:.1f}% to {t['new']*100:.1f}% "
                 f"({t['delta']*100:+.1f}%)" for t in transitions[:3]]
        return "Land-use transitions: " + "; ".join(parts) + "."

    if "summarize the current analysis" in lower or "summarize" in lower:
        change_pct = analysis_record.get("change_percentage", "unknown")
        regions = analysis_record.get("regions", [])
        return (f"Analysis {analysis_record.get('analysis_id', '—')} "
                f"detected a {change_pct}% visual change with "
                f"{len(regions)} region(s) flagged. "
                f"Review priority: {analysis_record.get('priority', {}).get('label', 'unknown')}.")

    if "is this result legally verified" in lower or "verified" in lower:
        review_status = analysis_record.get("review_status")
        if not review_status:
            return "No verification record exists for this analysis."
        return ("The analysis has a human verification record; "
                f"status: {review_status}. "
                "However, this decision is a human review of the AI findings and "
                "does not establish a legally certified land boundary. "
                "Further legal confirmation may be required from official "
                "land authorities or surveyors.")

    return ("I do not have information to answer that question based on the "
            "stored analysis data. The answer would require an unavailable "
            "field or missing results.")
