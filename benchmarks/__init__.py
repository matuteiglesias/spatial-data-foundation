"""Deterministic, network-free performance probes for spatial-data-foundation.

The benchmark package is development infrastructure, not part of the public
``spatial_foundation`` API.
"""

from .runner import CURRENT_ADAPTER, KernelAdapter, run_suite
from .workloads import AREAL_CASES, POINT_CASES, PRESET_WIDTHS, make_areal_workload, make_point_workload

__all__ = [
    "AREAL_CASES",
    "CURRENT_ADAPTER",
    "KernelAdapter",
    "POINT_CASES",
    "PRESET_WIDTHS",
    "make_areal_workload",
    "make_point_workload",
    "run_suite",
]
