import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, Polygon

from spatial_foundation.geography import MembershipAudit, assign_points


def _square(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _candidate_pairs(result, point_id_col="point_id", polygon_id_col="geo_uid"):
    matched = result.dropna(subset=[polygon_id_col])
    return set(matched[[point_id_col, polygon_id_col]].itertuples(index=False, name=None))


def test_membership_kernel_emits_candidates_statuses_and_audit():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A", "B"], "geometry_role": ["analytical", "analytical"]},
        geometry=[_square(0, 0, 1, 1), _square(1, 0, 2, 1)],
        crs="EPSG:4326",
    )
    points = gpd.GeoDataFrame(
        {"point_id": ["inside-a", "inside-b", "outside", "boundary"]},
        geometry=[Point(0.25, 0.5), Point(1.75, 0.5), Point(3, 3), Point(1, 0.5)],
        crs="EPSG:4326",
    )

    result, audit = assign_points(points, polygons, point_id_col="point_id")

    assert _candidate_pairs(result) == {
        ("inside-a", "A"),
        ("inside-b", "B"),
        ("boundary", "A"),
        ("boundary", "B"),
    }

    point_status = (
        result[["point_id", "candidate_count", "assignment_status"]]
        .drop_duplicates()
        .set_index("point_id")
    )
    assert point_status.loc["inside-a"].to_dict() == {
        "candidate_count": 1,
        "assignment_status": "matched_unique",
    }
    assert point_status.loc["inside-b"].to_dict() == {
        "candidate_count": 1,
        "assignment_status": "matched_unique",
    }
    assert point_status.loc["outside"].to_dict() == {
        "candidate_count": 0,
        "assignment_status": "unmatched_outside",
    }
    assert point_status.loc["boundary"].to_dict() == {
        "candidate_count": 2,
        "assignment_status": "ambiguous_multiple",
    }
    assert audit == MembershipAudit(
        input_points=4,
        matched_unique=2,
        unmatched_outside=1,
        ambiguous_multiple=1,
    )


def test_membership_kernel_reprojects_points_to_polygon_crs():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"], "geometry_role": ["analytical"]},
        geometry=[_square(0, 0, 1, 1)],
        crs="EPSG:4326",
    ).to_crs("EPSG:3857")
    points = gpd.GeoDataFrame(
        {"point_id": ["inside"]},
        geometry=[Point(0.5, 0.5)],
        crs="EPSG:4326",
    )

    result, audit = assign_points(points, polygons, point_id_col="point_id")

    assert _candidate_pairs(result) == {("inside", "A")}
    assert result.loc[0, "assignment_status"] == "matched_unique"
    assert audit.matched_unique == 1


def test_membership_kernel_retains_missing_and_empty_points_as_invalid():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"], "geometry_role": ["analytical"]},
        geometry=[_square(0, 0, 1, 1)],
        crs="EPSG:4326",
    )
    points = gpd.GeoDataFrame(
        {"point_id": ["valid", "empty", "missing"]},
        geometry=[Point(0.5, 0.5), Point(), None],
        crs="EPSG:4326",
    )

    result, audit = assign_points(points, polygons, point_id_col="point_id")
    statuses = (
        result[["point_id", "candidate_count", "assignment_status"]]
        .drop_duplicates()
        .set_index("point_id")
    )

    assert statuses.loc["valid"].to_dict() == {
        "candidate_count": 1,
        "assignment_status": "matched_unique",
    }
    assert statuses.loc["empty"].to_dict() == {
        "candidate_count": 0,
        "assignment_status": "invalid_point",
    }
    assert statuses.loc["missing"].to_dict() == {
        "candidate_count": 0,
        "assignment_status": "invalid_point",
    }
    assert audit == MembershipAudit(
        input_points=3,
        matched_unique=1,
        unmatched_outside=0,
        ambiguous_multiple=0,
        invalid_point=2,
    )


def test_membership_kernel_rejects_unsupported_source_geometry_family():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"], "geometry_role": ["analytical"]},
        geometry=[_square(0, 0, 1, 1)],
        crs="EPSG:4326",
    )
    points = gpd.GeoDataFrame(
        {"point_id": ["not-a-point"]},
        geometry=[LineString([(0.2, 0.2), (0.8, 0.8)])],
        crs="EPSG:4326",
    )

    with pytest.raises(ValueError, match="Point source geometry only"):
        assign_points(points, polygons, point_id_col="point_id")


def test_membership_kernel_rejects_invalid_target_geography():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"], "geometry_role": ["display"]},
        geometry=[_square(0, 0, 1, 1)],
        crs="EPSG:4326",
    )
    points = gpd.GeoDataFrame(
        {"point_id": ["point"]},
        geometry=[Point(0.5, 0.5)],
        crs="EPSG:4326",
    )

    with pytest.raises(ValueError, match="requires analytical geometry"):
        assign_points(points, polygons, point_id_col="point_id")


def test_membership_kernel_matches_recovered_legacy_overlay_sample():
    """Parity with the recovered 2023_Duke spatial-intersection implementation.

    The legacy notebook `51 - Spatial Intersection` used
    `gpd.overlay(points, areas, how="intersection")` to generate point-to-GID
    rows. The new kernel is intentionally richer for outside/boundary cases, but
    its candidate pairs must match that legacy operation for ordinary interior
    points.
    """
    areas = gpd.GeoDataFrame(
        {"GID": ["AAA.1_1", "AAA.2_1"]},
        geometry=[_square(0, 0, 1, 1), _square(1, 0, 2, 1)],
        crs="EPSG:4326",
    )
    points = gpd.GeoDataFrame(
        {"event_id": ["legacy-1", "legacy-2", "legacy-3"]},
        geometry=[Point(0.2, 0.2), Point(0.8, 0.7), Point(1.4, 0.4)],
        crs="EPSG:4326",
    )

    legacy = gpd.overlay(points, areas, how="intersection")
    result, audit = assign_points(
        points,
        areas,
        point_id_col="event_id",
        polygon_id_col="GID",
    )

    legacy_pairs = set(legacy[["event_id", "GID"]].itertuples(index=False, name=None))
    kernel_pairs = _candidate_pairs(result, point_id_col="event_id", polygon_id_col="GID")

    assert kernel_pairs == legacy_pairs
    assert set(result["assignment_status"]) == {"matched_unique"}
    assert audit == MembershipAudit(
        input_points=3,
        matched_unique=3,
        unmatched_outside=0,
        ambiguous_multiple=0,
    )
