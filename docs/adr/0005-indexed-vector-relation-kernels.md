# ADR 0005 — Indexed vector relation kernels behind stable semantics

## Status

Accepted for Build Pack B design.

## Context

The 0.1 relation functions use `geopandas.sjoin`, then retain only compact ID relationships. Areal overlap additionally computes exact intersections in a Python loop. GeoPandas 1.1 implements `sjoin` by querying its Shapely-backed spatial index and then performing a general DataFrame join. Shapely 2 provides vectorized exact geometry operations.

## Decision

The preferred 0.2 hot-path architecture is:

```text
GeoPandas GeometryArray / cached sindex
    -> public sindex.query positional pairs
    -> Shapely vectorized exact geometry where required
    -> NumPy counts/masks
    -> compact pandas semantic result
```

Use raw `shapely.STRtree` only if benchmark evidence shows a material repeatable benefit over the public GeoPandas spatial-index wrapper.

Low-level index machinery remains private. Public semantic APIs remain `assign_points(...)` and `relate_areal_objects(...)` unless concrete consumers later justify another surface.

## Consequences

- avoid O(N x M) scans;
- avoid generic DataFrame join materialization when only positional pairs are needed;
- remove per-candidate scalar geometry loops;
- retain GeoPandas CRS/index ownership and interoperability;
- do not build a custom R-tree/cache abstraction;
- do not promise candidate row order;
- performance rewrites require benchmark and parity evidence.
