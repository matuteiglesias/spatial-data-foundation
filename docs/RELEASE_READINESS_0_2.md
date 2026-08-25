# 0.2 Release Readiness

Status: **implementation-complete candidate; not yet published**.

This document closes Build Pack B as an engineering program. It records what is now authoritative, the hosted validation evidence behind the candidate, and the explicit decision not to add a speculative B4 optimization wave.

The package version remains `0.1.0` until a human explicitly approves the release/version-bump step. No tag or package publication is implied by this readiness record.

## Implemented waves

### B0 — benchmark authority

The repository has deterministic, network-free point and areal benchmark workloads with machine-readable JSON output, runtime/native stack versions, phase timings, candidate cardinality and bbox-to-predicate amplification. The harness can compare a frozen reference implementation with the current kernels and can accept caller-provided local spatial inputs without downloading data.

### B1 — correctness and installed provenance

The supported contract now includes:

- installed-wheel materialization without Git metadata;
- package/runtime/native-library provenance in run parameters;
- projected-metre CRS validation before emitting `_m2` / `_km2` quantities;
- explicit invalid/outside/ambiguous point states;
- shared analytical-geography validation for relation kernels.

### B2 — low-overhead relation kernels

The production relation path now uses:

```text
GeoPandas CRS-aware arrays + cached spatial index
                |
                v
       sindex.query positional pairs
                |
                v
     Shapely vectorized GEOS operations
                |
                v
        NumPy counts and masks
                |
                v
       compact pandas result
```

The point path no longer materializes a generic `sjoin` frame or loops over points for status assembly. The areal path no longer performs scalar Python intersection/area work per candidate or loops over source objects for result assembly.

The B1 kernels are retained only under benchmark infrastructure as a parity/performance reference; they are not part of the public package API.

### B3 — GADM I/O and dependency truth

GADM materialization now:

- validates registered source hashes before source interpretation;
- inspects vector layers/fields with Pyogrio before loading complete geometry;
- selects requested native ADM levels from explicit `GID_*` evidence;
- projects reads to the identity attributes actually needed by normalization;
- uses GDAL/Pyogrio Arrow transfer in the PyArrow-backed materialization workflow;
- retains staged publication and RED failure manifests;
- supports separate-level vector sources, multi-layer GeoPackages and GeoParquet sources.

Direct production dependencies are explicitly declared. The only owned optional extras are `io`, `presentation`, and `dev`; speculative DuckDB, raster, and CLI promises were removed.

## B4 decision — skipped by evidence

Build Pack B4 was conditional. The merged B2 benchmark evidence does not justify another optimization wave for 0.2.

Hosted medium-workload evidence from the B2 comparison included:

| Workload | B1 reference | Current kernel |
| --- | ---: | ---: |
| point uniform | 24.19 ms | 6.19 ms |
| point boundary | 21.43 ms | 6.23 ms |
| point outside | 19.39 ms | 5.25 ms |
| point dense overlap | 33.24 ms | 15.70 ms |
| areal tiles | 1.066 s | 19.25 ms |
| areal cross-boundary | 1.171 s | 36.55 ms |
| areal slivers | 1.158 s | 35.12 ms |
| areal outside | 270.3 ms | 7.05 ms |
| areal sparse MultiPolygon | 287.3 ms | 9.17 ms |

The deliberately pathological sparse-MultiPolygon medium case produced `1026` bounding-box candidates for `2` exact predicate candidates, a `513x` amplification, but the predicate query itself remained about `0.55 ms`. That is evidence to continue measuring the pathology, not evidence to add exploded-part indexing.

No hosted evidence currently shows:

- unacceptable peak memory requiring deterministic chunking;
- material spatial-index cost requiring parent/part index machinery;
- a remaining GEOS bottleneck with demonstrated 2/4-thread scaling.

Therefore B4-A batching, B4-B part indexing and B4-C threaded exact work are all **deferred**. They should be reopened only from a concrete large/real consumer benchmark.

## Supported public semantics

### Point membership

`assign_points(...)` is Point-only and preserves uncertainty rather than inventing assignment policy:

- valid interior point with one candidate -> `matched_unique`;
- valid point with no candidate -> `unmatched_outside`;
- exact-boundary / multiple candidates -> `ambiguous_multiple`;
- missing, empty or invalid Point geometry -> `invalid_point`;
- unsupported source geometry family -> fail closed;
- target geography must be analytical, valid, non-empty and have unique/non-missing IDs and a CRS.

