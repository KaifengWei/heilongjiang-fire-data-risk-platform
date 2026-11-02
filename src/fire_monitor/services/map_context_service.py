"""Display-only regional boundary reference for observation-coordinate maps.

Only polygons already installed in the local boundary catalog are used.
No point is assigned a region by this helper; the geometry is a visual
reference, not a nationwide administrative lookup or a download service.
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import box, mapping, shape


def build_observation_boundary_context(
    installed_features: list[dict[str, Any]],
    observed_bbox: list[float] | tuple[float, ...] | None,
    *,
    simplify_degrees: float = 0.012,
    limit: int = 30,
) -> dict[str, Any]:
    """Include real installed outlines intersecting the observed viewport.

    The local data is already WGS84. Topology-preserving simplification
    reduces the 1:1M region polygons for responsive offline Canvas display.
    This must never be interpreted as validation of user-supplied labels.
    """
    empty = {"type": "FeatureCollection", "features": []}
    if not observed_bbox or len(observed_bbox) != 4:
        return empty

    try:
        west, south, east, north = (float(value) for value in observed_bbox)
    except (TypeError, ValueError):
        return empty
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        return empty

    x_pad = max(0.15, (east - west) * 0.08)
    y_pad = max(0.15, (north - south) * 0.08)
    viewport = box(west - x_pad, south - y_pad, east + x_pad, north + y_pad)
    features = []
    for feature in installed_features:
        if len(features) >= limit:
            break
        try:
            polygon = shape(feature["geometry"])
        except (KeyError, TypeError, ValueError):
            continue
        if (
            polygon.is_empty
            or not polygon.is_valid
            or polygon.geom_type not in ("Polygon", "MultiPolygon")
            or not polygon.intersects(viewport)
        ):
            continue
        simplified = polygon.simplify(simplify_degrees, preserve_topology=True)
        if simplified.is_empty:
            continue
        properties = feature.get("properties") or {}
        public_properties = {
            "name": str(properties.get("name") or ""),
            "source": str(properties.get("source") or "local_catalog"),
            "reference_only": True,
        }
        if properties.get("reference_layer") == "basemap":
            public_properties["reference_layer"] = "basemap"
        features.append({
            "type": "Feature",
            "properties": public_properties,
            "geometry": mapping(simplified),
        })
    return {"type": "FeatureCollection", "features": features}
