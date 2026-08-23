from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

import geopandas as gpd
import pandas as pd
from empirical_contracts import (
    AuthorityLevel,
    DataLayer,
    DatasetRef,
    GeographySpec,
    GrainSpec,
    QAResult,
    RunManifest,
    SourceSnapshotRef,
)

from ..catalog import DataRoot, sha256_file
from .gadm import normalize_gadm_frame

PACKAGE_NAME = "spatial-data-foundation"


@dataclass(frozen=True)
class GADMMaterialization:
    run_id: str
    dataset_root: Path
    run_root: Path
    outputs: dict[int, Path]
    manifest_path: Path
    qa_path: Path


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _package_version() -> str:
    try:
        return package_version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.1.0"


def _resolve_code_commit(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    env_value = os.environ.get("SPATIAL_DATA_FOUNDATION_CODE_COMMIT")
    if env_value and env_value.strip():
        return env_value.strip()

    repo_root = Path(__file__).resolve().parents[3]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        result = None
    if result and result.stdout.strip():
        return result.stdout.strip()
    raise ValueError(
        "code_commit is required when Git metadata is unavailable; pass it explicitly "
        "or set SPATIAL_DATA_FOUNDATION_CODE_COMMIT"
    )


def _validate_levels(levels: Iterable[int]) -> tuple[int, ...]:
    normalized = tuple(sorted(set(levels)))
    if not normalized:
        raise ValueError("at least one GADM level is required")
    if any(not isinstance(level, int) or isinstance(level, bool) or level < 0 for level in normalized):
        raise ValueError("GADM levels must be non-negative integers")
    return normalized


def _validate_run_id(run_id: str) -> str:
    if not run_id or run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
        raise ValueError("run_id must be a non-empty path-safe identifier")
    return run_id


def _default_run_id(
    *,
    snapshot: SourceSnapshotRef,
    levels: tuple[int, ...],
    area_crs: str,
    code_commit: str,
    started_at: datetime,
) -> str:
    payload = "|".join(
        [snapshot.snapshot_id, ",".join(map(str, levels)), area_crs, code_commit]
    ).encode()
    short = sha256(payload).hexdigest()[:8]
    stamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
    release = snapshot.release.replace(".", "-").replace("/", "-")
    return f"gadm-{release}-{stamp}-{short}"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _verify_snapshot(snapshot: SourceSnapshotRef) -> None:
    if snapshot.source.lower() != "gadm":
        raise ValueError(f"materialize_gadm requires a GADM snapshot, got {snapshot.source!r}")
    for ref in snapshot.files:
        path = Path(ref.path)
        if not path.exists():
            raise ValueError(f"source snapshot file is missing: {path}")
        actual_hash = sha256_file(path)
        if actual_hash != ref.sha256:
            raise ValueError(
                f"source snapshot hash mismatch for {path}: expected {ref.sha256}, got {actual_hash}"
            )
        actual_size = path.stat().st_size
        if actual_size != ref.size_bytes:
            raise ValueError(
                f"source snapshot size mismatch for {path}: expected {ref.size_bytes}, got {actual_size}"
            )


def _native_level(frame: gpd.GeoDataFrame) -> int | None:
    levels = []
    for column in frame.columns:
        if not column.startswith("GID_"):
            continue
        suffix = column[4:]
        if suffix.isdigit():
            levels.append(int(suffix))
    return max(levels) if levels else None


def _read_single_level(path: Path, level: int) -> gpd.GeoDataFrame | None:
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".geoparquet"}:
        frame = gpd.read_parquet(path)
        return frame if _native_level(frame) == level else None

    if suffix == ".gpkg":
        layer = f"ADM_ADM_{level}"
        try:
            frame = gpd.read_file(path, layer=layer)
        except (ValueError, RuntimeError, OSError):
            try:
                frame = gpd.read_file(path)
            except (ValueError, RuntimeError, OSError):
                return None
        return frame if _native_level(frame) == level else None

    try:
        frame = gpd.read_file(path)
    except (ValueError, RuntimeError, OSError) as exc:
        raise ValueError(f"cannot read registered GADM source file {path}: {exc}") from exc
    return frame if _native_level(frame) == level else None


