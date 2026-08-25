from __future__ import annotations

import geopandas as gpd
import pandas as pd

from spatial_foundation.geography._validation import (
    require_analytical_polygons,
    require_projected_metre_crs,
    require_unique_nonmissing_ids,
)
from spatial_foundation.geography.membership import MembershipAudit
from spatial_foundation.geography.models import MembershipStatus
from spatial_foundation.geography.overlap import ArealOverlapAudit

_AREAL_GEOMETRY_TYPES = {"Polygon", "MultiPolygon"}


def baseline_assign_points(
    points: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    *,
    point_id_col: str,
    polygon_id_col: str = "geo_uid",
) -> tuple[pd.DataFrame, MembershipAudit]:
    """Frozen B1 point kernel used only for benchmark/parity comparisons."""
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


def baseline_relate_areal_objects(
    objects: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    *,
    object_id_col: str,
    polygon_id_col: str = "geo_uid",
    area_crs: str = "EPSG:6933",
    min_overlap_area_m2: float = 0.0,
) -> tuple[pd.DataFrame, ArealOverlapAudit]:
    """Frozen B1 areal kernel used only for benchmark/parity comparisons."""
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

    object_geometry = objects.geometry
    nonempty = object_geometry.notna() & ~object_geometry.is_empty
    non_areal = nonempty & ~object_geometry.geom_type.isin(_AREAL_GEOMETRY_TYPES)
    if non_areal.any():
        found = sorted(object_geometry.loc[non_areal].geom_type.unique().tolist())
        raise ValueError(
            "relate_areal_objects accepts Polygon/MultiPolygon source geometry only; "
            f"found {found}. Use point membership for point sources."
        )

    valid = nonempty & object_geometry.is_valid
    valid_objects = objects.loc[valid, [object_id_col, "geometry"]].copy()
    left = valid_objects[[object_id_col, "geometry"]].to_crs(polygons.crs)
    right = polygons[[polygon_id_col, "geometry"]]
    candidates = gpd.sjoin(left, right, how="inner", predicate="intersects")
    pairs = candidates[[object_id_col, polygon_id_col]].drop_duplicates().copy()

    if not pairs.empty:
        object_area = valid_objects[[object_id_col, "geometry"]].to_crs(area_crs)
        polygon_area = polygons[[polygon_id_col, "geometry"]].to_crs(area_crs)
        object_geometries = object_area.set_index(object_id_col)["geometry"]
        polygon_geometries = polygon_area.set_index(polygon_id_col)["geometry"]

        overlap_areas: list[float] = []
        object_areas: list[float] = []
        for object_id, polygon_id in pairs[[object_id_col, polygon_id_col]].itertuples(
            index=False, name=None
        ):
            object_geometry = object_geometries.loc[object_id]
            polygon_geometry = polygon_geometries.loc[polygon_id]
            overlap_areas.append(float(object_geometry.intersection(polygon_geometry).area))
            object_areas.append(float(object_geometry.area))

        pairs["overlap_area_m2"] = overlap_areas
        pairs["_object_area_m2"] = object_areas
        pairs = pairs.loc[pairs["overlap_area_m2"] > min_overlap_area_m2].copy()
        pairs["overlap_share_of_object"] = (
            pairs["overlap_area_m2"] / pairs["_object_area_m2"]
        )
        pairs = pairs.drop(columns=["_object_area_m2"]).reset_index(drop=True)
    else:
        pairs = pd.DataFrame(
            columns=[
                object_id_col,
                polygon_id_col,
                "overlap_area_m2",
                "overlap_share_of_object",
            ]
        )

    overlap_counts = (
        pairs.groupby(object_id_col)[polygon_id_col].count()
        if len(pairs)
        else pd.Series(dtype="int64")
    )
    rows: list[dict] = []
    for object_id in objects[object_id_col]:
        if not bool(valid.loc[objects[object_id_col].eq(object_id)].iloc[0]):
            rows.append(
                {
                    object_id_col: object_id,
                    polygon_id_col: pd.NA,
                    "overlap_area_m2": pd.NA,
                    "overlap_share_of_object": pd.NA,
                    "overlap_count": 0,
                    "relation_status": "invalid_geometry",
                }
            )
            continue

        count = int(overlap_counts.get(object_id, 0))
        if count == 0:
            rows.append(
                {
                    object_id_col: object_id,
                    polygon_id_col: pd.NA,
                    "overlap_area_m2": pd.NA,
                    "overlap_share_of_object": pd.NA,
                    "overlap_count": 0,
                    "relation_status": "unmatched_outside",
                }
            )
            continue

        status = "matched_single" if count == 1 else "matched_multiple"
        object_pairs = pairs.loc[pairs[object_id_col].eq(object_id)]
        for pair in object_pairs.to_dict(orient="records"):
            rows.append(
                {
                    **pair,
                    "overlap_count": count,
                    "relation_status": status,
                }
            )

    result = pd.DataFrame(rows)
    status_by_object = result[[object_id_col, "relation_status"]].drop_duplicates(object_id_col)
    audit = ArealOverlapAudit(
        input_objects=len(objects),
        matched_single=int(status_by_object["relation_status"].eq("matched_single").sum()),
        matched_multiple=int(status_by_object["relation_status"].eq("matched_multiple").sum()),
        unmatched_outside=int(status_by_object["relation_status"].eq("unmatched_outside").sum()),
        invalid_geometry=int(status_by_object["relation_status"].eq("invalid_geometry").sum()),
        relation_rows=int(result[polygon_id_col].notna().sum()),
    )
    return result, audit
