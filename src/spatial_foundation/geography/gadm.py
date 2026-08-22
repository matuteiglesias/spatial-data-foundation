from __future__ import annotations

import geopandas as gpd

from .models import GeometryRole, geography_uid


REQUIRED_BASE = {"GID_0"}


def normalize_gadm_frame(
    frame: gpd.GeoDataFrame,
    *,
    version: str,
    level: int,
    area_crs: str = "EPSG:6933",
) -> gpd.GeoDataFrame:
    """Normalize one native GADM level without simplifying analytical geometry.

    Expected source fields are GID_0 .. GID_{level}. Parent identity is retained when
    available. Geometry is stored in EPSG:4326; area is calculated in the declared
    equal-area CRS and recorded as metadata by the caller/run manifest.
    """
    gid_col = f"GID_{level}"
    parent_col = f"GID_{level - 1}" if level > 0 else None
    required = REQUIRED_BASE | {gid_col}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing required GADM columns: {sorted(missing)}")
    if frame.crs is None:
        raise ValueError("GADM source must have a declared CRS")

    data = frame.to_crs("EPSG:4326").copy()
    metric = data.to_crs(area_crs)
    data["area_km2"] = metric.geometry.area / 1_000_000.0
    data["provider"] = "gadm"
    data["version"] = version
    data["source_geo_id"] = data[gid_col].astype(str)
    data["country_iso3"] = data["GID_0"].astype(str).str.slice(0, 3)
    data["native_admin_level"] = level
    data["geo_uid"] = data["source_geo_id"].map(lambda x: geography_uid("gadm", version, level, x))
    if parent_col and parent_col in data.columns:
        data["parent_geo_uid"] = data[parent_col].astype(str).map(
            lambda x: geography_uid("gadm", version, level - 1, x)
        )
    else:
        data["parent_geo_uid"] = None
    data["geometry_role"] = GeometryRole.ANALYTICAL.value

    keep = [
        "geo_uid",
        "provider",
        "version",
        "source_geo_id",
        "country_iso3",
        "native_admin_level",
        "parent_geo_uid",
        "area_km2",
        "geometry_role",
        "geometry",
    ]
    out = data[keep]
    if out["geo_uid"].duplicated().any():
        dupes = out.loc[out["geo_uid"].duplicated(keep=False), "geo_uid"].unique().tolist()[:10]
        raise ValueError(f"duplicate geography IDs after normalization: {dupes}")
    return out
