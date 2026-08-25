# Build Pack B — Next-Version Foundation Sprint

## Mission

Move `spatial-data-foundation` from a correct 0.1.0 package boundary to a technically mature 0.2 vector-spatial foundation by tightening correctness invariants, removing avoidable relation-kernel overhead, modernizing source I/O, and making dependency/provenance declarations match the actual geospatial stack.

This build pack is intentionally bounded. It does not migrate downstream repositories. It prepares the foundation so those repositories can be investigated against a stable, evidence-backed spatial authority afterward.

## Global invariants

Every PR in this pack must preserve the current repository invariants in `AGENTS.md` and additionally obey:

- public relation semantics before/after optimization must be identical;
- no domain winner/tie/ownership policy enters the foundation;
- no geometry repair, precision snapping, or simplification is introduced as a hidden optimization;
- no network data acquisition enters core execution or tests;
- no performance claim is accepted without benchmark evidence;
- absolute CI timing is not a merge gate;
- no public low-level index abstraction is introduced merely to support one implementation;
- package-installed execution is first-class, not a fallback to source-checkout behavior.

## Target release

The intended result is suitable for a backward-compatible `0.2.0` release after the full pack is reviewed.

The version bump/release is not part of the implementation waves below unless explicitly requested after all gates are green.

---

# Wave B0 — Benchmark and profiling authority

**Suggested branch:** `bench/spatial-relation-baseline`

**Role:** spatial algorithms/performance engineer.

## Mission

Create a deterministic, network-free benchmark harness that makes performance decisions evidence-based before production kernels are rewritten.

## Required work

Add a non-packaged `benchmarks/` surface containing deterministic generators and a runner for:

### Point profiles

- uniform one-candidate membership;
- exact-boundary ambiguity;
- mostly-outside points;
- deliberately overlapping polygons / high candidate cardinality.

### Areal profiles

- low-overlap tiles;
- controlled 60/40 cross-boundary cases;
- sliver-heavy intersections;
- mostly-outside polygons;
- sparse/widely-separated MultiPolygon parts producing poor envelopes.

The runner must be able to compare the existing implementation with experimental functions supplied on a branch without requiring huge committed fixtures.

## Metrics

Record at least:

```text
input query count
input target count
bbox hit count when measurable
exact predicate hit count
retained relation count
candidate amplification ratio
CRS transform time
index query time
exact geometry time
result assembly time
total wall time
peak RSS if implemented reliably
runtime stack versions
```

Output a machine-readable JSON report plus a compact human-readable summary.

## Implementation restraint

Do not change production relation semantics in B0.

A tiny instrumentation helper may be added under `benchmarks/`; it must not become public package API.

## Validation

- deterministic benchmark generators for a fixed seed/config;
- benchmark runner smoke test or unit tests for generator invariants;
- current pytest + Ruff remain green;
- no performance threshold in ordinary CI.

## Definition of done

B0 ends when a later performance PR can show before/after measurements by workload phase, rather than reporting only one total timing.

---

# Wave B1 — Installed provenance and spatial correctness invariants

**Suggested branch:** `fix/runtime-provenance-crs-point-invariants`

**Role:** geospatial correctness / reproducibility engineer.

**Can start in parallel with B0.**

## Mission

Fix correctness gaps that should not depend on performance work.

## B1.1 — Installed-wheel materialization provenance

Current `materialize_gadm()` must not fail merely because the installed wheel has no Git checkout.

Required behavior:

```text
explicit code_commit
    -> use it

environment code_commit
    -> use it

resolvable source-checkout Git SHA
    -> use it

otherwise
    -> code_commit = None
```

The package version remains required and must come from installed distribution metadata when available.

Add a clean-wheel acceptance test that performs a synthetic GADM materialization without passing `code_commit` and without relying on repository Git metadata.

## B1.2 — Runtime stack provenance

