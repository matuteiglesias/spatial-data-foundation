import geopandas as gpd
import pytest
from empirical_contracts import PeriodScheme
from shapely.geometry import Point, Polygon

from spatial_foundation.geography import assign_points, normalize_gadm_frame
from spatial_foundation.periods import PeriodIndex


def _square(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_exact_shared_vertex_reports_all_candidates_as_ambiguous():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["SW", "SE", "NW", "NE"]},
        geometry=[
            _square(0, 0, 1, 1),
            _square(1, 0, 2, 1),
            _square(0, 1, 1, 2),
            _square(1, 1, 2, 2),
        ],
        crs="EPSG:4326",
    )
    points = gpd.GeoDataFrame(
        {"point_id": ["vertex"]},
        geometry=[Point(1, 1)],
        crs="EPSG:4326",
    )

    result, audit = assign_points(points, polygons, point_id_col="point_id")

    assert set(result["geo_uid"].dropna()) == {"SW", "SE", "NW", "NE"}
    assert result["candidate_count"].unique().tolist() == [4]
    assert result["assignment_status"].unique().tolist() == ["ambiguous_multiple"]
    assert audit.ambiguous_multiple == 1


def test_overlapping_polygons_report_ambiguity_without_tie_breaking():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A", "B"]},
        geometry=[_square(0, 0, 2, 2), _square(1, 1, 3, 3)],
        crs="EPSG:4326",
    )
    points = gpd.GeoDataFrame(
        {"point_id": ["overlap"]},
        geometry=[Point(1.5, 1.5)],
        crs="EPSG:4326",
    )

    result, audit = assign_points(points, polygons, point_id_col="point_id")

    assert set(result["geo_uid"].dropna()) == {"A", "B"}
    assert result["candidate_count"].unique().tolist() == [2]
    assert result["assignment_status"].unique().tolist() == ["ambiguous_multiple"]
    assert audit.ambiguous_multiple == 1


def test_point_outside_polygon_coverage_remains_explicitly_unmatched():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"]},
        geometry=[_square(0, 0, 1, 1)],
        crs="EPSG:4326",
    )
    points = gpd.GeoDataFrame(
        {"point_id": ["outside"]},
        geometry=[Point(5, 5)],
        crs="EPSG:4326",
    )

    result, audit = assign_points(points, polygons, point_id_col="point_id")

    assert result.loc[0, "assignment_status"] == "unmatched_outside"
    assert result.loc[0, "candidate_count"] == 0
    assert audit.unmatched_outside == 1


def test_duplicate_point_ids_are_rejected_before_spatial_join():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"]},
        geometry=[_square(0, 0, 1, 1)],
        crs="EPSG:4326",
    )
    points = gpd.GeoDataFrame(
        {"point_id": ["dup", "dup"]},
        geometry=[Point(0.25, 0.25), Point(0.75, 0.75)],
        crs="EPSG:4326",
    )

    with pytest.raises(ValueError, match="point IDs must be unique"):
        assign_points(points, polygons, point_id_col="point_id")


@pytest.mark.parametrize("missing_on", ["points", "polygons"])
def test_point_assignment_rejects_missing_crs(missing_on):
    point_crs = None if missing_on == "points" else "EPSG:4326"
    polygon_crs = None if missing_on == "polygons" else "EPSG:4326"
    points = gpd.GeoDataFrame(
        {"point_id": ["p"]}, geometry=[Point(0.5, 0.5)], crs=point_crs
    )
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"]}, geometry=[_square(0, 0, 1, 1)], crs=polygon_crs
    )

    with pytest.raises(ValueError, match="require a CRS"):
        assign_points(points, polygons, point_id_col="point_id")


def test_gadm_normalization_rejects_missing_crs(synthetic_gadm_level2):
    frame = synthetic_gadm_level2.iloc[[0]].copy().set_crs(None, allow_override=True)

    with pytest.raises(ValueError, match="declared CRS"):
        normalize_gadm_frame(frame, version="4.1", level=2)


def test_gadm_normalization_rejects_duplicate_geography_ids(synthetic_gadm_level2):
    frame = synthetic_gadm_level2.iloc[[0, 0]].copy()

    with pytest.raises(ValueError, match="duplicate geography IDs"):
        normalize_gadm_frame(frame, version="4.1", level=2)


def test_point_assignment_rejects_duplicate_geography_ids():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A", "A"]},
        geometry=[_square(0, 0, 1, 1), _square(1, 0, 2, 1)],
        crs="EPSG:4326",
    )
    points = gpd.GeoDataFrame(
        {"point_id": ["p"]},
        geometry=[Point(0.5, 0.5)],
        crs="EPSG:4326",
    )

    with pytest.raises(ValueError, match="polygon IDs must be unique"):
        assign_points(points, polygons, point_id_col="point_id")


def test_early_gregorian_period_is_supported_but_nonpositive_years_are_rejected():
    index = PeriodIndex(PeriodScheme(width_years=2, anchor_year=2001))

    period = index.period_for(1)
    assert period.period_id == "1-2"
    assert period.start_year == 1
    assert period.end_year == 2

    for year in (0, -1, -100):
        with pytest.raises(ValueError):
            index.period_for(year)


def test_display_geometry_cannot_enter_point_assignment():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"], "geometry_role": ["display"]},
        geometry=[_square(0, 0, 1, 1)],
        crs="EPSG:4326",
    )
    points = gpd.GeoDataFrame(
        {"point_id": ["p"]},
        geometry=[Point(0.5, 0.5)],
        crs="EPSG:4326",
    )

    with pytest.raises(ValueError, match="analytical geometry"):
        assign_points(points, polygons, point_id_col="point_id")
