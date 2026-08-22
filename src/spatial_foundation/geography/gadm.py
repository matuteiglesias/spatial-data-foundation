from __future__ import annotations

import geopandas as gpd

from .models import geography_uid, GeometryRole


REQUIRED_BASE = {"GID_0"}


def _require_identity(series, *, label: str):
    missing = series.isna() | series.astype("string").str.strip().eq("")
    if missing.any():
        raise ValueError(f"GADM {label} is not resolvable for {int(missing.sum())} row(s)")
    return series.astype(str)


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
    equal-area CRS. The returned frame records the area CRS and geometry validity
    profile in ``GeoDataFrame.attrs`` for run-manifest/provenance capture.
    """
    if level < 0:
        raise ValueError("GADM admin level must be >= 0")
    if not version.strip():
        raise ValueError("GADM version must be non-empty")

    gid_col = f"GID_{level}"
    parent_col = f"GID_{level - 1}" if level > 0 else None
    required = REQUIRED_BASE | {gid_col}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing required GADM columns: {sorted(missing)}")
    if frame.crs is None:
        raise ValueError("GADM source must have a declared CRS")

    source_ids = _require_identity(frame[gid_col], label="source geography identity")
    country_ids = _require_identity(frame["GID_0"], label="country identity")

    data = frame.to_crs("EPSG:4326").copy()
    metric = data.to_crs(area_crs)
    data["area_km2"] = metric.geometry.area / 1_000_000.0
    data["provider"] = "gadm"
    data["version"] = version
    data["source_geo_id"] = source_ids.to_numpy()
    data["country_iso3"] = country_ids.str.slice(0, 3).to_numpy()
    data["native_admin_level"] = level
    data["geo_uid"] = data["source_geo_id"].map(lambda x: geography_uid("gadm", version, level, x))
    if parent_col and parent_col in data.columns:
        parent_present = data[parent_col].notna() & data[parent_col].astype("string").str.strip().ne("")
        data["parent_geo_uid"] = [
            geography_uid("gadm", version, level - 1, str(value)) if present else None
            for value, present in zip(data[parent_col], parent_present)
        ]
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
    out = data[keep].copy()
    if out["geo_uid"].duplicated().any():
        dupes = out.loc[out["geo_uid"].duplicated(keep=False), "geo_uid"].unique().tolist()[:10]
        raise ValueError(f"duplicate geography IDs after normalization: {dupes}")

    null_geometry = out.geometry.isna()
    invalid_geometry = ~null_geometry & ~out.geometry.is_valid
    out.attrs["area_crs"] = area_crs
    out.attrs["geometry_profile"] = {
        "rows": len(out),
        "null": int(null_geometry.sum()),
        "invalid": int(invalid_geometry.sum()),
    }
    return out
