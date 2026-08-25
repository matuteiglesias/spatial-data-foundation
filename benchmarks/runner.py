from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import metadata
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from spatial_foundation.geography import assign_points, relate_areal_objects

from .baselines import baseline_assign_points, baseline_relate_areal_objects
from .workloads import (
    AREAL_CASES,
    POINT_CASES,
    make_areal_workload,
    make_point_workload,
)


@dataclass(frozen=True)
class KernelAdapter:
    """Callable boundary that later optimization branches can benchmark unchanged."""

    name: str
    assign_points: Callable[..., tuple[pd.DataFrame, Any]]
    relate_areal_objects: Callable[..., tuple[pd.DataFrame, Any]]


BASELINE_ADAPTER = KernelAdapter(
    name="b1_baseline",
    assign_points=baseline_assign_points,
    relate_areal_objects=baseline_relate_areal_objects,
)
CURRENT_ADAPTER = KernelAdapter(
    name="current",
    assign_points=assign_points,
    relate_areal_objects=relate_areal_objects,
)


def _seconds(callable_: Callable[[], Any]) -> tuple[Any, float]:
    started = perf_counter()
    result = callable_()
    return result, perf_counter() - started


def runtime_versions() -> dict[str, str]:
    names = (
        "spatial-data-foundation",
        "empirical-data-contracts",
        "geopandas",
        "shapely",
        "pyproj",
        "pyogrio",
        "pandas",
        "numpy",
    )
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not-installed"

    try:
        import shapely

        versions["GEOS"] = shapely.geos_version_string
    except (ImportError, AttributeError):
        pass
    try:
        import pyproj

        versions["PROJ"] = pyproj.proj_version_str
    except (ImportError, AttributeError):
        pass
    try:
        import pyogrio

        versions["GDAL"] = ".".join(str(part) for part in pyogrio.__gdal_version__)
    except (ImportError, AttributeError):
        pass
    return versions


def _amplification(bbox_candidates: int, predicate_candidates: int) -> float | None:
    if predicate_candidates == 0:
        return None
    return bbox_candidates / predicate_candidates


def _query_pairs(polygons, geometries, *, predicate: str | None):
    return polygons.geometry.sindex.query(
        geometries,
        predicate=predicate,
        sort=False,
    )


def profile_point_workload(workload, *, adapter: KernelAdapter = CURRENT_ADAPTER) -> dict[str, Any]:
    left, reprojection_seconds = _seconds(lambda: workload.points.to_crs(workload.polygons.crs))
    bbox_pairs, bbox_query_seconds = _seconds(
        lambda: _query_pairs(workload.polygons, left.geometry, predicate=None)
    )
    predicate_pairs, tree_query_seconds = _seconds(
        lambda: _query_pairs(workload.polygons, left.geometry, predicate="intersects")
    )

    def assemble() -> dict[str, int]:
        left_indices = predicate_pairs[0]
        counts = np.bincount(left_indices, minlength=len(left))
        return {
            "matched_unique": int(np.count_nonzero(counts == 1)),
            "ambiguous_multiple": int(np.count_nonzero(counts > 1)),
            "unmatched_outside": int(np.count_nonzero(counts == 0)),
        }

    status_counts, assembly_seconds = _seconds(assemble)
    (result, audit), public_kernel_seconds = _seconds(
        lambda: adapter.assign_points(
            workload.points,
            workload.polygons,
            point_id_col="point_id",
        )
    )

    bbox_candidates = int(bbox_pairs.shape[1]) if bbox_pairs.ndim == 2 else len(bbox_pairs)
    predicate_candidates = (
        int(predicate_pairs.shape[1]) if predicate_pairs.ndim == 2 else len(predicate_pairs)
    )
    return {
        "kind": "point",
        "workload": workload.name,
        "adapter": adapter.name,
        "inputs": {"points": len(workload.points), "polygons": len(workload.polygons)},
        "cardinality": {
            "bbox_candidates": bbox_candidates,
            "predicate_candidates": predicate_candidates,
            "result_rows": len(result),
            "candidate_amplification": _amplification(bbox_candidates, predicate_candidates),
        },
        "status_counts": status_counts,
        "audit": audit.__dict__,
        "timings_seconds": {
            "reprojection": reprojection_seconds,
            "bbox_tree_query": bbox_query_seconds,
            "predicate_tree_query": tree_query_seconds,
            "diagnostic_result_assembly": assembly_seconds,
            "public_kernel_total": public_kernel_seconds,
        },
    }


