import math

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

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
    from shapely.geometry import Point

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
