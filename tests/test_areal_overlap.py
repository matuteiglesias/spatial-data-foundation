import math

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

from spatial_foundation.geography import ArealOverlapAudit, relate_areal_objects


def _square(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_areal_overlap_preserves_legitimate_many_to_many_relation():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A", "B"], "geometry_role": ["analytical", "analytical"]},
        geometry=[_square(0, 0, 1, 1), _square(1, 0, 2, 1)],
        crs="EPSG:4326",
    )
    objects = gpd.GeoDataFrame(
        {"project_id": ["cross", "inside", "outside"]},
        geometry=[_square(0.5, 0.2, 1.5, 0.8), _square(0.1, 0.1, 0.4, 0.4), _square(3, 3, 4, 4)],
        crs="EPSG:4326",
    )

    result, audit = relate_areal_objects(objects, polygons, object_id_col="project_id")

    cross = result.loc[result["project_id"].eq("cross")].sort_values("geo_uid")
    assert cross["geo_uid"].tolist() == ["A", "B"]
    assert cross["relation_status"].tolist() == ["matched_multiple", "matched_multiple"]
    assert cross["overlap_count"].tolist() == [2, 2]
    assert math.isclose(float(cross["overlap_share_of_object"].sum()), 1.0, rel_tol=1e-5)

    inside = result.loc[result["project_id"].eq("inside")].iloc[0]
    assert inside["geo_uid"] == "A"
    assert inside["relation_status"] == "matched_single"
    assert math.isclose(float(inside["overlap_share_of_object"]), 1.0, rel_tol=1e-5)

    outside = result.loc[result["project_id"].eq("outside")].iloc[0]
    assert pd.isna(outside["geo_uid"])
    assert outside["relation_status"] == "unmatched_outside"

    assert audit == ArealOverlapAudit(
        input_objects=3,
        matched_single=1,
        matched_multiple=1,
        unmatched_outside=1,
        invalid_geometry=0,
        relation_rows=3,
    )


def test_areal_overlap_excludes_boundary_only_touch():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"], "geometry_role": ["analytical"]},
        geometry=[_square(0, 0, 1, 1)],
        crs="EPSG:4326",
    )
    objects = gpd.GeoDataFrame(
        {"project_id": ["touch"]},
        geometry=[_square(1, 0.2, 1.5, 0.8)],
        crs="EPSG:4326",
    )

    result, audit = relate_areal_objects(objects, polygons, object_id_col="project_id")

    assert len(result) == 1
    assert pd.isna(result.loc[0, "geo_uid"])
    assert result.loc[0, "relation_status"] == "unmatched_outside"
    assert audit.relation_rows == 0


def test_areal_overlap_marks_missing_or_invalid_source_geometry():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"], "geometry_role": ["analytical"]},
        geometry=[_square(0, 0, 1, 1)],
        crs="EPSG:4326",
    )
    objects = gpd.GeoDataFrame(
        {"project_id": ["missing"]},
        geometry=[None],
        crs="EPSG:4326",
    )

    result, audit = relate_areal_objects(objects, polygons, object_id_col="project_id")

    assert result.loc[0, "relation_status"] == "invalid_geometry"
    assert audit.invalid_geometry == 1


def test_areal_overlap_rejects_display_geography():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"], "geometry_role": ["display"]},
        geometry=[_square(0, 0, 1, 1)],
        crs="EPSG:4326",
    )
    objects = gpd.GeoDataFrame(
        {"project_id": ["p1"]},
        geometry=[_square(0.1, 0.1, 0.2, 0.2)],
        crs="EPSG:4326",
    )

    with pytest.raises(ValueError, match="analytical geography"):
        relate_areal_objects(objects, polygons, object_id_col="project_id")


def test_areal_overlap_rejects_non_areal_source_geometry():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"], "geometry_role": ["analytical"]},
        geometry=[_square(0, 0, 1, 1)],
        crs="EPSG:4326",
    )
    objects = gpd.GeoDataFrame(
        {"project_id": ["point"]},
        geometry=[Point(0.5, 0.5)],
        crs="EPSG:4326",
    )

    with pytest.raises(ValueError, match="Use point membership"):
        relate_areal_objects(objects, polygons, object_id_col="project_id")


