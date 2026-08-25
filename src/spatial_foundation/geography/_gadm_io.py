from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pyogrio


@dataclass(frozen=True)
class GADMSourceSelection:
    path: Path
    layer: str | None
    columns: tuple[str, ...]
    geometry_column: str | None = None


def _native_level_from_fields(fields: Iterable[str]) -> int | None:
    levels = []
    for field in fields:
        if not field.startswith("GID_"):
            continue
        suffix = field[4:]
        if suffix.isdigit():
            levels.append(int(suffix))
    return max(levels) if levels else None


def _required_identity_columns(fields: Iterable[str], level: int) -> tuple[str, ...]:
    available = set(fields)
    required = ["GID_0", f"GID_{level}"]
    missing = sorted(set(required) - available)
    if missing:
        raise ValueError(
            f"GADM ADM{level} source is missing required identity fields: {missing}"
        )

    columns = ["GID_0"]
    if level > 0:
        parent = f"GID_{level - 1}"
        if parent in available and parent not in columns:
            columns.append(parent)
    current = f"GID_{level}"
    if current not in columns:
        columns.append(current)
    return tuple(columns)


def _inspect_vector_source(path: Path, level: int) -> GADMSourceSelection | None:
    try:
        layers = pyogrio.list_layers(path)
    except Exception as exc:
        raise ValueError(f"cannot inspect registered GADM source file {path}: {exc}") from exc

    matches: list[GADMSourceSelection] = []
    for row in layers:
        layer = str(row[0])
        try:
            info = pyogrio.read_info(path, layer=layer)
        except Exception as exc:
            raise ValueError(
                f"cannot inspect registered GADM layer {layer!r} in {path}: {exc}"
            ) from exc
        fields = tuple(str(field) for field in info.get("fields", ()))
        if _native_level_from_fields(fields) != level:
            continue
        columns = _required_identity_columns(fields, level)
        matches.append(GADMSourceSelection(path=path, layer=layer, columns=columns))

    if len(matches) > 1:
        layer_names = [selection.layer for selection in matches]
        raise ValueError(
            f"registered GADM source {path} contains multiple ADM{level} layers: {layer_names}"
        )
    return matches[0] if matches else None


def _inspect_geoparquet_source(path: Path, level: int) -> GADMSourceSelection | None:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - materialization checks this first
        raise RuntimeError(
            "GeoParquet GADM source inspection requires pyarrow; "
            "install spatial-data-foundation[io]"
        ) from exc

    try:
        schema = pq.read_schema(path)
    except Exception as exc:
        raise ValueError(f"cannot inspect registered GADM GeoParquet {path}: {exc}") from exc

    fields = tuple(schema.names)
    if _native_level_from_fields(fields) != level:
        return None
    columns = _required_identity_columns(fields, level)

    metadata = schema.metadata or {}
    geo_metadata = metadata.get(b"geo")
    if not geo_metadata:
        raise ValueError(f"registered GADM parquet source is missing GeoParquet metadata: {path}")
    try:
        primary_geometry = json.loads(geo_metadata.decode("utf-8"))["primary_column"]
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot resolve GeoParquet primary geometry column for {path}") from exc
    if primary_geometry not in fields:
        raise ValueError(
            f"GeoParquet primary geometry column {primary_geometry!r} is missing from {path}"
        )
    return GADMSourceSelection(
        path=path,
        layer=None,
        columns=columns,
        geometry_column=primary_geometry,
    )


def inspect_gadm_source(path: Path, level: int) -> GADMSourceSelection | None:
    """Select one requested native GADM level without materializing source geometry."""
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".geoparquet"}:
        return _inspect_geoparquet_source(path, level)
    return _inspect_vector_source(path, level)


def read_gadm_selection(
    selection: GADMSourceSelection,
    *,
    use_arrow: bool,
) -> gpd.GeoDataFrame:
    """Read only the selected GADM identity columns plus the authoritative geometry."""
    if selection.geometry_column is not None:
        columns = [*selection.columns, selection.geometry_column]
        try:
            return gpd.read_parquet(selection.path, columns=columns)
        except Exception as exc:
            raise ValueError(
                f"cannot read registered GADM GeoParquet {selection.path}: {exc}"
            ) from exc

    try:
        return pyogrio.read_dataframe(
            selection.path,
            layer=selection.layer,
            columns=list(selection.columns),
            use_arrow=use_arrow,
        )
    except Exception as exc:
        layer_text = "" if selection.layer is None else f" layer {selection.layer!r}"
        raise ValueError(
            f"cannot read registered GADM source file {selection.path}{layer_text}: {exc}"
        ) from exc


def read_gadm_level_parts(
    paths: Iterable[Path],
    level: int,
    *,
    use_arrow: bool,
) -> list[gpd.GeoDataFrame]:
    """Inspect registered sources first, then load only parts matching ``level``."""
    parts = []
    for path in paths:
        selection = inspect_gadm_source(path, level)
        if selection is None:
            continue
        parts.append(read_gadm_selection(selection, use_arrow=use_arrow))
    return parts
