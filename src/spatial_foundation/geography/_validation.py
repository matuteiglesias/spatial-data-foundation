from __future__ import annotations

import math

import geopandas as gpd
from pyproj import CRS

_AREAL_GEOMETRY_TYPES = {"Polygon", "MultiPolygon"}


def require_unique_nonmissing_ids(
    frame: gpd.GeoDataFrame,
    column: str,
    *,
    label: str,
) -> None:
    if column not in frame.columns:
        raise ValueError(f"missing {label} id column: {column}")
    values = frame[column]
    if values.isna().any() or values.duplicated().any():
        raise ValueError(f"{label} IDs must be non-missing and unique")


def require_analytical_polygons(
    polygons: gpd.GeoDataFrame,
    *,
    polygon_id_col: str,
    operation: str,
) -> None:
    if polygons.crs is None:
        raise ValueError(f"{operation} analytical geography requires a CRS")
    require_unique_nonmissing_ids(polygons, polygon_id_col, label="polygon")

    if "geometry_role" in polygons.columns:
        roles = polygons["geometry_role"].astype("string")
        if roles.isna().any() or roles.ne("analytical").any():
            raise ValueError(f"{operation} requires analytical geography geometry")

    geometry = polygons.geometry
    if geometry.isna().any() or geometry.is_empty.any() or (~geometry.is_valid).any():
        raise ValueError("analytical geography contains missing, empty, or invalid geometry")
    non_areal = ~geometry.geom_type.isin(_AREAL_GEOMETRY_TYPES)
    if non_areal.any():
        found = sorted(geometry.loc[non_areal].geom_type.unique().tolist())
        raise ValueError(
            f"{operation} analytical geography requires Polygon/MultiPolygon geometry; "
            f"found {found}"
        )


def require_projected_metre_crs(value: object, *, label: str = "area_crs") -> CRS:
    """Return a CRS that is projected and whose horizontal axes use metres.

    This establishes unit correctness for quantities labelled in square metres or
    square kilometres. It deliberately does not claim that every projected metre
    CRS is equal-area or otherwise suitable for every scientific measurement.
    """
    try:
        crs = CRS.from_user_input(value)
    except Exception as exc:  # pyproj accepts several user-input exception types
        raise ValueError(f"{label} is not a resolvable CRS: {value!r}") from exc

    if not crs.is_projected:
        raise ValueError(f"{label} must be a projected CRS with metre horizontal units")

    axes = crs.axis_info[:2]
    if len(axes) < 2:
        raise ValueError(f"{label} must expose two horizontal axes with metre units")
    if any(
        axis.unit_conversion_factor is None
        or not math.isclose(float(axis.unit_conversion_factor), 1.0, rel_tol=0.0, abs_tol=1e-12)
        for axis in axes
    ):
        units = [axis.unit_name for axis in axes]
        raise ValueError(
            f"{label} must use metre horizontal units; resolved horizontal units are {units}"
        )
    return crs
