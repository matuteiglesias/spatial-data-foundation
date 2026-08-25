from __future__ import annotations

from pathlib import Path
from typing import Any

_PRESENTATION_INSTALL_HINT = (
    "spatial_foundation.presentation requires the optional presentation dependencies; "
    "install with `pip install 'spatial-data-foundation[presentation]'`"
)

try:
    import contextily as cx
    from xyzservices import TileProvider, providers
except ModuleNotFoundError as exc:  # pragma: no cover - exercised in an isolated subprocess
    raise ModuleNotFoundError(_PRESENTATION_INSTALL_HINT) from exc


BASEMAP_ALIASES: dict[str, TileProvider] = {
    "neutral": providers.CartoDB.Positron,
    "imagery": providers.Esri.WorldImagery,
    "terrain": providers.OpenTopoMap,
}

BasemapSource = str | Path | TileProvider


def resolve_basemap(source: BasemapSource = "neutral") -> str | TileProvider:
    """Resolve a small governed alias vocabulary or pass through a concrete source.

    String sources outside the alias vocabulary are intentionally passed through to
    contextily, which can interpret a tile URL/provider name or a local raster path.
    `Path` values are normalized to strings for the same reason.
    """
    if isinstance(source, Path):
        return str(source)
    if isinstance(source, str) and source in BASEMAP_ALIASES:
        return BASEMAP_ALIASES[source]
    return source


def add_basemap(
    ax: Any,
    *,
    crs: Any,
    kind: str = "neutral",
    source: BasemapSource | None = None,
    alpha: float = 1.0,
    attribution: str | None = None,
    zoom: int | str = "auto",
    interpolation: str = "bilinear",
) -> Any:
    """Add contextual cartography beneath an existing analytical plot.

    This is presentation-only. It never changes source geometry or spatial
    membership. The caller must provide the CRS of the plotted analytical data.
    Provider attribution is preserved by default and cannot be disabled here.
    """
    if crs is None:
        raise ValueError("a CRS is required to align a contextual basemap")
    if attribution is False:
        raise ValueError("basemap attribution cannot be disabled")
    if not 0 <= alpha <= 1:
        raise ValueError("alpha must be between 0 and 1")

    selected: BasemapSource = source if source is not None else kind
    resolved_source = resolve_basemap(selected)
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()

    cx.add_basemap(
        ax,
        crs=crs,
        source=resolved_source,
        alpha=alpha,
        attribution=attribution,
        reset_extent=True,
        zoom=zoom,
        interpolation=interpolation,
    )

    # contextily already promises reset_extent=True, but preserve the public
    # presentation contract even if a provider/local raster behaves unusually.
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    return ax
