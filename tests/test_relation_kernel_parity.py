from __future__ import annotations

import math

import pandas as pd
import pytest

from benchmarks.baselines import baseline_assign_points, baseline_relate_areal_objects
from benchmarks.workloads import AREAL_CASES, POINT_CASES, make_areal_workload, make_point_workload
from spatial_foundation.geography import assign_points, relate_areal_objects


def _point_records(frame: pd.DataFrame) -> list[tuple]:
    rows = []
    for row in frame.itertuples(index=False, name=None):
        point_id, polygon_id, candidate_count, status = row
        rows.append(
            (
                point_id,
                None if pd.isna(polygon_id) else polygon_id,
                int(candidate_count),
                status,
            )
        )
    return sorted(rows, key=lambda row: (str(row[0]), "" if row[1] is None else str(row[1])))


def _areal_records(frame: pd.DataFrame) -> dict[tuple[str, str | None], tuple]:
    records = {}
    for row in frame.itertuples(index=False, name=None):
        object_id, polygon_id, area, share, count, status = row
        key = (object_id, None if pd.isna(polygon_id) else polygon_id)
        records[key] = (area, share, int(count), status)
    return records


@pytest.mark.parametrize("case", POINT_CASES)
def test_indexed_point_kernel_matches_b1_baseline(case):
    workload = make_point_workload(case, "small")

    baseline, baseline_audit = baseline_assign_points(
        workload.points,
        workload.polygons,
        point_id_col="point_id",
    )
    optimized, optimized_audit = assign_points(
        workload.points,
        workload.polygons,
        point_id_col="point_id",
    )

    assert optimized_audit == baseline_audit
    assert _point_records(optimized) == _point_records(baseline)


@pytest.mark.parametrize("case", AREAL_CASES)
def test_vectorized_areal_kernel_matches_b1_baseline(case):
    workload = make_areal_workload(case, "small")

    baseline, baseline_audit = baseline_relate_areal_objects(
        workload.objects,
        workload.polygons,
        object_id_col="object_id",
        area_crs="EPSG:3857",
    )
    optimized, optimized_audit = relate_areal_objects(
        workload.objects,
        workload.polygons,
        object_id_col="object_id",
        area_crs="EPSG:3857",
    )

    assert optimized_audit == baseline_audit
    baseline_records = _areal_records(baseline)
    optimized_records = _areal_records(optimized)
    assert optimized_records.keys() == baseline_records.keys()

    for key, baseline_record in baseline_records.items():
        baseline_area, baseline_share, baseline_count, baseline_status = baseline_record
        area, share, count, status = optimized_records[key]
        assert count == baseline_count
        assert status == baseline_status
        if pd.isna(baseline_area):
            assert pd.isna(area)
            assert pd.isna(share)
        else:
            assert math.isclose(float(area), float(baseline_area), rel_tol=1e-12, abs_tol=1e-12)
            assert math.isclose(float(share), float(baseline_share), rel_tol=1e-12, abs_tol=1e-12)
