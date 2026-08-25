import math

from benchmarks.runner import profile_areal_workload, profile_point_workload
from benchmarks.workloads import make_areal_workload, make_point_workload


def _geometry_fingerprint(frame):
    return frame.geometry.to_wkb().tolist()


def test_point_workloads_are_deterministic():
    first = make_point_workload("boundary", "small")
    second = make_point_workload("boundary", "small")

    assert first.points["point_id"].tolist() == second.points["point_id"].tolist()
    assert first.polygons["geo_uid"].tolist() == second.polygons["geo_uid"].tolist()
    assert _geometry_fingerprint(first.points) == _geometry_fingerprint(second.points)
    assert _geometry_fingerprint(first.polygons) == _geometry_fingerprint(second.polygons)


def test_areal_workloads_are_deterministic():
    first = make_areal_workload("sparse_multipolygon", "small")
    second = make_areal_workload("sparse_multipolygon", "small")

    assert first.objects["object_id"].tolist() == second.objects["object_id"].tolist()
    assert first.polygons["geo_uid"].tolist() == second.polygons["geo_uid"].tolist()
    assert _geometry_fingerprint(first.objects) == _geometry_fingerprint(second.objects)
    assert _geometry_fingerprint(first.polygons) == _geometry_fingerprint(second.polygons)


def test_point_profile_reports_ambiguity_and_phase_metrics():
    metrics = profile_point_workload(make_point_workload("boundary", "small"))

    assert metrics["kind"] == "point"
    assert metrics["status_counts"]["ambiguous_multiple"] > 0
    assert metrics["cardinality"]["predicate_candidates"] > metrics["inputs"]["points"]
    assert set(metrics["timings_seconds"]) == {
        "reprojection",
        "bbox_tree_query",
        "predicate_tree_query",
        "diagnostic_result_assembly",
        "public_kernel_total",
    }
    assert all(value >= 0 for value in metrics["timings_seconds"].values())


def test_sparse_multipolygon_profile_exposes_bbox_amplification():
    metrics = profile_areal_workload(make_areal_workload("sparse_multipolygon", "small"))

    assert metrics["kind"] == "areal"
    assert metrics["cardinality"]["bbox_candidates"] > metrics["cardinality"]["predicate_candidates"]
    amplification = metrics["cardinality"]["candidate_amplification"]
    assert amplification is not None and math.isfinite(amplification) and amplification > 1
    assert set(metrics["timings_seconds"]) == {
        "query_reprojection",
        "bbox_tree_query",
        "predicate_tree_query",
        "metric_reprojection",
        "diagnostic_scalar_exact_geometry",
        "diagnostic_result_assembly",
        "public_kernel_total",
    }
    assert all(value >= 0 for value in metrics["timings_seconds"].values())
