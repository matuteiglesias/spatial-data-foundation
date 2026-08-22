from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import pandas as pd

from .models import MembershipStatus


@dataclass(frozen=True)
class MembershipAudit:
    input_points: int
    matched_unique: int
    unmatched_outside: int
    ambiguous_multiple: int


def assign_points(
    points: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    *,
    point_id_col: str,
    polygon_id_col: str = "geo_uid",
) -> tuple[pd.DataFrame, MembershipAudit]:
    """Return candidate memberships and explicit point-level assignment status.

    Boundary/multiple-polygon cases are *not* silently tie-broken. A downstream
    source-specific policy may decide what to do with them.
    """
    if points.crs is None or polygons.crs is None:
        raise ValueError("both points and polygons require a CRS")
    if point_id_col not in points.columns:
        raise ValueError(f"missing point id column: {point_id_col}")
    if polygon_id_col not in polygons.columns:
        raise ValueError(f"missing polygon id column: {polygon_id_col}")
    if points[point_id_col].duplicated().any():
        raise ValueError("point IDs must be unique")
    if polygons[polygon_id_col].duplicated().any():
        raise ValueError("polygon IDs must be unique")
    if "geometry_role" in polygons.columns:
        roles = polygons["geometry_role"].astype("string")
        if roles.isna().any() or roles.ne("analytical").any():
            raise ValueError("point assignment requires analytical geometry")

    left = points[[point_id_col, "geometry"]].to_crs(polygons.crs)
    right = polygons[[polygon_id_col, "geometry"]]

    # intersects intentionally preserves exact-boundary candidates instead of
    # dropping them as `within` could do.
    joined = gpd.sjoin(left, right, how="left", predicate="intersects")
    candidates = joined[[point_id_col, polygon_id_col]].copy()

    counts = candidates.groupby(point_id_col)[polygon_id_col].count()
    status_rows = []
    for point_id in left[point_id_col]:
        n = int(counts.get(point_id, 0))
        if n == 0:
            status = MembershipStatus.UNMATCHED_OUTSIDE.value
        elif n == 1:
            status = MembershipStatus.MATCHED_UNIQUE.value
        else:
            status = MembershipStatus.AMBIGUOUS_MULTIPLE.value
        status_rows.append({point_id_col: point_id, "candidate_count": n, "assignment_status": status})
    status_df = pd.DataFrame(status_rows)
    result = candidates.merge(status_df, on=point_id_col, how="left")

    audit = MembershipAudit(
        input_points=len(left),
        matched_unique=int((status_df.assignment_status == MembershipStatus.MATCHED_UNIQUE.value).sum()),
        unmatched_outside=int((status_df.assignment_status == MembershipStatus.UNMATCHED_OUTSIDE.value).sum()),
        ambiguous_multiple=int((status_df.assignment_status == MembershipStatus.AMBIGUOUS_MULTIPLE.value).sum()),
    )
    return result, audit
