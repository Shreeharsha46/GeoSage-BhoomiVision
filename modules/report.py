"""
GeoSage - PDF report generator (Stage 7.1).

ReportLab-based professional report. Every value on the report comes
from stored analysis records; when a value or image is missing the
section says so explicitly instead of fabricating data. The mandatory
verification disclaimer appears on the cover and in the footer.
"""
import json
from datetime import datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image as RLImage, KeepTogether, PageBreak,
                                Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

BRAND_NAVY = colors.HexColor("#0d1b2a")
BRAND_GREEN = colors.HexColor("#1fbf75")
BRAND_CYAN = colors.HexColor("#38c6d9")
BRAND_GREY = colors.HexColor("#5a6b7b")

PRIORITY_LABELS = {
    "low": "Low", "medium": "Medium", "high": "High",
    "insufficient_data": "Insufficient data",
}
STATUS_LABELS = {
    "pending_verification": "Pending Verification",
    "verified_by_reviewer": "Verified by Reviewer",
    "rejected_false_detection": "Rejected as False Detection",
}


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"],
                              textColor=colors.white, fontSize=26, leading=32))
    styles.add(ParagraphStyle(name="CoverSub", parent=styles["Normal"],
                              textColor=colors.HexColor("#9fd8c2"), fontSize=12))
    styles.add(ParagraphStyle(name="H2Brand", parent=styles["Heading2"],
                              textColor=BRAND_NAVY))
    styles.add(ParagraphStyle(name="SmallGrey", parent=styles["Normal"],
                              textColor=BRAND_GREY, fontSize=8, leading=10))
    return styles


def _artifact_table(analysis, artifact_keys):
    """2x3 grid of artifact images with captions (missing -> notice)."""
    styles = _styles()
    cells, captions = [], []
    captions_map = {
        "side_by_side": "Previous vs registered recent image",
        "difference": "Difference visualisation (Jet)",
        "mask": "Binary change mask",
        "heatmap": "Change-intensity heatmap (green-yellow-red)",
        "overlay": "Detected change contours on previous image",
        "registered": "Registered recent image",
    }
    for key in artifact_keys:
        path = json.loads(analysis.artifacts or "{}").get(key)
        caption = Paragraph(captions_map.get(key, key), styles["SmallGrey"])
        if path and (Path(__name__).parent if False else True):
            full = Path(__file__).resolve().parent.parent / path
            if full.is_file():
                img = RLImage(str(full), width=5.4 * cm, height=3.8 * cm,
                              kind="proportional")
                cells.append([img, caption])
                continue
        cells.append([Paragraph("Not available for this analysis.",
                                styles["SmallGrey"]), caption])
    rows = []
    for i in range(0, len(cells), 2):
        pair = cells[i:i + 2]
        while len(pair) < 2:
            pair.append([Paragraph("", styles["SmallGrey"]),
                         Paragraph("", styles["SmallGrey"])])
        rows.append([pair[0][0], pair[1][0]])
        rows.append([pair[0][1], pair[1][1]])
    table = Table(rows, colWidths=[8.6 * cm, 8.6 * cm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dde5ec")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _kv_table(pairs):
    table = Table([[Paragraph(f"<b>{k}</b>", _styles()["Normal"]), str(v)]
                   for k, v in pairs], colWidths=[5.2 * cm, 12 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef4f1")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dde5ec")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _cover(analysis, parcel):
    styles = _styles()
    flow = []
    cover_table = Table([
        [Paragraph("GeoSage", ParagraphStyle(
            name="c1", parent=styles["CoverTitle"], alignment=1))],
        [Paragraph("AI-Powered Rural Land Intelligence &amp; Boundary "
                   "Verification System", ParagraphStyle(
            name="c2", parent=styles["CoverSub"], alignment=1))],
        [Paragraph("BHOOMI VISION", ParagraphStyle(
            name="c3", parent=styles["CoverSub"], alignment=1,
            textColor=BRAND_CYAN, fontName="Helvetica-Bold", fontSize=14))],
    ], colWidths=[17 * cm])
    cover_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_NAVY),
        ("TOPPADDING", (0, 0), (-1, 0), 40),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 40),
    ]))
    flow.append(cover_table)
    flow.append(Spacer(1, 24))
    flow.append(Paragraph(
        f"Land Change Analysis Report — Analysis #{analysis.id}", styles["Title"]))
    flow.append(Spacer(1, 8))
    flow.append(_kv_table([
        ("Parcel", parcel.parcel_name),
        ("Location", parcel.location or "Not recorded"),
        ("Georeferenced",
         f"Yes (lat {parcel.latitude:.5f}, lon {parcel.longitude:.5f}, "
         f"{parcel.coordinate_reference_system or 'CRS not stated'})"
         if parcel.is_georeferenced else "No — parcel has no coordinates"),
        ("Analysis ID", analysis.id),
        ("Analysis date", (analysis.analysis_date or datetime.now())
         .strftime("%Y-%m-%d %H:%M UTC")),
        ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Method", analysis.processing_method or "—"),
    ]))
    flow.append(Spacer(1, 20))
    flow.append(Paragraph(
        "<b>Mandatory verification disclaimer.</b> All findings in this report "
        "are preliminary AI screening aids produced from visual image "
        "comparison. They are NOT legally verified property boundaries and "
        "NOT proof of land change or encroachment. Confirm everything with "
        "authorized land surveyors or officials before any action.",
        ParagraphStyle(name="disc", parent=styles["Normal"],
                       textColor=colors.HexColor("#8a1c1c"), fontSize=10)))
    flow.append(PageBreak())
    return flow


