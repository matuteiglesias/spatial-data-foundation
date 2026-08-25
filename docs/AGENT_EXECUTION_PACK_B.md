# Agent Execution Pack B

## Purpose

This file converts `BUILD_PACK_B.md` into bounded agent-ready jobs. Agents should read `AGENTS.md`, `NEXT_VERSION_ARCHITECTURE.md`, `PERFORMANCE_ENGINEERING.md`, `STACK_INTEGRATION_AUDIT.md`, and `BUILD_PACK_B.md` before implementation.

Every agent starts from fresh `main`, inspects current code rather than assuming these documents are still exact, and stops when its bounded deliverable is satisfied.

Do not merge speculative optimizations merely because they are technically possible.

---

## Agent B0 — Spatial Relation Benchmark Authority

**Branch:** `bench/spatial-relation-baseline`

**Role:** algorithms/performance engineer.

### Mission

Create the deterministic benchmark and profiling authority that all later relation-kernel optimization must use.

### Inspect first

- `src/spatial_foundation/geography/membership.py`
- `src/spatial_foundation/geography/overlap.py`
- all membership/overlap/adversarial tests
- current dependency and CI configuration
- `docs/PERFORMANCE_ENGINEERING.md`

### Required deliverable

Create a network-free `benchmarks/` package or scripts with deterministic generated workloads for:

- point uniform;
- point boundary ambiguity;
- point outside;
- point dense overlap;
- areal tiles;
- areal cross-boundary;
- areal slivers;
- areal outside;
- sparse MultiPolygon envelope pathology.

Produce phase-level JSON metrics, not only a total time.

At minimum record input sizes, result/candidate cardinality, tree-query time, exact geometry time where applicable, result assembly time, total wall time, and runtime versions. Record bbox/predicate amplification where possible.

Support small/medium/large deterministic presets and an optional caller-provided local real-data path without any automatic download.

### Benchmark comparison contract

The harness must be able to compare current public kernels with an alternate implementation from the same branch or a callable adapter. Do not force later agents to rewrite the harness.

### Tests

Test benchmark generator determinism and structural invariants. Do not turn absolute timing into a CI pass/fail threshold.

### Non-goals

- no production kernel rewrite;
- no new public package API;
- no third-party benchmark framework unless clearly justified;
- no large committed binary data;
- no network fetch.

### PR evidence

PR body must include one baseline benchmark summary from the current implementation and explain where time is currently spent.

### Definition of done

Later performance work can make an evidence-backed choice between `sjoin`, `sindex.query`, raw STRtree, scalar intersection, and vectorized intersection.

---

## Agent B1 — Spatial Correctness and Installed Provenance

**Branch:** `fix/runtime-provenance-crs-point-invariants`

**Role:** geospatial correctness/reproducibility engineer.

### Mission

Close correctness gaps independently of performance rewrites.

### Inspect first

- `materialize.py`
- `gadm.py`
- `membership.py`
- `overlap.py`
- `models.py`
- `empirical-data-contracts` current public `RunManifest` contract
- distribution tests and release workflow

### Required work

#### Installed provenance

Change code-commit resolution so an installed wheel without Git metadata records `code_commit=None` instead of failing. Preserve explicit argument, environment override, and resolvable source-checkout SHA precedence.

Add a clean-wheel synthetic GADM materialization test that does not pass `code_commit`.

#### Runtime stack provenance

Collect package/native versions needed to diagnose spatial rebuild changes and persist them under run parameters. Keep this collector small and failure-tolerant for optional libraries.

#### Metric CRS invariant

Implement a private PyProj-based guard used by every code path that emits `_m2` or `_km2` values. Require a projected CRS whose horizontal units are metres. Test EPSG:6933 and EPSG:3857 as accepted unit cases, EPSG:4326 and at least one foot-based CRS as rejected.

Do not claim equal-area accuracy merely from projected metre units.

