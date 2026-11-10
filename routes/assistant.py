"""
Assistant blueprint (Stage 7.2): offline retrieval-based assistant.

Answers questions about stored analysis records.
"""
from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required
import json

from database.db import db
from database.models import AnalysisResult, ReviewRecord, LandUseObservation
from modules.assistant import answer_question
from routes.helpers import get_analysis_or_denied

assistant_bp = Blueprint("assistant", __name__, url_prefix="/assistant")

@assistant_bp.route("/")
@login_required
def index():
    return render_template("assistant/index.html")

@assistant_bp.route("/ask", methods=["POST"])
@login_required
def ask():
    analysis_id = request.form.get("analysis_id", type=int)
    question = request.form.get("question", "")
    if not analysis_id:
        return jsonify(answer="Please select an analysis.")
    
    analysis = get_analysis_or_denied(analysis_id)
    
    # Assemble the record
    review = db.session.query(ReviewRecord).filter_by(analysis_id=analysis.id).order_by(ReviewRecord.id.desc()).first()
    landuse = db.session.query(LandUseObservation).filter_by(analysis_id=analysis.id).all()
    
    record = {
        "analysis_id": analysis.id,
        "change_percentage": analysis.change_percentage,
        "review_status": review.review_status if review else None,
        "regions": [], # would load from DB if needed
        "boundary_summary": json.loads(analysis.boundary_summary or "null"),
        "landuse": {
            "transitions": [{"label": o.category, "old": o.old_proportion, "new": o.new_proportion, "delta": o.delta_proportion} for o in landuse]
        },
        "priority": {"label": analysis.review_priority}
    }
    
    answer = answer_question(record, question)
    return jsonify(answer=answer)
