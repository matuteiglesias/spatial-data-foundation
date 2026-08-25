from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import pandas as pd

from ._validation import require_analytical_polygons, require_unique_nonmissing_ids
from .models import MembershipStatus


@dataclass(frozen=True)
class MembershipAudit:
    input_points: int
    matched_unique: int
    unmatched_outside: int
    ambiguous_multiple: int
    invalid_point: int = 0


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
    """
    if points.crs is None:
        raise ValueError("point membership source points require a CRS")
    require_unique_nonmissing_ids(points, point_id_col, label="point")
    require_analytical_polygons(
        polygons,
        polygon_id_col=polygon_id_col,
        operation="point assignment",
    )

    geometry = points.geometry
    nonempty = geometry.notna() & ~geometry.is_empty
    unsupported = nonempty & geometry.geom_type.ne("Point")
    if unsupported.any():
        found = sorted(geometry.loc[unsupported].geom_type.unique().tolist())
        raise ValueError(f"assign_points accepts Point source geometry only; found {found}")

    valid = nonempty & geometry.is_valid
    valid_points = points.loc[valid, [point_id_col, "geometry"]].copy()
    if valid_points.empty:
        candidates = pd.DataFrame(columns=[point_id_col, polygon_id_col])
        counts = pd.Series(dtype="int64")
    else:
        left = valid_points.to_crs(polygons.crs)
        right = polygons[[polygon_id_col, "geometry"]]

        # intersects intentionally preserves exact-boundary candidates instead of
        # dropping them as `within` could do.
        joined = gpd.sjoin(left, right, how="left", predicate="intersects")
        candidates = joined[[point_id_col, polygon_id_col]].copy()
        counts = candidates.groupby(point_id_col)[polygon_id_col].count()

    invalid_rows = pd.DataFrame(
        {
            point_id_col: points.loc[~valid, point_id_col].to_numpy(),
            polygon_id_col: pd.NA,
        }
    )
    if not invalid_rows.empty:
        candidates = pd.concat([candidates, invalid_rows], ignore_index=True)

    status_rows = []
    for point_id, is_valid in zip(points[point_id_col], valid):
        if not bool(is_valid):
            n = 0
            status = MembershipStatus.INVALID_POINT.value
        else:
            n = int(counts.get(point_id, 0))
            if n == 0:
                status = MembershipStatus.UNMATCHED_OUTSIDE.value
            elif n == 1:
                status = MembershipStatus.MATCHED_UNIQUE.value
            else:
                status = MembershipStatus.AMBIGUOUS_MULTIPLE.value
        status_rows.append(
            {
                point_id_col: point_id,
                "candidate_count": n,
                "assignment_status": status,
            }
        )
    status_df = pd.DataFrame(status_rows)
    result = candidates.merge(status_df, on=point_id_col, how="left")

    audit = MembershipAudit(
        input_points=len(points),
        matched_unique=int(
            status_df.assignment_status.eq(MembershipStatus.MATCHED_UNIQUE.value).sum()
        ),
        unmatched_outside=int(
            status_df.assignment_status.eq(MembershipStatus.UNMATCHED_OUTSIDE.value).sum()
        ),
        ambiguous_multiple=int(
            status_df.assignment_status.eq(MembershipStatus.AMBIGUOUS_MULTIPLE.value).sum()
        ),
        invalid_point=int(
            status_df.assignment_status.eq(MembershipStatus.INVALID_POINT.value).sum()
        ),
    )
    return result, audit
