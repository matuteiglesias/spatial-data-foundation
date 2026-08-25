import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from spatial_foundation.geography import normalize_gadm_frame, relate_areal_objects


def _square(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _areal_inputs():
    polygons = gpd.GeoDataFrame(
        {"geo_uid": ["A"], "geometry_role": ["analytical"]},
        geometry=[_square(0, 0, 1, 1)],
        crs="EPSG:4326",
    )
    objects = gpd.GeoDataFrame(
        {"object_id": ["o1"]},
        geometry=[_square(0.1, 0.1, 0.2, 0.2)],
        crs="EPSG:4326",
    )
    return objects, polygons


def test_areal_overlap_rejects_geographic_area_crs():
    objects, polygons = _areal_inputs()

    with pytest.raises(ValueError, match="projected CRS with metre horizontal units"):
        relate_areal_objects(
            objects,
            polygons,
            object_id_col="object_id",
            area_crs="EPSG:4326",
        )


def test_areal_overlap_rejects_projected_foot_area_crs():
    objects, polygons = _areal_inputs()

    with pytest.raises(ValueError, match="metre horizontal units"):
        relate_areal_objects(
            objects,
            polygons,
            object_id_col="object_id",
            area_crs="EPSG:2263",
        )


def test_gadm_normalization_rejects_non_metre_area_units():
    frame = gpd.GeoDataFrame(
        {"GID_0": ["AAA"]},
        geometry=[_square(0, 0, 1, 1)],
        crs="EPSG:4326",
    )

    with pytest.raises(ValueError, match="metre horizontal units"):
        normalize_gadm_frame(frame, version="4.1", level=0, area_crs="EPSG:2263")


def test_metric_guard_accepts_projected_metre_crs_without_claiming_equal_area():
    objects, polygons = _areal_inputs()

    result, audit = relate_areal_objects(
        objects,
        polygons,
        object_id_col="object_id",
        area_crs="EPSG:3857",
    )

    assert result.loc[0, "overlap_area_m2"] > 0
    assert audit.matched_single == 1
