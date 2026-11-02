"""The optional Canvas boundary layer must be derived from real data."""

from fire_monitor.services.map_context_service import build_observation_boundary_context


def test_only_intersecting_installed_polygons_render_without_inferred_membership():
    local = {
        "type": "Feature",
        "properties": {"name": "本地示例", "source": "test"},
        "geometry": {"type": "Polygon", "coordinates": [[
            [110, 30], [111, 30], [111, 31], [110, 31], [110, 30],
        ]]},
    }
    remote = {
        "type": "Feature",
        "properties": {"name": "远处示例", "source": "test"},
        "geometry": {"type": "Polygon", "coordinates": [[
            [145, 40], [146, 40], [146, 41], [145, 41], [145, 40],
        ]]},
    }
    collection = build_observation_boundary_context(
        [local, remote], [110.2, 30.2, 110.8, 30.8],
    )
    assert len(collection["features"]) == 1
    assert collection["features"][0]["properties"]["name"] == "本地示例"
    assert collection["features"][0]["properties"]["reference_only"] is True
    assert build_observation_boundary_context([remote], [110, 30, 111, 31])["features"] == []
    assert build_observation_boundary_context([local], None)["features"] == []


def test_reference_basemap_marker_survives_geometry_simplification():
    feature = {
        "type": "Feature",
        "properties": {"name": "真实测试轮廓", "reference_layer": "basemap",
                       "source": "测试来源"},
        "geometry": {"type": "Polygon", "coordinates": [[
            [110, 30], [111, 30], [111, 31], [110, 31], [110, 30],
        ]]},
    }
    collection = build_observation_boundary_context([feature], [110, 30, 111, 31])
    assert collection["features"][0]["properties"]["reference_layer"] == "basemap"
    assert collection["features"][0]["properties"]["reference_only"] is True