def _read_level(
    snapshot: SourceSnapshotRef,
    level: int,
    *,
    area_crs: str,
) -> gpd.GeoDataFrame:
    normalized_parts = []
    for ref in snapshot.files:
        source = _read_single_level(Path(ref.path), level)
        if source is None:
            continue
        normalized_parts.append(
            normalize_gadm_frame(
                source,
                version=snapshot.release,
                level=level,
                area_crs=area_crs,
            )
        )

    if not normalized_parts:
        raise ValueError(
            f"registered GADM snapshot {snapshot.snapshot_id!r} contains no readable ADM{level} layer"
        )

    combined = gpd.GeoDataFrame(
        pd.concat(normalized_parts, ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )
    if combined["geo_uid"].duplicated().any():
        duplicates = int(combined["geo_uid"].duplicated(keep=False).sum())
        raise ValueError(f"duplicate geography IDs across registered GADM files: {duplicates} row(s)")
    return combined


def _level_metrics(frame: gpd.GeoDataFrame) -> dict[str, int]:
    null_geometry = frame.geometry.isna()
    invalid_geometry = ~null_geometry & ~frame.geometry.is_valid
    return {
        "row_count": len(frame),
        "country_count": int(frame["country_iso3"].nunique(dropna=True)),
        "null_geometry_count": int(null_geometry.sum()),
        "invalid_geometry_count": int(invalid_geometry.sum()),
        "duplicate_id_count": int(frame["geo_uid"].duplicated(keep=False).sum()),
    }


def _dataset_ref(level: int, release: str, content_hash: str) -> DatasetRef:
    return DatasetRef(
        dataset_id=f"gadm_native_adm{level}",
        version=release,
        schema_version="1",
        layer=DataLayer.SILVER,
        authority=AuthorityLevel.L1_NORMALIZED,
        grain=GrainSpec(keys=("geo_uid",)),
        geography=GeographySpec(
            provider="gadm",
            version=release,
            scheme="native",
            level=f"adm{level}",
        ),
        content_sha256=content_hash,
    )


def materialize_gadm(
    *,
    snapshot: SourceSnapshotRef,
    levels: Iterable[int],
    output_root: str | Path,
    area_crs: str = "EPSG:6933",
    code_commit: str | None = None,
    run_id: str | None = None,
    overwrite: bool = False,
) -> GADMMaterialization:
    """Materialize registered GADM sources as auditable silver GeoParquet assets.

    Source bytes are never downloaded or copied by this function. Registered hashes are
    revalidated before reading. All requested levels are normalized and staged before
    final silver paths are published. Run provenance and geography QA are persisted as
    JSON companions under ``runs/spatial-data-foundation/<run_id>/``.

    The registered snapshot may contain separate level files or standard GADM 4.x
    GeoPackages with ``ADM_ADM_<level>`` layers. GeoParquet materialization requires
    the package ``io`` extra (pyarrow).
    """
    try:
        import pyarrow  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "materialize_gadm requires pyarrow; install spatial-data-foundation[io]"
        ) from exc

    requested_levels = _validate_levels(levels)
    if not area_crs or not area_crs.strip():
        raise ValueError("area_crs must be non-empty")
    commit = _resolve_code_commit(code_commit)
    started_at = _utc_now()
    resolved_run_id = _validate_run_id(
        run_id
        or _default_run_id(
            snapshot=snapshot,
            levels=requested_levels,
            area_crs=area_crs,
            code_commit=commit,
            started_at=started_at,
        )
    )

    data_root = DataRoot.from_path(output_root)
    dataset_root = data_root.silver("geography", "gadm", snapshot.release)
    run_root = data_root.run(PACKAGE_NAME, resolved_run_id)
    manifest_path = run_root / "run_manifest.json"
    qa_path = run_root / "geography_qa.json"
    run_root.mkdir(parents=True, exist_ok=True)

    outputs = {level: dataset_root / f"adm{level}.geoparquet" for level in requested_levels}
    temp_paths = {level: dataset_root / f".adm{level}.geoparquet.tmp" for level in requested_levels}

    try:
        _verify_snapshot(snapshot)
        normalized = {
            level: _read_level(snapshot, level, area_crs=area_crs)
            for level in requested_levels
        }

        for path in outputs.values():
            if path.exists() and not overwrite:
                raise FileExistsError(
                    f"refusing to overwrite existing GADM asset {path}; pass overwrite=True explicitly"
                )

        dataset_root.mkdir(parents=True, exist_ok=True)
        output_hashes: dict[int, str] = {}
        level_qa: dict[str, dict[str, int | str]] = {}
        for level, frame in normalized.items():
            temp = temp_paths[level]
            if temp.exists():
                temp.unlink()
            frame.to_parquet(temp, index=False)
            output_hash = sha256_file(temp)
            output_hashes[level] = output_hash
            level_qa[str(level)] = {
                **_level_metrics(frame),
                "output_path": str(outputs[level]),
                "output_sha256": output_hash,
            }

        dataset_refs = tuple(
            _dataset_ref(level, snapshot.release, output_hashes[level])
            for level in requested_levels
        )
        qa_results = [
            QAResult(
                check_id="gadm_source_snapshot_integrity",
                state="GREEN",
                message="registered GADM source files match their snapshot hashes",
                metrics={"file_count": len(snapshot.files)},
            )
        ]
        for level in requested_levels:
            metrics = level_qa[str(level)]
            has_geometry_issue = bool(
                metrics["null_geometry_count"] or metrics["invalid_geometry_count"]
            )
            qa_results.append(
                QAResult(
                    check_id=f"gadm_adm{level}_geometry_profile",
                    state="YELLOW" if has_geometry_issue else "GREEN",
                    message=(
                        "geometry profile contains null or invalid geometries"
                        if has_geometry_issue
                        else "geometry profile is clean"
                    ),
                    metrics={
                        "row_count": metrics["row_count"],
                        "country_count": metrics["country_count"],
                        "null_geometry_count": metrics["null_geometry_count"],
                        "invalid_geometry_count": metrics["invalid_geometry_count"],
                        "duplicate_id_count": metrics["duplicate_id_count"],
                    },
                )
            )

        finished_at = _utc_now()
        manifest = RunManifest(
            run_id=resolved_run_id,
            package=PACKAGE_NAME,
            package_version=_package_version(),
            code_commit=commit,
            started_at=started_at,
            finished_at=finished_at,
            inputs=(snapshot,),
            parameters={
                "provider": "gadm",
                "version": snapshot.release,
                "area_crs": area_crs,
                "requested_levels": list(requested_levels),
                "available_levels": list(requested_levels),
                "output_files": {
                    str(level): {
                        "path": str(outputs[level]),
                        "sha256": output_hashes[level],
                    }
                    for level in requested_levels
                },
            },
            outputs=dataset_refs,
            qa=tuple(qa_results),
        )
        qa_payload = {
            "state": "YELLOW"
            if any(result.state == "YELLOW" for result in qa_results)
            else "GREEN",
            "provider": "gadm",
            "version": snapshot.release,
            "area_crs": area_crs,
            "available_levels": list(requested_levels),
            "source_snapshot": snapshot.model_dump(mode="json"),
            "levels": level_qa,
        }

        for level in requested_levels:
            temp_paths[level].replace(outputs[level])
        _write_json(manifest_path, manifest.model_dump(mode="json"))
        _write_json(qa_path, qa_payload)

        return GADMMaterialization(
            run_id=resolved_run_id,
            dataset_root=dataset_root,
            run_root=run_root,
            outputs=outputs,
            manifest_path=manifest_path,
            qa_path=qa_path,
        )
    except Exception as exc:
        for temp in temp_paths.values():
            if temp.exists():
                temp.unlink()
        failure = QAResult(
            check_id="gadm_materialization",
            state="RED",
            message=str(exc),
            metrics={"requested_level_count": len(requested_levels)},
        )
        failure_manifest = RunManifest(
            run_id=resolved_run_id,
            package=PACKAGE_NAME,
            package_version=_package_version(),
            code_commit=commit,
            started_at=started_at,
            finished_at=_utc_now(),
            inputs=(snapshot,),
            parameters={
                "provider": "gadm",
                "version": snapshot.release,
                "area_crs": area_crs,
                "requested_levels": list(requested_levels),
                "available_levels": [],
            },
            outputs=(),
            qa=(failure,),
        )
        _write_json(manifest_path, failure_manifest.model_dump(mode="json"))
        _write_json(
            qa_path,
            {
                "state": "RED",
                "provider": "gadm",
                "version": snapshot.release,
                "area_crs": area_crs,
                "available_levels": [],
                "source_snapshot": snapshot.model_dump(mode="json"),
                "error": str(exc),
                "levels": {},
            },
        )
        raise
