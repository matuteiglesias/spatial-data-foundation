from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
from shapely.geometry import MultiPolygon, Point, box

PRESET_WIDTHS = {"small": 8, "medium": 32, "large": 128}
POINT_CASES = ("uniform", "boundary", "outside", "dense_overlap")
AREAL_CASES = ("tiles", "cross_boundary", "slivers", "outside", "sparse_multipolygon")


@dataclass(frozen=True)
class PointWorkload:
    name: str
    points: gpd.GeoDataFrame
    polygons: gpd.GeoDataFrame


@dataclass(frozen=True)
class ArealWorkload:
    name: str
    objects: gpd.GeoDataFrame
    polygons: gpd.GeoDataFrame


def _width(preset: str) -> int:
    try:
        return PRESET_WIDTHS[preset]
    except KeyError as exc:
        raise ValueError(f"unknown benchmark preset: {preset!r}") from exc


def _grid_polygons(width: int) -> gpd.GeoDataFrame:
    ids: list[str] = []
    geometries = []
    for row in range(width):
        for column in range(width):
            ids.append(f"cell-{row:04d}-{column:04d}")
            geometries.append(box(column, row, column + 1.0, row + 1.0))
    return gpd.GeoDataFrame(
        {"geo_uid": ids, "geometry_role": ["analytical"] * len(ids)},
        geometry=geometries,
        crs="EPSG:3857",
    )


def make_point_workload(case: str, preset: str = "small") -> PointWorkload:
    width = _width(preset)
    polygons = _grid_polygons(width)

    if case == "uniform":
        geometries = [
            Point(column + 0.5, row + 0.5)
            for row in range(width)
            for column in range(width)
        ]
    elif case == "boundary":
        geometries = [
            Point(column, row + 0.5)
            for row in range(width)
            for column in range(1, width)
        ]
    elif case == "outside":
        geometries = [
            Point(width + 2.0 + column, row + 0.5)
            for row in range(width)
            for column in range(width)
        ]
    elif case == "dense_overlap":
        polygon_count = max(4, min(width, 32))
        dense_polygons = [box(-margin, -margin, 1.0 + margin, 1.0 + margin) for margin in range(polygon_count)]
        polygons = gpd.GeoDataFrame(
            {
                "geo_uid": [f"dense-{index:03d}" for index in range(polygon_count)],
                "geometry_role": ["analytical"] * polygon_count,
            },
            geometry=dense_polygons,
            crs="EPSG:3857",
        )
        point_count = width * width
        geometries = [
            Point(0.25 + (index % width) / (2 * width), 0.25 + (index // width) / (2 * width))
            for index in range(point_count)
        ]
    else:
        raise ValueError(f"unknown point benchmark case: {case!r}")

    points = gpd.GeoDataFrame(
        {"point_id": [f"point-{index:06d}" for index in range(len(geometries))]},
        geometry=geometries,
        crs="EPSG:3857",
    )
    return PointWorkload(name=f"point_{case}_{preset}", points=points, polygons=polygons)


def make_areal_workload(case: str, preset: str = "small") -> ArealWorkload:
    width = _width(preset)
    polygons = _grid_polygons(width)

    if case == "tiles":
        geometries = [
            box(column + 0.1, row + 0.1, column + 0.9, row + 0.9)
            for row in range(width)
            for column in range(width)
        ]
    elif case == "cross_boundary":
        geometries = [
            box(column - 0.2, row + 0.2, column + 0.2, row + 0.8)
            for row in range(width)
            for column in range(1, width)
        ]
    elif case == "slivers":
        geometries = [
            box(column + 0.2, row + 0.2, column + 1.000001, row + 0.8)
            for row in range(width)
            for column in range(width - 1)
        ]
    elif case == "outside":
        geometries = [
            box(width + 2.0 + column, row + 0.1, width + 2.8 + column, row + 0.9)
            for row in range(width)
            for column in range(width)
        ]
    elif case == "sparse_multipolygon":
        left_component = box(0.0, 0.0, 1.0, 1.0)
        right_component = box(float(width + 3), float(width + 3), float(width + 4), float(width + 4))
        polygons = gpd.GeoDataFrame(
            {"geo_uid": ["sparse-target"], "geometry_role": ["analytical"]},
            geometry=[MultiPolygon([left_component, right_component])],
            crs="EPSG:3857",
        )
        geometries = [
            box(1.5 + column * 0.5, 1.5 + row * 0.5, 1.7 + column * 0.5, 1.7 + row * 0.5)
            for row in range(width)
            for column in range(width)
        ]
        geometries.extend([box(0.2, 0.2, 0.4, 0.4), box(width + 3.2, width + 3.2, width + 3.4, width + 3.4)])
    else:
        raise ValueError(f"unknown areal benchmark case: {case!r}")

    objects = gpd.GeoDataFrame(
        {"object_id": [f"object-{index:06d}" for index in range(len(geometries))]},
        geometry=geometries,
        crs="EPSG:3857",
    )
    return ArealWorkload(name=f"areal_{case}_{preset}", objects=objects, polygons=polygons)