Add a small internal runtime-version collector and include its output in materialization run parameters.

Capture when available:

```text
python
spatial-data-foundation
empirical-data-contracts
numpy
pandas
geopandas
shapely
GEOS
pyproj
PROJ
pyogrio
GDAL
pyarrow
```

Do not modify `empirical-data-contracts` merely to add a spatial-specific top-level field. Put the mapping in `RunManifest.parameters`.

## B1.3 — Metric-area CRS guard

Introduce one shared internal invariant for functions producing metre-based area names.

Required behavior:

- `pyproj.CRS.from_user_input` parses the CRS;
- CRS must be projected;
- horizontal coordinate-system axes must have linear unit conversion factor 1 metre (within a narrow floating tolerance);
- `EPSG:4326` fails;
- a foot-based projected CRS fails;
- `EPSG:3857` passes unit validation even though it is not an equal-area projection;
- default `EPSG:6933` passes.

The error message must explain that `_m2`/`_km2` outputs require metre-based projected coordinates.

Use the guard in both GADM normalization and areal overlap.

## B1.4 — Complete point status semantics

`MembershipStatus.INVALID_POINT` currently exists but is not emitted.

Required behavior:

- missing geometry -> `invalid_point`;
- empty point geometry -> `invalid_point`;
- valid outside Point -> `unmatched_outside`;
- boundary Point -> preserve candidate ambiguity;
- source geometry outside the supported point geometry family fails closed with a clear error rather than being silently treated as a point.

Decide Point versus Point/MultiPoint support from current consumer evidence. Do not broaden the contract accidentally. If no current consumer requires MultiPoint, prefer Point-only semantics for this API and test them explicitly.

## B1.5 — Shared analytical-geography checks

Refactor only enough internal validation to keep membership and areal relations consistent on:

- CRS required;
- ID non-null and unique;
- analytical geometry role;
- target geometry non-null/non-empty/valid.

Do not create a large validation framework. One or two private helpers are enough.

## Validation

Run full CI plus clean-wheel distribution tests.

Add adversarial tests for all new invariants.

## Definition of done

B1 ends when package-installed materialization is valid provenance, metre-labelled areas cannot silently be square degrees/feet, and point-invalid semantics are complete.

---

# Wave B2 — Low-overhead relation engine

**Suggested branch:** `perf/index-query-vectorized-relations`

**Role:** spatial algorithms / numerical performance engineer.

**Starts after B0 benchmark authority is merged. Prefer B1 merged first so the optimized path implements final validation semantics rather than being rewritten twice.**

## Mission

Remove avoidable GeoPandas DataFrame-join and Python scalar-loop overhead while preserving public outputs.

## B2.1 — Point candidate query

Replace the full `gpd.sjoin` materialization with direct use of the public cached spatial index:

```python
query_idx, target_idx = polygons.geometry.sindex.query(
    projected_points.geometry,
    predicate="intersects",
    sort=False,
)
```

Use positional arrays to map IDs and counts.

Do not import GeoPandas private helpers.

## B2.2 — Vectorized point status assembly

Use NumPy masks/counts rather than groupby + per-point Python loop where this is clearer and measurably cheaper.

Ensure unmatched and invalid rows remain represented exactly as required by the public contract.

## B2.3 — Areal candidate query

Replace the full `gpd.sjoin` candidate frame with direct index query returning positional pairs.

Preserve current exact `intersects` candidate semantics in the target/query CRS.

## B2.4 — Vectorized exact overlap

Remove the per-candidate scalar intersection loop.

Use public Shapely vectorized operations over aligned geometry arrays:

```text
candidate source geometry array
candidate target geometry array
        -> shapely.intersection
        -> shapely.area
```

Compute source-object areas vectorially and derive `overlap_share_of_object` without a Python loop.

## B2.5 — Vectorized relation status assembly

Use positional candidate counts/masks to produce:

