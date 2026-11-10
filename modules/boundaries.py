"""
GeoSage - Boundary ingestion, validation and comparison (Stage 4).

Supports GeoJSON and KML uploads, validates geometry honestly, and
compares polygons with Shapely. Metric areas are computed ONLY in a
projected CRS (UTM zone derived from the geometry's centroid) - never
from raw latitude/longitude degrees.

Two coordinate spaces exist in the system and are never mixed:

  * geographic (lon/lat in EPSG:4326)  - uploaded GeoJSON/KML and drawn
    polygons on the Leaflet map,
  * image (pixel x/y)                  - polygons drawn on a plain
    non-georeferenced image, and candidate boundaries detected from the
    image.

A comparison between one geographic and one image-space polygon is
REJECTED with a clear message (that would silently produce nonsense).
"""
import json
import math
import xml.etree.ElementTree as ET

from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.validation import explain_validity

# --- Validation errors ---------------------------------------------------------

class BoundaryError(Exception):
    """Raised with a user-facing message when a boundary is invalid."""


GEOJSON_TYPES = {"Polygon", "MultiPolygon"}
KML_NS = "{http://www.opengis.net/kml/2.2}"


# --- Parsing ---------------------------------------------------------------------

def parse_geojson(raw_text):
    """Parse a GeoJSON Feature/FeatureCollection/geometry into shapely
    polygons. Raises BoundaryError with a clear message on problems."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise BoundaryError(f"Invalid GeoJSON: {exc.msg} at line {exc.lineno}.") from exc

    if not isinstance(data, dict):
        raise BoundaryError("GeoJSON must be an object.")

    crs_name = "EPSG:4326 (GeoJSON default)"
    if "crs" in data:  # legacy non-standard member; still seen in the wild
        crs = data["crs"]
        crs_name = crs.get("properties", {}).get("name", "") if isinstance(crs, dict) else ""
        if crs_name and "4326" not in str(crs_name) and "CRS84" not in str(crs_name):
            raise BoundaryError(
                f"Unsupported CRS '{crs_name}'. GeoSage accepts WGS84 "
                "(EPSG:4326 / CRS84) geographic coordinates only."
            )

    geometries = []
    if data.get("type") == "FeatureCollection":
        features = data.get("features") or []
        if not features:
            raise BoundaryError("FeatureCollection contains no features.")
        for feature in features:
            geom = feature.get("geometry")
            if geom:
                geometries.append(geom)
    elif data.get("type") == "Feature":
        if not data.get("geometry"):
            raise BoundaryError("Feature has no geometry.")
        geometries.append(data["geometry"])
    elif data.get("type") in GEOJSON_TYPES:
        geometries.append(data)
    else:
        raise BoundaryError(
            f"Geometry type '{data.get('type')}' is not supported. "
            "Use Polygon or MultiPolygon features."
        )

    polygons = []
    for geom in geometries:
        if geom.get("type") not in GEOJSON_TYPES:
            raise BoundaryError(
                f"Geometry type '{geom.get('type')}' is not supported; "
                "only Polygon / MultiPolygon are accepted."
            )
        try:
            shapely_geom = shape(geom)
        except (ValueError, AttributeError) as exc:
            raise BoundaryError(f"Geometry could not be parsed: {exc}") from exc
        for poly in _explode(shapely_geom):
            validate_polygon(poly)
            validate_coordinates(poly)
            polygons.append(poly)
    return polygons, crs_name


def parse_kml(raw_text):
    """Extract the first Polygon(s) from a KML document (WGS84 by spec)."""
    try:
        root = ET.fromstring(raw_text)
    except ET.ParseError as exc:
        raise BoundaryError(f"Invalid KML/XML: {exc}") from exc

    polygons = []
    for placemark_coords in root.iter(f"{KML_NS}outerBoundaryIs"):
        coords_node = placemark_coords.find(f".//{KML_NS}coordinates")
        if coords_node is not None and coords_node.text:
            polygons.append(_kml_ring(coords_node.text))
    if not polygons:  # tolerate KML written without boundaryIs wrappers
        for coords_node in root.iter(f"{KML_NS}coordinates"):
            if coords_node.text:
                polygons.append(_kml_ring(coords_node.text))
                break
    if not polygons:
        raise BoundaryError("No polygon coordinates found in the KML file.")
    for index, poly in enumerate(polygons):
        validate_polygon(poly, index)
        validate_coordinates(poly, index)
    return polygons, "EPSG:4326 (KML default)"


def _kml_ring(text):
    """Parse a KML 'lon,lat[,alt] lon,lat[,alt] ...' ring into a Polygon."""
    points = []
    for token in text.replace("\n", " ").split():
        parts = token.split(",")
        if len(parts) < 2:
            raise BoundaryError(f"Malformed KML coordinate '{token}'.")
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except ValueError as exc:
            raise BoundaryError(f"Non-numeric KML coordinate '{token}'.") from exc
        points.append((lon, lat))
    if len(points) < 4:
        raise BoundaryError("A KML polygon ring needs at least 4 coordinates.")
    return Polygon(points)


def _explode(geom):
    """Flatten MultiPolygon / GeometryCollection into a polygon list."""
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    polygons = []
    if hasattr(geom, "geoms"):
        for part in geom.geoms:
            polygons.extend(_explode(part))
    return polygons


# --- Validation --------------------------------------------------------------------

def validate_polygon(poly, index=0):
    """Validate one polygon; raises BoundaryError with precise reasons."""
    if poly.is_empty:
        raise BoundaryError(f"Polygon {index} is empty.")
    if not poly.is_valid:
        raise BoundaryError(
            f"Polygon {index} is geometrically invalid ({explain_validity(poly)}). "
            "Self-intersecting rings cannot be compared reliably."
        )
    if not poly.equals(poly.buffer(0)) or poly.area <= 0:
        raise BoundaryError(f"Polygon {index} encloses no area.")
    return True


def validate_coordinates(poly, index=0):
    """Geographic extents sanity: lon in [-180,180], lat in [-85,85].

    Rejects obviously swapped lon/lat pairs instead of silently
    producing a polygon at the wrong place on Earth.
    """
    lons = [c[0] for c in poly.exterior.coords]
    lats = [c[1] for c in poly.exterior.coords]
    if min(lons) < -180 or max(lons) > 180 or min(lats) < -85 or max(lats) > 85:
        raise BoundaryError(
            f"Polygon {index} has coordinates outside the WGS84 ranges "
            "(lon -180..180, lat -85..85). Did you swap longitude/latitude?"
        )
    return True


# --- Metric areas (projected CRS only) ------------------------------------------------

def utm_epsg_for(lon, lat):
    """UTM zone EPSG code (326xx north / 327xx south) for a lon/lat point."""
    zone = int(math.floor((lon + 180) / 6)) + 1
    zone = max(1, min(zone, 60))
    return (32600 if lat >= 0 else 32700) + zone


def projected_metrics(poly):
    """Return (area_m2, perimeter_m, epsg) for a WGS84 polygon.

    Projects to the local UTM zone via pyproj - the honest way to get
    metric areas from degree coordinates.
    """
    from pyproj import CRS, Transformer
    centroid = poly.centroid
    epsg = utm_epsg_for(centroid.x, centroid.y)
    transformer = Transformer.from_crs(CRS("EPSG:4326"), CRS(f"EPSG:{epsg}"),
                                       always_xy=True)
    projected = _transform_polygon(poly, transformer)
    return projected.area, projected.length, epsg


def _transform_polygon(poly, transformer):
    from shapely.ops import transform as shp_transform
    return shp_transform(lambda x, y, z=None: transformer.transform(x, y), poly)


# --- Comparison ------------------------------------------------------------------------

def compare_polygons(poly_a, poly_b, space="geographic"):
    """Full Shapely comparison of two polygons in the SAME coordinate space.

    Returns intersection/union/symmetric-difference WKT, IoU, overlap
    ratios, boundary (Hausdorff) distance and area difference. Metric
    areas are included only for geographic polygons (via UTM projection);
    image-space polygons report pixel areas only.
    """
    validate_polygon(poly_a)
    validate_polygon(poly_b)

    intersection = poly_a.intersection(poly_b)
    union = poly_a.union(poly_b)
    sym_diff = poly_a.symmetric_difference(poly_b)

    union_area = union.area
    iou = intersection.area / union_area if union_area > 0 else 0.0
    overlap_a = intersection.area / poly_a.area if poly_a.area > 0 else 0.0
    overlap_b = intersection.area / poly_b.area if poly_b.area > 0 else 0.0
    boundary_distance = poly_a.exterior.hausdorff_distance(poly_b.exterior)

    result = {
        "intersection_area": intersection.area,
        "union_area": union_area,
        "symmetric_difference_area": sym_diff.area,
        "iou": round(iou, 4),
        "overlap_in_recorded": round(overlap_a, 4),
        "overlap_in_candidate": round(overlap_b, 4),
        "boundary_distance": round(boundary_distance, 4),
        "area_difference": poly_a.area - poly_b.area,
        "space": space,
        "unit": "m²" if space == "geographic" else "px",
        "intersection_wkt": intersection.wkt,
        "symdiff_wkt": sym_diff.wkt,
    }

    if space == "geographic":
        area_a, _, epsg_a = projected_metrics(poly_a)
        area_b, _, _ = projected_metrics(poly_b)
        result["area_a_m2"] = area_a
        result["area_b_m2"] = area_b
        result["area_difference_m2"] = area_a - area_b
        result["projected_epsg"] = epsg_a

    return result


def screen_encroachment(recorded, candidate):
    """Possible-encroachment screening (review priorities, not verdicts).

    Compares the recorded polygon against the candidate polygon:

    - outside   : candidate area beyond the recorded boundary,
    - missing   : recorded area absent from the candidate,
    - displaced : mean boundary displacement (Hausdorff).

    Priorities by share of the recorded area affected:
    > 20% high, > 5% medium, otherwise low.
    """
    validate_polygon(recorded)
    validate_polygon(candidate)

    outside = candidate.difference(recorded)
    missing = recorded.difference(candidate)
    recorded_area = recorded.area

    outside_share = outside.area / recorded_area if recorded_area > 0 else 0.0
    missing_share = missing.area / recorded_area if recorded_area > 0 else 0.0
    displacement = recorded.exterior.hausdorff_distance(candidate.exterior)

    worst = max(outside_share, missing_share)
    if worst > 0.20 or (recorded_area > 0 and recorded.intersection(candidate).area == 0):
        priority = "high"
    elif worst > 0.05:
        priority = "medium"
    else:
        priority = "low"

    return {
        "outside_share": round(outside_share, 4),
        "missing_share": round(missing_share, 4),
        "displacement": round(displacement, 4),
        "priority": priority,
        "outside_wkt": outside.wkt,
        "missing_wkt": missing.wkt,
        "note": ("Screening aid only - highlights where the two polygons "
                 "disagree. It is not proof of encroachment and must be "
                 "verified by a surveyor."),
    }


# --- GeoJSON export helpers --------------------------------------------------------------

def polygon_to_geojson(poly):
    return json.dumps(mapping(poly))


def geojson_from_coords(coords, space="image"):
    """Build a GeoJSON polygon string from a coordinate list (validated)."""
    ring = [(float(x), float(y)) for x, y in coords]
    if len(ring) < 3:
        raise BoundaryError("A polygon needs at least 3 vertices.")
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    poly = Polygon(ring)
    validate_polygon(poly)
    if space == "geographic":
        validate_coordinates(poly)
    return poly
