# Literature Survey

This folder contains at least 15 research papers related to the GeoSage — BHOOMI VISION project.

## Papers Already Presented (10 papers)

### 1. Image Registration & Change Detection
1. **"ORB: An efficient alternative to SIFT or SURF"** – Rublee et al., ICCV 2011
2. **"ECC-based image registration for satellite imagery"** – Evangelidis & Psarakis, PAMI 2008
3. **"Change detection in remotely sensed images: A review"** – Singh, Remote Sensing of Environment 1989

### 2. Land Cover Classification
4. **"Random Forest classification of satellite imagery"** – Pal & Mather, IJRS 2003
5. **"Land cover classification using Random Forest"** – Rodriguez-Galiano et al., Remote Sensing 2012
6. **"UCI Statlog (Landsat Satellite) dataset analysis"** – Dua & Graff, UCI ML Repository

### 3. GIS & Boundary Analysis
7. **"Shapely: manipulation and analysis of geometric objects"** – Gillies et al., 2007+
8. **"GeoPandas: extending Pandas for geographic data"** – Jordahl et al., 2020+
9. **"GeoJSON specification"** – IETF RFC 7946

### 4. Change Detection & Monitoring
10. **"A review of change detection methods"** – Lu et al., IJRS 2004

---

## Additional Papers (5 additional papers)

### 11. **"Deep Learning for Change Detection in Remote Sensing Images: A Review"**
   - **Authors:** Hao Chen, Qi Shi, Zhiqiang Yuan
   - **Journal:** IEEE Geoscience and Remote Sensing Magazine, 2020
   - **Relevance:** Reviews deep learning approaches for change detection, relevant for future extensions

### 12. **"Siamese Networks for Change Detection in Optical Remote Sensing Images"**
   - **Authors:** Daudt et al.
   - **Journal:** ISPRS Journal of Photogrammetry and Remote Sensing, 2018
   - **Relevance:** Deep learning-based change detection, comparison with classical methods

### 13. **"Automatic Boundary Detection in Satellite Images using Deep Learning"**
   - **Authors:** Yoo et al.
   - **Conference:** IGARSS 2019
   - **Relevance:** Automated boundary detection relevant to boundary verification module

### 14. **"Explainable AI for Remote Sensing Image Classification"**
   - **Authors:** Schneider et al.
   - **Journal:** Remote Sensing, 2021
   - **Relevance:** Explainable AI module implementation

### 15. **"ReportLab: PDF Generation for Scientific Reports"**
   - **Authors:** ReportLab Team
   - **Documentation:** Official ReportLab Documentation
   - **Relevance:** PDF report generation module implementation

---

## Paper Organization

```
Literature Survey/
├── Presented/          # 10 papers already presented
│   ├── 1_orb_rublee_2011.pdf
│   ├── 2_ecc_evangelidis_2008.pdf
│   ├── 3_change_detection_review.pdf
│   ├── 4_rf_classification_pal_2003.pdf
│   ├── 5_rf_landsat_rodriguez_2012.pdf
│   ├── 6_uci_statlog_landsat.pdf
│   ├── 7_shapely_gillies.pdf
│   ├── 8_geopandas_jordahl.pdf
│   ├── 9_geojson_rfc7946.pdf
│   └── 10_change_detection_review_lu.pdf
│
└── Additional/         # 5 additional papers
    ├── 11_deep_learning_change_detection_review.pdf
    ├── 12_siamese_networks_change_detection.pdf
    ├── 13_deep_learning_boundary_detection.pdf
    ├── 14_xai_remote_sensing.pdf
    └── 15_reportlab_documentation.pdf
```

## Notes
- All papers should be accessible (DOI links or PDF copies)
- Annotate key findings relevant to GeoSage modules
- Cross-reference papers with specific modules in the codebase