from __future__ import annotations

from typing import Any

import geopandas as gpd

from .basemaps import BasemapSource, add_basemap


def plot_context(
    gdf: gpd.GeoDataFrame,
    *,
    basemap: BasemapSource = "neutral",
    basemap_alpha: float = 1.0,
    basemap_attribution: str | None = None,
    basemap_zoom: int | str = "auto",
    **plot_kwargs: Any,
) -> Any:
    """Plot a GeoDataFrame and add an optional contextual basemap beneath it."""
    if gdf.crs is None:
        raise ValueError("GeoDataFrame requires a CRS for contextual plotting")

    ax = gdf.plot(**plot_kwargs)
    add_basemap(
        ax,
        crs=gdf.crs,
        source=basemap,
        alpha=basemap_alpha,
        attribution=basemap_attribution,
        zoom=basemap_zoom,
    )
    return ax