#### Point-invalid semantics

Make `INVALID_POINT` real. Missing/empty input Point geometry must be distinguishable from valid geometry outside the target geography. Unsupported geometry family must fail closed.

Check current consumers before deciding whether MultiPoint belongs in the supported family. Do not broaden the contract without evidence.

#### Shared target invariants

Use small private helpers if useful so point and areal kernels agree on target ID/CRS/analytical-geometry requirements. Avoid a new validation framework.

### Validation

- full tests and Ruff;
- distribution boundary;
- clean-wheel materialization;
- adversarial point/CRS cases;
- no public API expansion unless unavoidable.

### Non-goals

- no relation performance rewrite;
- no source I/O modernization;
- no dependency-floor sweep except what is strictly required by correctness;
- no downstream consumer changes.

### Definition of done

Installed-package materialization works without Git, metre-labelled areas cannot be angular/foot areas, and point status semantics are complete.

---

## Agent B2 — Indexed and Vectorized Spatial Relation Kernel

**Branch:** `perf/index-query-vectorized-relations`

**Role:** computational geometry/performance engineer.

### Preconditions

Start only after the B0 benchmark authority is merged. Prefer B1 merged first.

### Mission

Use the lowest useful stable abstraction in the modern stack to remove avoidable relation overhead while preserving the public contract exactly.

### Inspect first

- current post-B1 membership and overlap implementations;
- benchmark harness/results;
- GeoPandas 1.1 `sjoin` and `SpatialIndex` implementation;
- Shapely 2 vectorized intersection/area and STRtree docs.

### Required experiments

For point membership compare:

1. current `gpd.sjoin` candidate generation;
2. public `polygons.geometry.sindex.query` + compact assembly;
3. raw `shapely.STRtree.query` only if useful as a benchmark comparator.

For areal relation compare:

1. current join + scalar exact intersection;
2. direct `sindex.query` + scalar intersection;
3. direct `sindex.query` + vectorized Shapely intersection/area.

Also compare all-valid vs candidate-subset metric reprojection if transformation cost is material.

### Preferred architecture

Unless evidence says otherwise:

```text
GeoPandas GeometryArray owns cached STRtree
        |
        v
sindex.query -> NumPy position pairs
        |
        v
Shapely ufuncs for exact geometry
        |
        v
NumPy counts/masks
        |
        v
compact pandas semantic result
```

### Required implementation

- remove full `sjoin` frame materialization where direct index query is materially better;
- remove per-candidate scalar Shapely intersection loop;
- remove per-object Python status loops when a clear vectorized implementation exists;
- do not use private GeoPandas `_data` or `_geom_predicate_query` APIs;
- do not promise result row order;
- do not alter ambiguity or invalidity semantics.

### Raw STRtree decision

Raw STRtree is not automatically more professional than `sindex.query`. GeoPandas `SpatialIndex` is already a thin wrapper and GeometryArray caches it.

Use raw STRtree in production only if measured improvement is repeatable and meaningful enough to justify manual index ownership.

### MultiPolygon experiment

Use B0's sparse MultiPolygon profile to record bbox candidate amplification. Do not implement exploded-part indexing in this PR unless the evidence is unusually strong and the change remains small. Prefer deferring it to conditional B4.

### Performance evidence

Attach before/after benchmark summaries to the PR. Include phase timings and candidate cardinalities. Explain why the final abstraction was chosen.

A different implementation with no meaningful speed/memory benefit is not a successful performance PR.

### Compatibility gates

Candidate pairs, statuses, audit counts, positive-area relation IDs, sliver behavior, and boundary behavior must remain equivalent. Use explicit numeric tolerances only if necessary and justified.

### Non-goals

- no concurrency;
- no chunking unless needed only to run the benchmark itself;
- no precision grid;
- no repair;
- no public index class;
- no I/O rewrite.

### Definition of done