def profile_areal_workload(
    workload,
    *,
    adapter: KernelAdapter = CURRENT_ADAPTER,
    area_crs: str = "EPSG:3857",
) -> dict[str, Any]:
    query_objects, query_reprojection_seconds = _seconds(
        lambda: workload.objects.to_crs(workload.polygons.crs)
    )
    bbox_pairs, bbox_query_seconds = _seconds(
        lambda: _query_pairs(workload.polygons, query_objects.geometry, predicate=None)
    )
    predicate_pairs, tree_query_seconds = _seconds(
        lambda: _query_pairs(workload.polygons, query_objects.geometry, predicate="intersects")
    )

    metric_inputs, metric_reprojection_seconds = _seconds(
        lambda: (workload.objects.to_crs(area_crs), workload.polygons.to_crs(area_crs))
    )
    metric_objects, metric_polygons = metric_inputs
    left_indices = predicate_pairs[0]
    right_indices = predicate_pairs[1]

    def exact_intersections() -> np.ndarray:
        return np.asarray(
            [
                metric_objects.geometry.iloc[int(left_index)]
                .intersection(metric_polygons.geometry.iloc[int(right_index)])
                .area
                for left_index, right_index in zip(left_indices, right_indices)
            ],
            dtype="float64",
        )

    overlap_areas, exact_geometry_seconds = _seconds(exact_intersections)

    def assemble() -> dict[str, int]:
        retained = overlap_areas > 0.0
        retained_left = left_indices[retained]
        counts = np.bincount(retained_left, minlength=len(workload.objects))
        return {
            "matched_single": int(np.count_nonzero(counts == 1)),
            "matched_multiple": int(np.count_nonzero(counts > 1)),
            "unmatched_outside": int(np.count_nonzero(counts == 0)),
            "positive_area_relations": int(np.count_nonzero(retained)),
        }

    status_counts, assembly_seconds = _seconds(assemble)
    (result, audit), public_kernel_seconds = _seconds(
        lambda: adapter.relate_areal_objects(
            workload.objects,
            workload.polygons,
            object_id_col="object_id",
            area_crs=area_crs,
        )
    )

    bbox_candidates = int(bbox_pairs.shape[1]) if bbox_pairs.ndim == 2 else len(bbox_pairs)
    predicate_candidates = (
        int(predicate_pairs.shape[1]) if predicate_pairs.ndim == 2 else len(predicate_pairs)
    )
    return {
        "kind": "areal",
        "workload": workload.name,
        "adapter": adapter.name,
        "inputs": {"objects": len(workload.objects), "polygons": len(workload.polygons)},
        "cardinality": {
            "bbox_candidates": bbox_candidates,
            "predicate_candidates": predicate_candidates,
            "result_rows": len(result),
            "candidate_amplification": _amplification(bbox_candidates, predicate_candidates),
        },
        "status_counts": status_counts,
        "audit": audit.__dict__,
        "timings_seconds": {
            "query_reprojection": query_reprojection_seconds,
            "bbox_tree_query": bbox_query_seconds,
            "predicate_tree_query": tree_query_seconds,
            "metric_reprojection": metric_reprojection_seconds,
            "diagnostic_scalar_exact_geometry": exact_geometry_seconds,
            "diagnostic_result_assembly": assembly_seconds,
            "public_kernel_total": public_kernel_seconds,
        },
    }


def run_suite(
    preset: str = "small",
    *,
    adapters: Mapping[str, KernelAdapter] | None = None,
) -> dict[str, Any]:
    selected = adapters or {CURRENT_ADAPTER.name: CURRENT_ADAPTER}
    results = []
    for adapter in selected.values():
        for case in POINT_CASES:
            results.append(profile_point_workload(make_point_workload(case, preset), adapter=adapter))
        for case in AREAL_CASES:
            results.append(profile_areal_workload(make_areal_workload(case, preset), adapter=adapter))
    return {"preset": preset, "runtime_versions": runtime_versions(), "results": results}
