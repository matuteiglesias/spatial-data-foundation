from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import pandas as pd


@dataclass(frozen=True)
class ArealOverlapAudit:
    input_objects: int
    matched_single: int
    matched_multiple: int
    unmatched_outside: int
    invalid_geometry: int
    relation_rows: int


_AREAL_GEOMETRY_TYPES = {"Polygon", "MultiPolygon"}


def _require_analytical_geography(polygons: gpd.GeoDataFrame) -> None:
    if "geometry_role" not in polygons.columns:
        return
    roles = polygons["geometry_role"].astype("string")
    if roles.isna().any() or roles.ne("analytical").any():
        raise ValueError("areal overlap requires analytical geography geometry")


def _positive_overlap_pairs(
    objects: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    *,
    object_id_col: str,
    polygon_id_col: str,
    area_crs: str,
    min_overlap_area_m2: float,
) -> pd.DataFrame:
    left = objects[[object_id_col, "geometry"]].to_crs(polygons.crs)
    right = polygons[[polygon_id_col, "geometry"]]
    candidates = gpd.sjoin(left, right, how="inner", predicate="intersects")
    pairs = candidates[[object_id_col, polygon_id_col]].drop_duplicates().copy()
    if pairs.empty:
        return pd.DataFrame(
            columns=[object_id_col, polygon_id_col, "overlap_area_m2", "overlap_share_of_object"]
        )

    object_area = objects[[object_id_col, "geometry"]].to_crs(area_crs)
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
    pairs["overlap_share_of_object"] = pairs["overlap_area_m2"] / pairs["_object_area_m2"]
    return pairs.drop(columns=["_object_area_m2"]).reset_index(drop=True)


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

    Boundary-only touches have zero intersection area and are excluded by default.
    """
    if min_overlap_area_m2 < 0:
        raise ValueError("min_overlap_area_m2 must be non-negative")
    if objects.crs is None or polygons.crs is None:
        raise ValueError("both objects and polygons require a CRS")
    if object_id_col not in objects.columns:
        raise ValueError(f"missing object id column: {object_id_col}")
    if polygon_id_col not in polygons.columns:
        raise ValueError(f"missing polygon id column: {polygon_id_col}")
    if objects[object_id_col].isna().any() or objects[object_id_col].duplicated().any():
        raise ValueError("object IDs must be non-missing and unique")
    if polygons[polygon_id_col].isna().any() or polygons[polygon_id_col].duplicated().any():
        raise ValueError("polygon IDs must be non-missing and unique")
    _require_analytical_geography(polygons)

    polygon_geometry = polygons.geometry
    if polygon_geometry.isna().any() or polygon_geometry.is_empty.any() or (~polygon_geometry.is_valid).any():
        raise ValueError("analytical geography contains missing, empty, or invalid geometry")

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
    pairs = _positive_overlap_pairs(
        valid_objects,
        polygons,
        object_id_col=object_id_col,
        polygon_id_col=polygon_id_col,
        area_crs=area_crs,
        min_overlap_area_m2=min_overlap_area_m2,
    )

    overlap_counts = pairs.groupby(object_id_col)[polygon_id_col].count() if len(pairs) else pd.Series(dtype="int64")
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