The hot relation path has no per-candidate Python geometry loop, avoids generic DataFrame join work when unnecessary, and has benchmark evidence supporting the result.

---

## Agent B3 — GDAL/Pyogrio I/O and Dependency Boundary

**Branch:** `perf/gadm-io-and-dependency-boundary`

**Role:** geospatial systems and packaging engineer.

### Preconditions

B1 should be merged. B2 may run in parallel, but rebase before finalizing because both can affect imports and `pyproject.toml`.

### Mission

Make source materialization use the native geospatial I/O stack intentionally and make package dependency metadata truthful.

### Inspect first

- current `_read_single_level` / `_read_level` logic;
- synthetic materialization tests;
- Pyogrio 0.13 `list_layers`, `read_info`, `read_dataframe`, Arrow support;
- current GeoPandas file/GeoParquet APIs;
- current clean-install dependency resolution.

### Required work

#### Metadata-first source discovery

For multi-layer sources, inspect layers and fields before loading full geometry. Select the exact requested GADM level from explicit evidence rather than trial-reading every possibility.

#### Column projection

Read only required GADM identity attributes plus geometry where possible.

#### Arrow transfer

Use `use_arrow=True` in the materialization path when PyArrow is installed and the driver path supports it. Preserve a tested non-Arrow behavior if the library/API requires fallback.

#### Runtime metadata

Coordinate with B1 runtime provenance so Pyogrio/GDAL and PyArrow versions are captured once, not by duplicate collectors.

#### Dependencies

After imports settle, explicitly declare every directly imported core dependency.

Raise minimum versions only to APIs the implementation genuinely requires and add a minimum-dependency CI proof.

Remove speculative extras with no implementation:

- DuckDB from `io`;
- `raster`;
- `cli`.

Do not add their replacement features.

### GeoParquet

Keep current canonical geometry encoding unless a concrete consumer requires a change. Do not enable covering bbox merely because the API exists.

### Validation

- separate-level file source;
- multi-layer GPKG source;
- malformed/missing requested level;
- source hash drift;
- Arrow-enabled materialization;
- clean package installs;
- minimum dependency environment.

### Non-goals

- no remote source acquisition;
- no Arrow streaming architecture;
- no raster;
- no DuckDB query API;
- no relation kernel changes.

### Definition of done

Materialization inspects before it loads, loads only what it needs, uses Arrow opportunistically, and package metadata accurately describes the implementation.

---

## Agent B4 — Conditional Performance Specialist

**Branch:** choose one bounded name after reviewing B0/B2 evidence.

**Role:** performance specialist.

### Start condition

Do not start merely because Build Pack B mentions this agent. Start only if B0/B2 produce evidence for one remaining high-leverage bottleneck.

### Allowed jobs

Choose one:

- deterministic batched query execution to cap memory;
- exploded MultiPolygon part indexing to reduce proven bounding-box amplification;
- bounded threaded GEOS exact work after vectorization.

### Required evidence

Before modifying production code, reproduce the bottleneck with the committed benchmark harness and state the measured problem in the PR body.

### Hard stop

If the intervention does not materially improve the measured bottleneck after accounting for added complexity, close/drop the branch rather than merging activity for its own sake.

---

# Integration/review role

After B0–B3 are merged, a final integration reviewer should run a small architecture census rather than add new features.

Questions:

1. Does every direct dependency correspond to a production import/architectural role?
2. Are any transitive internals being relied upon accidentally?
3. Does installed-wheel materialization run without Git?
4. Can any area-labelled output still use a non-metre CRS?
5. Are all point states reachable and tested?
6. Are hot geometry loops vectorized?
7. Is spatial-index ownership duplicated?
8. Does I/O load entire layers unnecessarily?
9. Do benchmark results justify the chosen low-level seam?
10. Did any speculative surface enter the package without a consumer?

If these are clean, prepare the 0.2 release separately. Do not continue refactoring simply because the repository is open.
