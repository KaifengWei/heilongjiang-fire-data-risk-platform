from fire_monitor.core.mcd64 import parse_mcd64_metadata, spherical_geographic_cell_area_km2


def test_parse_mcd64_filename_and_hash(tmp_path):
    path = tmp_path / "MCD64monthly.A2026060.Win16.061.burndate.tif"
    path.write_bytes(b"small test fixture")
    metadata = parse_mcd64_metadata(path)
    assert metadata.year == 2026
    assert metadata.month_start_doy == 60
    assert metadata.product == "MCD64A1"
    assert len(metadata.raster_sha256) == 64


def test_geographic_grid_area_changes_with_latitude():
    near_equator = spherical_geographic_cell_area_km2(0.00439453125, 1.0, 0.99560546875)
    near_heilongjiang = spherical_geographic_cell_area_km2(0.00439453125, 47.0, 46.99560546875)
    assert near_equator > 0
    assert near_heilongjiang > 0
    assert near_heilongjiang < near_equator