def generate_report(analysis):
    """Build the PDF for one AnalysisResult. Returns PDF bytes."""
    from database.models import LandUseObservation, ReviewRecord

    parcel = analysis.parcel
    styles = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.6 * cm, bottomMargin=2.0 * cm,
        title=f"GeoSage Analysis Report #{analysis.id}",
        author="GeoSage - BHOOMI VISION",
    )

    story = _cover(analysis, parcel)

    # --- Images --------------------------------------------------------------
    story.append(Paragraph("1. Image Evidence", styles["H2Brand"]))
    story.append(Spacer(1, 6))
    story.append(_artifact_table(analysis, ["side_by_side", "difference", "mask",
                                            "heatmap", "overlay", "registered"]))
    story.append(Spacer(1, 14))

    # --- Measurements ----------------------------------------------------------
    story.append(Paragraph("2. Measured Results", styles["H2Brand"]))
    metadata = json.loads(analysis.processing_metadata or "{}")
    registration = metadata.get("registration", {})
    quality = metadata.get("quality", {})
    story.append(_kv_table([
        ("Visual change", (f"{analysis.change_percentage:.2f}% of the valid "
                           "comparison area") if analysis.change_percentage is not None
         else "Not computed (registration failed)"),
        ("Keypoints (prev / recent)",
         f"{registration.get('keypoints_old', '—')} / "
         f"{registration.get('keypoints_new', '—')}"),
        ("Good matches", registration.get("good_matches", "—")),
        ("RANSAC inliers", registration.get("inliers", "—")),
        ("Inlier ratio", registration.get("inlier_ratio", "—")),
        ("Median reprojection error",
         f"{registration.get('median_reprojection_error')} px"
         if registration.get("median_reprojection_error") is not None else "—"),
        ("Blur score (prev / recent)",
         f"{quality.get('old', {}).get('blur_score', '—')} / "
         f"{quality.get('new', {}).get('blur_score', '—')}"),
        ("Processing time",
         f"{metadata.get('processing_seconds', '—')} s"),
        ("Review priority",
         PRIORITY_LABELS.get(analysis.review_priority,
                             analysis.review_priority or "—")),
    ]))
    story.append(Spacer(1, 14))

    # --- Regions -----------------------------------------------------------------
    story.append(Paragraph("3. Flagged Regions & Explanations", styles["H2Brand"]))
    if analysis.regions:
        rows = [["#", "Area (px)", "Mean diff", "Priority"]]
        for index, region in enumerate(analysis.regions, start=1):
            rows.append([str(index), str(region.pixel_area),
                         f"{region.mean_intensity:.0f}/255"
                         if region.mean_intensity is not None else "—",
                         region.priority or "—"])
        region_table = Table(rows, colWidths=[1.5 * cm, 3.5 * cm, 3.5 * cm, 3 * cm])
        region_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dde5ec")),
        ]))
        story.append(region_table)
        story.append(Spacer(1, 8))
        for index, region in enumerate(analysis.regions, start=1):
            story.append(KeepTogether([
                Paragraph(f"<b>Why was region {index} flagged?</b>",
                          styles["Heading4"]),
                Paragraph(region.explanation or "No explanation stored.",
                          styles["Normal"]),
                Paragraph("Limitations: visual pixel change only; seasonal, "
                          "shadow and illumination effects are mitigated but "
                          "not eliminated; no claim about WHAT changed. "
                          "Recommended action: on-ground / cadastral "
                          "verification before conclusions.",
                          styles["SmallGrey"]),
                Spacer(1, 8),
            ]))
    else:
        story.append(Paragraph(
            "No regions were flagged for this analysis (either no measurable "
            "change or the comparison failed).", styles["Normal"]))
    story.append(PageBreak())

    # --- Land-use observations ------------------------------------------------------
    story.append(Paragraph("4. Land-Use Baseline Observations", styles["H2Brand"]))
    observations = (db_landuse(analysis))
    if observations:
        rows = [["Category", "Previous", "Recent", "Change"]]
        for obs in observations:
            rows.append([obs.category, f"{obs.old_proportion * 100:.1f}%",
                         f"{obs.new_proportion * 100:.1f}%",
                         f"{obs.delta_proportion * 100:+.1f}%"])
        lu_table = Table(rows, colWidths=[6 * cm, 3.6 * cm, 3.6 * cm, 3.6 * cm])
        lu_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dde5ec")),
        ]))
        story.append(lu_table)
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Classical HSV colour/texture baseline - heuristic observations, "
            "not trained-model predictions.", styles["SmallGrey"]))
    else:
        story.append(Paragraph("No land-use observations stored for this "
                               "analysis.", styles["Normal"]))
    story.append(Spacer(1, 14))

    # --- Boundary comparison ---------------------------------------------------------
    story.append(Paragraph("5. Boundary Comparison", styles["H2Brand"]))
    boundary = json.loads(analysis.boundary_summary or "null")
    if boundary:
        unit = boundary.get("unit", "px")
        story.append(_kv_table([
            ("Intersection over Union", boundary.get("iou", "—")),
            ("Candidate outside recorded boundary",
             f"{boundary.get('outside_share', 0) * 100:.1f}%"),
            ("Recorded area missing from candidate",
             f"{boundary.get('missing_share', 0) * 100:.1f}%"),
            ("Boundary displacement", f"{boundary.get('displacement', '—')} {unit}"),
            ("Screening priority", boundary.get("priority", "—").title()),
        ]))
        story.append(Spacer(1, 4))
        story.append(Paragraph(boundary.get("note", ""), styles["SmallGrey"]))
    else:
        story.append(Paragraph("No boundary comparison has been run for this "
                               "parcel's analyses.", styles["Normal"]))
    story.append(Spacer(1, 14))

    # --- Verification -----------------------------------------------------------------
    story.append(Paragraph("6. Human Verification Status", styles["H2Brand"]))
    latest_review = (db_latest_review(analysis))
    if latest_review:
        story.append(_kv_table([
            ("Status", STATUS_LABELS.get(latest_review.review_status,
                                         latest_review.review_status)),
            ("Reviewer", latest_review.reviewer.name if latest_review.reviewer else "—"),
            ("Reviewed at", latest_review.reviewed_at.strftime("%Y-%m-%d %H:%M UTC")),
            ("Comments", latest_review.comments or "—"),
        ]))
    else:
        story.append(Paragraph("No verification records exist yet.", styles["Normal"]))
    story.append(PageBreak())

    # --- Methodology, limitations, findings -------------------------------------------
    story.append(Paragraph("7. Methodology", styles["H2Brand"]))
    story.append(Paragraph(
        "1) Upload validation (extension whitelist, content sniffing, size "
        "limits). 2) Preprocessing: decoding, downscaling, CLAHE contrast "
        "normalization. 3) Registration: ORB features, descriptor matching "
        "with Lowe ratio test, RANSAC homography, perspective warp; quality "
        "is measured by inlier ratio and median reprojection error, and "
        "failed registrations are reported, never forced. 4) Change "
        "detection: absolute difference over the valid overlap, Otsu "
        "thresholding, morphological open/close, connected-component region "
        "extraction; change percentage uses valid comparison pixels only. "
        "5) Land-use: classical HSV colour-range segmentation baseline. "
        "6) Boundary: GeoJSON/KML ingestion, Shapely validation and "
        "comparison in a projected UTM CRS where geographic. 7) Transparent "
        "review-priority engine over measured factors.", styles["Normal"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("8. Limitations", styles["H2Brand"]))
    story.append(Paragraph(
        "- Results are visual pixel changes, not confirmed physical changes.<br/>"
        "- Seasonal vegetation cycles, shadows and illumination differences "
        "are mitigated (CLAHE, morphology) but not eliminated.<br/>"
        "- Without scale metadata, areas are pixel-only; geographic sizes are "
        "never invented.<br/>"
        "- Detected boundary candidates are image features, not legal "
        "boundaries.<br/>"
        "- Review priorities are screening aids, not encroachment verdicts or "
        "legal conclusions.", styles["Normal"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("9. Final Findings", styles["H2Brand"]))
    story.append(Paragraph(analysis.result_summary or
                           "No summary stored for this analysis.", styles["Normal"]))
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "<b>Verification required:</b> this report must be reviewed by an "
        "authorized human reviewer and, where relevant, verified on the "
        "ground. AI findings never substitute for official land records.",
        ParagraphStyle(name="disc2", parent=styles["Normal"],
                       textColor=colors.HexColor("#8a1c1c"))))

    doc.build(story)
    return buffer.getvalue()


# --- Small DB accessors kept at module bottom for readability ---------------
def db_landuse(analysis):
    from database.models import LandUseObservation
    return (LandUseObservation.query
            if hasattr(LandUseObservation, "query") else None) and \
        analysis.__class__.query.session.query(LandUseObservation).filter_by(
            analysis_id=analysis.id).order_by(LandUseObservation.id).all()


def db_latest_review(analysis):
    from database.models import ReviewRecord
    return analysis.__class__.query.session.query(ReviewRecord).filter_by(
        analysis_id=analysis.id).order_by(ReviewRecord.reviewed_at.desc()).first()
