import geopandas as gpd
import pytest
from shapely.geometry import Point, Polygon

from spatial_foundation.geography import assign_points, normalize_gadm_frame


def test_normalize_gadm_keeps_full_geometry_and_hierarchy(synthetic_gadm_level2):
    frame = synthetic_gadm_level2.iloc[[0]].copy()
    out = normalize_gadm_frame(frame, version="4.1", level=2, area_crs="EPSG:6933")
    row = out.iloc[0]
    assert row.geo_uid == "gadm:4.1:adm2:AAA.1.1_1"
    assert row.parent_geo_uid == "gadm:4.1:adm1:AAA.1_1"
    assert row.geometry.equals(frame.geometry.iloc[0])
    assert row.area_km2 > 0
    assert row.geometry_role == "analytical"
    assert out.crs.to_string() == "EPSG:4326"
    assert out.attrs["area_crs"] == "EPSG:6933"
    assert out.attrs["geometry_profile"] == {"rows": 1, "null": 0, "invalid": 0}


def test_normalize_gadm_preserves_missing_parent_as_missing(synthetic_gadm_level2):
    out = normalize_gadm_frame(synthetic_gadm_level2.iloc[[1]].copy(), version="4.1", level=2)
    assert out.iloc[0].parent_geo_uid is None


def test_normalize_gadm_rejects_unresolvable_country_identity(synthetic_gadm_level2):
    frame = synthetic_gadm_level2.iloc[[0]].copy()
    frame["GID_0"] = [None]
    with pytest.raises(ValueError, match="country identity"):
        normalize_gadm_frame(frame, version="4.1", level=2)


def test_normalize_gadm_rejects_blank_source_id(synthetic_gadm_level2):
    frame = synthetic_gadm_level2.iloc[[0]].copy()
    frame["GID_2"] = [""]
    with pytest.raises(ValueError, match="source geography identity"):
        normalize_gadm_frame(frame, version="4.1", level=2)


def test_point_membership_reports_unique_unmatched_and_boundary_ambiguity():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A", "B"]},
        geometry=[
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            Polygon([(1, 0), (2, 0), (2, 1), (1, 1)]),
        ],
        crs="EPSG:4326",
    )
    points = gpd.GeoDataFrame(
        {"event_id": ["inside", "outside", "boundary"]},
        geometry=[Point(0.5, 0.5), Point(3, 3), Point(1, 0.5)],
        crs="EPSG:4326",
    )
    result, audit = assign_points(points, polygons, point_id_col="event_id")
    status = result[["event_id", "assignment_status"]].drop_duplicates().set_index("event_id")["assignment_status"]
    assert status["inside"] == "matched_unique"
    assert status["outside"] == "unmatched_outside"
    assert status["boundary"] == "ambiguous_multiple"
    assert audit.input_points == 3
    assert audit.matched_unique == 1
    assert audit.unmatched_outside == 1
    assert audit.ambiguous_multiple == 1
