from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from ._validation import require_analytical_polygons, require_unique_nonmissing_ids
from .models import MembershipStatus


@dataclass(frozen=True)
class MembershipAudit:
    input_points: int
    matched_unique: int
    unmatched_outside: int
    ambiguous_multiple: int
    invalid_point: int = 0


def _point_geometry_masks(points: gpd.GeoDataFrame) -> tuple[np.ndarray, np.ndarray]:
    geometry = points.geometry
    values = geometry.array
    missing = np.asarray(shapely.is_missing(values), dtype=bool)
    empty = np.asarray(shapely.is_empty(values), dtype=bool)
    nonempty = ~(missing | empty)
    type_ids = np.asarray(shapely.get_type_id(values))
    unsupported = nonempty & (type_ids != int(shapely.GeometryType.POINT))
    if unsupported.any():
        found = sorted(geometry.iloc[np.flatnonzero(unsupported)].geom_type.unique().tolist())
        raise ValueError(f"assign_points accepts Point source geometry only; found {found}")
    valid = nonempty & np.asarray(shapely.is_valid(values), dtype=bool)
    return valid, ~valid


def assign_points(
    points: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    *,
    point_id_col: str,
    polygon_id_col: str = "geo_uid",
) -> tuple[pd.DataFrame, MembershipAudit]:
    """Return candidate memberships and explicit point-level assignment status.

    Missing, empty, or invalid Point geometry is retained as ``invalid_point``.
    Unsupported source geometry families fail closed. Boundary/multiple-polygon
    cases are *not* silently tie-broken; a downstream source-specific policy may
    decide what to do with them.

    Candidate generation uses the target GeoSeries' cached spatial index directly,
    avoiding generic GeoDataFrame join materialization. Candidate row order is not
    semantic.
    """
    if points.crs is None:
        raise ValueError("point membership source points require a CRS")
    require_unique_nonmissing_ids(points, point_id_col, label="point")
    require_analytical_polygons(
        polygons,
        polygon_id_col=polygon_id_col,
        operation="point assignment",
    )

    valid, invalid = _point_geometry_masks(points)
    valid_positions = np.flatnonzero(valid)
    if valid_positions.size:
        query_points = points.iloc[valid_positions][[point_id_col, "geometry"]].to_crs(
            polygons.crs
        )
        query_idx, polygon_idx = polygons.geometry.sindex.query(
            query_points.geometry,
            predicate="intersects",
            sort=False,
        )
        source_positions = valid_positions[np.asarray(query_idx, dtype=np.intp)]
        polygon_positions = np.asarray(polygon_idx, dtype=np.intp)
    else:
        source_positions = np.empty(0, dtype=np.intp)
        polygon_positions = np.empty(0, dtype=np.intp)

    candidate_counts = np.bincount(source_positions, minlength=len(points))
    status = np.full(len(points), MembershipStatus.INVALID_POINT.value, dtype=object)
    status[valid & (candidate_counts == 0)] = MembershipStatus.UNMATCHED_OUTSIDE.value
    status[valid & (candidate_counts == 1)] = MembershipStatus.MATCHED_UNIQUE.value
    status[valid & (candidate_counts > 1)] = MembershipStatus.AMBIGUOUS_MULTIPLE.value

    unmatched_positions = np.flatnonzero(valid & (candidate_counts == 0))
    invalid_positions = np.flatnonzero(invalid)
    result_source_positions = np.concatenate(
        [source_positions, unmatched_positions, invalid_positions]
    )

    polygon_values = np.empty(len(result_source_positions), dtype=object)
    matched_count = len(source_positions)
    if matched_count:
        polygon_values[:matched_count] = polygons[polygon_id_col].to_numpy(
            copy=False
        )[polygon_positions]
    polygon_values[matched_count:] = pd.NA

    result = pd.DataFrame(
        {
            point_id_col: points[point_id_col].to_numpy(copy=False)[result_source_positions],
            polygon_id_col: polygon_values,
            "candidate_count": candidate_counts[result_source_positions],
            "assignment_status": status[result_source_positions],
        }
    )

    audit = MembershipAudit(
        input_points=len(points),
        matched_unique=int(np.count_nonzero(status == MembershipStatus.MATCHED_UNIQUE.value)),
        unmatched_outside=int(
            np.count_nonzero(status == MembershipStatus.UNMATCHED_OUTSIDE.value)
        ),
        ambiguous_multiple=int(
            np.count_nonzero(status == MembershipStatus.AMBIGUOUS_MULTIPLE.value)
        ),
        invalid_point=int(np.count_nonzero(status == MembershipStatus.INVALID_POINT.value)),
    )
    return result, audit