Candidate row ordering is not a public semantic contract.

### Areal relation

`relate_areal_objects(...)` emits geometric relation facts, never ownership policy:

- positive-area one-target relation -> `matched_single`;
- positive-area multi-target relation -> `matched_multiple`;
- valid source with no positive-area relation -> `unmatched_outside`;
- missing/empty/invalid source geometry -> `invalid_geometry`;
- boundary-only touches are not positive-area relations;
- `overlap_area_m2` and `overlap_share_of_object` are geometric facts only;
- no winner, tie-break, population allocation, treatment or exposure policy is inferred.

Any `area_crs` used for metre-labelled output must be projected and expose metre horizontal axes. That validates units, not universal distortion-free area measurement.

## Materialization and provenance contract

`materialize_gadm(...)` never downloads source data. It operates on registered immutable local source snapshots.

Code identity is resolved in this order:

```text
explicit code_commit
    -> environment override
    -> resolvable checkout Git SHA
    -> None
```

An installed wheel is therefore a first-class execution environment. `code_commit=None` is valid when no source checkout exists; the manifest still records package version, runtime/native stack versions, input snapshot hashes, output content hashes, parameters and QA.

## Dependency floor

The 0.2 candidate declares and executes against:

```text
Python                    >= 3.10
empirical-data-contracts >= 0.1,<0.2
NumPy                     >= 1.24
pandas                    >= 2.2
GeoPandas                 >= 1.1
Shapely                   >= 2.1
PyProj                    >= 3.7
Pyogrio                   >= 0.8
Pydantic                  >= 2.7,<3
```

The `io` extra adds PyArrow `>=15`.

The minimum-dependency CI job resolves the candidate floors on Python 3.10 and executes the core/geography/relation/materialization suite. The exact proof environment currently uses NumPy 1.24.4, pandas 2.2.0, GeoPandas 1.1.0, Shapely 2.1.0, PyProj 3.7.0, Pyogrio 0.8.0, Pydantic 2.7.0 and PyArrow 15.0.0.

## Release gates

The candidate is ready for human release review when the branch containing the final release documentation satisfies all of the following:

- [ ] full pytest on Python 3.10 GREEN;
- [ ] full pytest on Python 3.12 GREEN;
- [ ] Ruff GREEN;
- [ ] wheel/sdist build GREEN;
- [ ] clean core wheel consumer GREEN;
- [ ] clean presentation wheel consumer GREEN;
- [ ] clean `[io]` materialization from an installed wheel GREEN without Git metadata;
- [ ] exact minimum-dependency environment GREEN;
- [ ] B1-vs-current small/medium benchmark comparison GREEN;
- [ ] README and architecture describe current rather than aspirational behavior.

These checks are intentionally evidence gates, not absolute performance thresholds.

The governed release workflow also rebuilds the exact tagged distributions and independently verifies clean core, presentation, and `[io]` materialization environments before allowing the publish job to consume those exact artifacts.

## Explicitly deferred beyond 0.2

The following remain outside the current foundation unless a real consumer creates a bounded requirement:

- source/network acquisition;
- generic geometry repair or precision policy;
- domain winner/tie/ownership policy;
- public STRtree/cache abstraction;
- chunked/threaded/distributed execution;
- raster/GHSL kernels;
- DuckDB spatial query API;
- CLI;
- GeoParquet covering-bbox or alternate geometry encoding;
- treatment/control/exposure semantics.

## Human release action still required

After this readiness PR is reviewed and merged, a separate explicit release action may:

1. bump the package version to `0.2.0` in a bounded release-only change;
2. run the same CI gates against that exact versioned commit;
3. create the `v0.2.0` tag / GitHub Release only after those gates are green.

**Publishing the GitHub Release is the PyPI trigger.** The repository's `Release` workflow checks that the release tag matches the package version, rebuilds wheel/sdist, verifies clean core, presentation, and installed-wheel `[io]` materialization, and then publishes those exact artifacts to PyPI through OIDC. Creating/publishing that release is therefore an explicit external publication action, not a harmless bookkeeping step.

Do not combine the version bump, release publication, or any later consumer migration with unrelated implementation work.