```text
matched_single
matched_multiple
unmatched_outside
invalid_geometry
```

without looping over every source object.

## Benchmark decisions inside B2

Measure and document:

- baseline `sjoin` vs `sindex.query`;
- scalar vs vectorized intersection;
- total and phase timings;
- candidate cardinality scaling;
- memory where available.

Also benchmark raw `shapely.STRtree` against `GeoSeries.sindex.query`.

Default rule: retain `sindex.query` unless raw STRtree gives a repeatable meaningful benefit beyond the thin wrapper.

## Reprojection experiment

Benchmark both:

- transform all valid objects/targets once;
- transform only unique candidate-participating subsets.

Choose the simpler path unless subset projection materially improves realistic sparse cases.

## Compatibility gates

- exact candidate ID pairs for membership;
- exact assignment statuses and audit counts;
- exact areal relation IDs/statuses/counts;
- overlap areas/shares equal under existing deterministic test CRS, or within an explicitly justified tight tolerance if vectorized execution changes floating evaluation details;
- no new ordering promise;
- current external consumer tests unchanged unless test-only canonical sorting becomes necessary.

## Performance merge gate

Do not merge a rewrite that is merely different.

The final path must demonstrate either:

- meaningful median wall-time improvement on realistic medium/high-K cases; or
- meaningful memory reduction with no material speed regression; or
- both.

If direct `sindex.query` provides no material advantage for a specific kernel, keep the simpler existing implementation for that phase and vectorize only the proven bottleneck.

## Definition of done

B2 ends when no hot geometry relation path contains a per-candidate Python geometry loop and benchmark evidence explains the chosen abstraction level.

---

# Wave B3 — GADM source I/O modernization and dependency truth

**Suggested branch:** `perf/gadm-io-and-dependency-boundary`

**Role:** geospatial systems / packaging engineer.

**Can be developed independently after B1; merge after B2 if both touch dependency metadata.**

## Mission

Use GDAL/Pyogrio intentionally and make dependency metadata reflect actual production imports.

## B3.1 — Metadata-first layer selection

Replace trial-reading of GeoPackage layers with source inspection.

Preferred sequence:

```text
pyogrio.list_layers
      |
      v
pyogrio.read_info for candidate layer
      |
      v
verify requested GADM identity fields
      |
      v
read exact layer
```

For single-layer files, inspect fields before a full read when practical.

Do not weaken the current source snapshot hash validation.

## B3.2 — Column projection

Read only attributes required to normalize the requested level plus geometry.

At minimum consider:

```text
GID_0
GID_<level>
GID_<level-1> when level > 0 and available
geometry
```

The reader must still detect malformed/unexpected sources explicitly.

## B3.3 — Arrow transfer

When PyArrow is available in the materialization workflow, use Pyogrio/GeoPandas Arrow-backed vector reading (`use_arrow=True`) where supported.

No silent alternate scientific semantics may result from the faster I/O path.

## B3.4 — Dependency declaration cleanup

After B2/B3 imports settle, make direct dependencies explicit.

Expected direct production imports may include:

```text
numpy
pandas
geopandas
shapely
pyproj
pyogrio
pydantic
empirical-data-contracts
```

Raise the geospatial minimum versions only to the floors required by the APIs actually used and prove those floors in CI.

Provisional target:

```text
GeoPandas >= 1.1
Shapely >= 2.1
PyProj >= 3.7
pandas >= 2.2
NumPy >= 1.24
Pyogrio >= 0.8
```

Add a minimum-dependency CI job or equivalent clean environment that actually resolves near the intended floors. Do not claim compatibility that is never executed.

## B3.5 — Remove speculative extras

Remove unused package metadata:

- `duckdb` from the `io` extra;
- `raster` extra until raster code exists;
- `cli` extra until CLI code exists.

Keep:

- `io` for PyArrow/GeoParquet support;
- `presentation` as already governed;
- `dev` for test/build/lint dependencies.

