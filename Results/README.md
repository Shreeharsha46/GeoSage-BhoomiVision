# Results Folder

This folder contains all partial/intermediate results obtained during the development and testing of the GeoSage — BHOOMI VISION project.

## Expected Contents

### Analysis Results
```
Results/
├── analysis_outputs/           # Generated analysis results
│   ├── analysis_<id>_diff.png        # Difference image
│   ├── analysis_<id>_heatmap.png     # Change heatmap
│   ├── analysis_<id>_mask.png        # Binary change mask
│   ├── analysis_<id>_overlay.png     # Contour overlay
│   ├── analysis_<id>_side_by_side.png # Side-by-side comparison
│   └── analysis_<id>_registered.png  # Registered image
│
├── analysis_reports/           # Generated PDF reports
│   ├── report_analysis_<id>.pdf
│   └── ...
│
├── boundary_comparisons/       # Boundary comparison outputs
│   ├── comparison_<id>_iou.json
│   ├── comparison_<id>_overlay.png
│   └── ...
│
├── landuse_outputs/           # Land-use classification results
│   ├── landuse_<id>_old.png
│   ├── landuse_<id>_new.png
│   ├── landuse_<id>_transitions.json
│   └── ...
│
├── boundary_detections/       # Candidate boundary detections
│   ├── detection_<id>_candidates.png
│   ├── detection_<id>_candidates.geojson
│   └── ...
│
├── verification_records/       # Human verification records
│   ├── verification_<analysis_id>.json
│   └── ...
│
├── training_logs/             # Model training logs
│   ├── training_log_<timestamp>.log
│   └── ...
│
├── test_results/              # Test outputs
│   ├── test_output_<timestamp>/
│   └── ...
│
└── screenshots/               # Demo/screenshots for documentation
    ├── dashboard.png
    ├── analysis_results.png
    ├── boundary_comparison.png
    ├── pdf_report.png
    └── ...
```

## File Naming Convention
- Use format: `<type>_<analysis_id>_<description>.<ext>`
- Example: `analysis_001_diff.png`, `report_001.pdf`
- Timestamps: ISO 8601 format (YYYY-MM-DD_HH-MM-SS)

## File Types & Formats
| Type | Format | Description |
|------|--------|-------------|
| Images | PNG, TIFF | Analysis visualizations |
| Reports | PDF | Analysis reports |
| Boundaries | GeoJSON | Boundary geometries |
| Comparisons | JSON | IoU, overlap metrics |
| Logs | TXT/JSON | Training/test logs |

## Naming Convention
- Use lowercase with underscores: `snake_case`
- Include analysis ID for traceability
- Include timestamp for versioning
- Max filename length: 255 characters

## Storage Guidelines
- Organize by analysis ID for traceability
- Compress large outputs (>10MB) if needed
- Keep raw inputs in Dataset/
- Store final deliverables in Results/
- Backup critical results periodically

## Partial Results Tracking
Each analysis run should generate a results summary:
```json
{
  "analysis_id": 123,
  "timestamp": "2026-11-16T10:30:00",
  "parcel_id": 5,
  "change_percentage": 12.5,
  "regions_detected": 5,
  "priority": "high",
  "boundary_iou": 0.87,
  "status": "completed"
}
```

## Cleanup Policy
- Retain: Final reports, verified results, boundary comparisons
- Archive: Intermediate processing images after report generation
- Delete: Temporary processing files after 30 days
- Never delete: User uploads, final reports, verification records