def test_external_consumer_gets_metric_60_40_candidates_without_assignment():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["west", "east"], "geometry_role": ["analytical", "analytical"]},
        geometry=[_square(0, 0, 400, 1000), _square(400, 0, 1000, 1000)],
        crs="EPSG:3857",
    )
    objects = gpd.GeoDataFrame(
        {"unit_id": ["cross"]},
        geometry=[_square(0, 0, 1000, 1000)],
        crs="EPSG:3857",
    )

    result, audit = relate_areal_objects(
        objects,
        polygons,
        object_id_col="unit_id",
        area_crs="EPSG:3857",
    )
    candidates = result.sort_values("geo_uid").reset_index(drop=True)

    assert candidates["geo_uid"].tolist() == ["east", "west"]
    assert candidates["overlap_area_m2"].tolist() == pytest.approx([600_000, 400_000])
    assert candidates["overlap_share_of_object"].tolist() == pytest.approx([0.6, 0.4])
    assert candidates["relation_status"].tolist() == ["matched_multiple", "matched_multiple"]
    assert candidates["overlap_count"].tolist() == [2, 2]
    assert {
        "assigned_geo_uid",
        "assignment_status",
        "winner",
        "winner_share",
    }.isdisjoint(result.columns)
    assert audit.matched_multiple == 1


def test_external_consumer_can_set_a_positive_sliver_threshold():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["main", "sliver"], "geometry_role": ["analytical", "analytical"]},
        geometry=[_square(0, 0, 9.5, 1), _square(9.5, 0, 10, 1)],
        crs="EPSG:3857",
    )
    objects = gpd.GeoDataFrame(
        {"unit_id": ["u1"]},
        geometry=[_square(0, 0, 10, 1)],
        crs="EPSG:3857",
    )

    result, audit = relate_areal_objects(
        objects,
        polygons,
        object_id_col="unit_id",
        area_crs="EPSG:3857",
        min_overlap_area_m2=0.5,
    )

    assert result["geo_uid"].tolist() == ["main"]
    assert result.loc[0, "overlap_area_m2"] == pytest.approx(9.5)
    assert result.loc[0, "overlap_share_of_object"] == pytest.approx(0.95)
    assert result.loc[0, "relation_status"] == "matched_single"
    assert audit.relation_rows == 1


def test_equal_and_near_equal_candidates_remain_unresolved_geometric_facts():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["left", "right"], "geometry_role": ["analytical", "analytical"]},
        geometry=[_square(0, 0, 1.0000004, 1), _square(1.0000004, 0, 2, 1)],
        crs="EPSG:3857",
    )
    objects = gpd.GeoDataFrame(
        {"unit_id": ["near_tie"]},
        geometry=[_square(0, 0, 2, 1)],
        crs="EPSG:3857",
    )

    result, _ = relate_areal_objects(
        objects,
        polygons,
        object_id_col="unit_id",
        area_crs="EPSG:3857",
    )
    candidates = result.sort_values("geo_uid").reset_index(drop=True)

    assert candidates["geo_uid"].tolist() == ["left", "right"]
    assert candidates["relation_status"].tolist() == ["matched_multiple", "matched_multiple"]
    assert candidates["overlap_share_of_object"].sum() == pytest.approx(1.0)
    assert abs(candidates.loc[0, "overlap_area_m2"] - candidates.loc[1, "overlap_area_m2"]) < 1e-6


def test_external_consumer_duplicate_source_ids_fail_closed():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"], "geometry_role": ["analytical"]},
        geometry=[_square(0, 0, 2, 2)],
        crs="EPSG:3857",
    )
    objects = gpd.GeoDataFrame(
        {"unit_id": ["duplicate", "duplicate"]},
        geometry=[_square(0, 0, 1, 1), _square(1, 1, 2, 2)],
        crs="EPSG:3857",
    )

    with pytest.raises(ValueError, match="object IDs must be non-missing and unique"):
        relate_areal_objects(objects, polygons, object_id_col="unit_id", area_crs="EPSG:3857")


def test_relation_semantics_are_canonicalizable_without_row_order_contract():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A", "B"], "geometry_role": ["analytical", "analytical"]},
        geometry=[_square(0, 0, 1, 1), _square(1, 0, 2, 1)],
        crs="EPSG:3857",
    )
    objects = gpd.GeoDataFrame(
        {"unit_id": ["cross"]},
        geometry=[_square(0.5, 0, 1.5, 1)],
        crs="EPSG:3857",
    )

    first, _ = relate_areal_objects(
        objects,
        polygons,
        object_id_col="unit_id",
        area_crs="EPSG:3857",
    )
    second, _ = relate_areal_objects(
        objects,
        polygons.iloc[::-1].reset_index(drop=True),
        object_id_col="unit_id",
        area_crs="EPSG:3857",
    )
    columns = [
        "unit_id",
        "geo_uid",
        "overlap_area_m2",
        "overlap_share_of_object",
        "overlap_count",
        "relation_status",
    ]
    first_canonical = first[columns].sort_values(["unit_id", "geo_uid"]).reset_index(drop=True)
    second_canonical = second[columns].sort_values(["unit_id", "geo_uid"]).reset_index(drop=True)

    pd.testing.assert_frame_equal(first_canonical, second_canonical)
