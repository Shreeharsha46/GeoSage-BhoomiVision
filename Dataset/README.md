# Dataset Folder

This folder contains all datasets used for the GeoSage — BHOOMI VISION project.

## Expected Contents

### Satellite/Drone Imagery
- Historical satellite imagery (previous captures)
- Recent satellite/drone imagery (current captures)
- Supported formats: JPG, PNG, TIFF, GeoTIFF
- Recommended resolution: ≥ 0.5m/pixel for change detection

### Sample Datasets (for testing/demo)
- `sample_old.png` – Previous satellite image
- `sample_recent.png` – Recent satellite image  
- `sample_boundary.geojson` – Sample parcel boundary

### Data Organization
```
Dataset/
├── raw/                    # Raw imagery
├── processed/              # Preprocessed/registered images
├── boundaries/             # GeoJSON/KML boundary files
├── test/                   # Test images for unit tests
└── sample/                 # Demo/sample data
```

## Data Requirements
- Images must be co-registered (same spatial extent)
- GeoTIFF files should have valid CRS metadata (EPSG:4326 recommended)
- Boundary files: GeoJSON or KML format with Polygon geometry
- CRS: WGS84 (EPSG:4326) or UTM zones for metric calculations

## Sample Data Sources
- USGS EarthExplorer (Landsat/Sentinel)
- Copernicus Open Access Hub (Sentinel-2)
- NASA Earthdata (MODIS, ASTER)
- Local drone surveys