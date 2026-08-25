from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from ._validation import require_analytical_polygons, require_projected_metre_crs


@dataclass(frozen=True)
class ArealOverlapAudit:
    input_objects: int
    matched_single: int
    matched_multiple: int
    unmatched_outside: int
    invalid_geometry: int
    relation_rows: int


def _areal_geometry_masks(objects: gpd.GeoDataFrame) -> tuple[np.ndarray, np.ndarray]:
    geometry = objects.geometry
    values = geometry.array
    missing = np.asarray(shapely.is_missing(values), dtype=bool)
    empty = np.asarray(shapely.is_empty(values), dtype=bool)
    nonempty = ~(missing | empty)
    type_ids = np.asarray(shapely.get_type_id(values))
    allowed = np.isin(
        type_ids,
        [int(shapely.GeometryType.POLYGON), int(shapely.GeometryType.MULTIPOLYGON)],
    )
    non_areal = nonempty & ~allowed
    if non_areal.any():
        found = sorted(geometry.iloc[np.flatnonzero(non_areal)].geom_type.unique().tolist())
        raise ValueError(
            "relate_areal_objects accepts Polygon/MultiPolygon source geometry only; "
            f"found {found}. Use point membership for point sources."
        )
    valid = nonempty & np.asarray(shapely.is_valid(values), dtype=bool)
    return valid, ~valid


def _indexed_positive_overlap_pairs(
    objects: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    *,
    valid_positions: np.ndarray,
    area_crs: str,
    min_overlap_area_m2: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return retained source/target positions plus vectorized area facts."""
    if valid_positions.size == 0:
        empty_int = np.empty(0, dtype=np.intp)
        empty_float = np.empty(0, dtype="float64")
        return empty_int, empty_int.copy(), empty_float, empty_float.copy()

    valid_objects = objects.iloc[valid_positions]
    query_objects = valid_objects[[objects.geometry.name]].to_crs(polygons.crs)
    query_idx, polygon_idx = polygons.geometry.sindex.query(
        query_objects.geometry,
        predicate="intersects",
        sort=False,
    )
    query_idx = np.asarray(query_idx, dtype=np.intp)
    polygon_idx = np.asarray(polygon_idx, dtype=np.intp)
    if query_idx.size == 0:
        empty_int = np.empty(0, dtype=np.intp)
        empty_float = np.empty(0, dtype="float64")
        return empty_int, empty_int.copy(), empty_float, empty_float.copy()

    metric_objects = valid_objects[[objects.geometry.name]].to_crs(area_crs)
    metric_polygons = polygons[[polygons.geometry.name]].to_crs(area_crs)
    source_geometry = metric_objects.geometry.array.take(query_idx)
    target_geometry = metric_polygons.geometry.array.take(polygon_idx)

    overlap_area = np.asarray(
        shapely.area(shapely.intersection(source_geometry, target_geometry)),
        dtype="float64",
    )
    object_area = np.asarray(shapely.area(metric_objects.geometry.array), dtype="float64")
    overlap_share = overlap_area / object_area[query_idx]
    retained = overlap_area > min_overlap_area_m2

    return (
        valid_positions[query_idx[retained]],
        polygon_idx[retained],
        overlap_area[retained],
        overlap_share[retained],
    )


def relate_areal_objects(
    objects: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    *,
    object_id_col: str,
    polygon_id_col: str = "geo_uid",
    area_crs: str = "EPSG:6933",
    min_overlap_area_m2: float = 0.0,
) -> tuple[pd.DataFrame, ArealOverlapAudit]:
    """Relate areal source objects to analytical geography without assigning ownership.

    One source geometry may legitimately overlap several geography units. Those rows are
    retained as a many-to-many relation rather than treated as assignment ambiguity.
    Intersection area and the share of the source object's area are geometric facts only;
    they do not allocate money, exposure, population, or any other substantive quantity.

    ``area_crs`` must be a projected CRS with metre horizontal units because the
    emitted area column is explicitly labelled in square metres. This unit check does
    not imply that every metre projection is equal-area.

    Candidate generation uses the target GeoSeries' cached spatial index. Exact
    intersections and areas are evaluated as Shapely vector operations over candidate
    arrays. Boundary-only touches have zero intersection area and are excluded by
    default. Candidate row order is not semantic.
    """
    if min_overlap_area_m2 < 0:
        raise ValueError("min_overlap_area_m2 must be non-negative")
    if objects.crs is None:
        raise ValueError("areal relation source objects require a CRS")
    if object_id_col not in objects.columns:
        raise ValueError(f"missing object id column: {object_id_col}")
    if objects[object_id_col].isna().any() or objects[object_id_col].duplicated().any():
        raise ValueError("object IDs must be non-missing and unique")
    require_analytical_polygons(
        polygons,
        polygon_id_col=polygon_id_col,
        operation="areal overlap",
    )
    require_projected_metre_crs(area_crs)

    valid, invalid = _areal_geometry_masks(objects)
    valid_positions = np.flatnonzero(valid)
    source_positions, polygon_positions, overlap_area, overlap_share = (
        _indexed_positive_overlap_pairs(
            objects,
            polygons,
            valid_positions=valid_positions,
            area_crs=area_crs,
            min_overlap_area_m2=min_overlap_area_m2,
        )
    )

    overlap_counts = np.bincount(source_positions, minlength=len(objects))
    status = np.full(len(objects), "invalid_geometry", dtype=object)
    status[valid & (overlap_counts == 0)] = "unmatched_outside"
    status[valid & (overlap_counts == 1)] = "matched_single"
    status[valid & (overlap_counts > 1)] = "matched_multiple"

    unmatched_positions = np.flatnonzero(valid & (overlap_counts == 0))
    invalid_positions = np.flatnonzero(invalid)
    result_source_positions = np.concatenate(
        [source_positions, unmatched_positions, invalid_positions]
    )
    relation_count = len(source_positions)

    polygon_values = np.empty(len(result_source_positions), dtype=object)
    area_values = np.empty(len(result_source_positions), dtype=object)
    share_values = np.empty(len(result_source_positions), dtype=object)
    if relation_count:
        polygon_values[:relation_count] = polygons[polygon_id_col].to_numpy(
            copy=False
        )[polygon_positions]
        area_values[:relation_count] = overlap_area
        share_values[:relation_count] = overlap_share
    polygon_values[relation_count:] = pd.NA
    area_values[relation_count:] = pd.NA
    share_values[relation_count:] = pd.NA

    result = pd.DataFrame(
        {
            object_id_col: objects[object_id_col].to_numpy(copy=False)[
                result_source_positions
            ],
            polygon_id_col: polygon_values,
            "overlap_area_m2": area_values,
            "overlap_share_of_object": share_values,
            "overlap_count": overlap_counts[result_source_positions],
            "relation_status": status[result_source_positions],
        }
    )

    audit = ArealOverlapAudit(
        input_objects=len(objects),
        matched_single=int(np.count_nonzero(status == "matched_single")),
        matched_multiple=int(np.count_nonzero(status == "matched_multiple")),
        unmatched_outside=int(np.count_nonzero(status == "unmatched_outside")),
        invalid_geometry=int(np.count_nonzero(status == "invalid_geometry")),
        relation_rows=relation_count,
    )
    return result, audit