## GeoParquet decision

Do not enable covering bbox or GeoArrow geometry encoding by default in this wave.

Document them as evaluated future options. If a benchmark/consumer already demonstrates substantial filtered-read benefit, a separate bounded PR may enable a covering bbox with explicit format/schema tests.

## Validation

- current GADM synthetic materialization parity;
- source drift/failure behavior parity;
- separate-level and GeoPackage coverage;
- clean package install;
- minimum-dependency CI;
- Arrow and non-Arrow tests where feasible without duplicating the whole test suite.

## Definition of done

B3 ends when GADM materialization does not load more vector source structure than it needs, the Arrow path is available when the I/O dependency exists, and package metadata accurately describes supported implementation dependencies.

---

# Wave B4 — Conditional large-scale optimizations

**Suggested branch:** created only if B0/B2 evidence justifies one specific optimization.

**Role:** performance specialist.

This wave is deliberately conditional and may be skipped entirely for 0.2.

Choose at most one or two evidence-backed interventions.

## Candidate B4-A — Batched query execution

Trigger: peak memory for a large relation is unacceptable while the same cached target index can be reused.

Requirements:

- deterministic fixed-size query batches;
- same relation result after canonical sort;
- same audit/status semantics;
- no distributed scheduler.

## Candidate B4-B — MultiPolygon part index

Trigger: realistic source/target geography shows high bbox-to-predicate candidate amplification caused by sparse MultiPolygon envelopes.

Requirements:

- explode only for private index representation;
- preserve authoritative parent geometry;
- map part hits to parent positions;
- deduplicate parent relation candidates before exact relation work;
- benchmark total benefit including mapping/dedup cost.

## Candidate B4-C — Threaded GEOS exact work

Trigger: after vectorization, exact GEOS intersection remains dominant and 2-thread/4-thread benchmarks scale materially.

Requirements:

- fixed deterministic chunk partition;
- output parity;
- no public concurrency API unless another consumer requires it;
- memory remains bounded.

## Stop rule

If B0/B2 do not demonstrate a real bottleneck, skip B4. “Could be faster” is not sufficient evidence.

---

# Release readiness — 0.2

After B0–B3, and B4 only if justified, perform a release-readiness pass.

Required evidence:

```text
pytest                  GREEN
ruff                    GREEN
wheel/sdist build       GREEN
clean core wheel        GREEN
clean presentation      GREEN
clean materialization   GREEN without Git metadata
minimum-dependency env  GREEN
benchmark report        attached / summarized
```

The README/architecture must accurately describe:

- public relation semantics;
- installed-wheel materialization;
- metric CRS rule;
- modern dependency floor;
- optional presentation;
- benchmarked but non-public performance internals.

Do not version-bump or publish until all implementation waves selected for 0.2 are merged.

---

# Parallel agent plan

Safe parallelism:

```text
B0 benchmark authority  --------+
                              |
B1 correctness/provenance -----+----> B2 relation engine
        |                               |
        +----------> B3 I/O/deps <------+
                                       |
                                       v
                              optional B4 only by evidence
```

B0 and B1 can run concurrently from fresh `main` because B0 should not modify production kernels.

B2 should consume the final B1 invariants.

B3 may be prepared in parallel with B2 but must rebase before merge if `pyproject.toml`, runtime provenance, or materializer imports overlap.

B4 is never started speculatively.

---

# Non-goals for Build Pack B

Do not add:

- downstream census/electoral/FCV policy;
- automatic GADM acquisition;
- raster/GHSL implementation;
- DuckDB query API;
- Typer CLI;
- PostGIS integration;
- Dask/Spark/Ray orchestration;
- public STRtree cache/index classes;
- generic geometry repair;
- crosswalk winner/tie policy;
- new presentation features.

The next cross-repository geo-estate audit begins only after this pack leaves a stable 0.2-ready vector foundation.
