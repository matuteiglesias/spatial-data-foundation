# Next-Version Architecture — spatial-data-foundation 0.2

## Purpose

This document defines the intended architecture for the next foundation sprint after the 0.1.0 package boundary became installable and externally consumable.

The goal is not to turn this repository into a generic GIS framework. The goal is to make its small public surface behave like a professional spatial substrate: explicit correctness invariants, low-overhead relation kernels, disciplined use of the modern GEOS/PROJ/GDAL stack, reproducible materialization, and enough performance evidence that downstream repositories can rely on it without copying spatial mechanics.

## Design principle

The package should add policy only where the external geospatial stack does not already provide the needed primitive.

```text
empirical-data-contracts
    identity / grain / provenance / QA contracts
                 |
                 v
spatial-data-foundation
    governed spatial semantics and provider normalization
                 |
        +--------+---------+
        |                  |
        v                  v
GeoPandas / pandas     Shapely / PyProj / Pyogrio
containers / tables   GEOS / PROJ / GDAL primitives
```

The foundation is therefore an adapter and governance layer around mature spatial primitives, not a replacement for them.

## Layer ownership

### NumPy

Owns compact positional arrays, masks, counts, and index-pair manipulation.

Expected 0.2 use:

- positional candidate pairs returned by the spatial index;
- `bincount`/mask based candidate counts where clearer than DataFrame groupby;
- vectorized result assembly inputs;
- no public NumPy-specific API contract.

### pandas

Owns the returned tabular relation/status products and deterministic tabular transformations.

Expected 0.2 use:

- final relation DataFrames;
- compact ID lookup and status assembly;
- explicit deterministic sorting only where serialization requires it.

### Shapely / GEOS

Owns exact geometry predicates, spatial indexing, intersection, area, geometry validity predicates, and vectorized geometry operations.

Expected 0.2 use:

- STRtree-backed candidate discovery through GeoPandas `sindex.query` unless benchmarks prove a meaningful benefit from direct `shapely.STRtree` use;
- vectorized `shapely.intersection` and `shapely.area` for polygon relation facts;
- no Python loop over candidate pairs in the hot geometry path;
- no custom R-tree implementation;
- no silent precision snapping or geometry repair inside generic relations.

Shapely STRtree predicate evaluation already uses prepared geometries where possible. Do not add a second explicit preparation layer unless a benchmark demonstrates a distinct repeated-predicate workload that benefits from it.

### PyProj / PROJ

Owns CRS interpretation and linear-unit correctness.

Expected 0.2 use:

- parse all metric-area CRSs with `pyproj.CRS`;
- reject geographic or non-metre projected CRSs when outputs are named `_m2` / `_km2`;
- preserve the declared CRS in run provenance;
- do not attempt to invent projection math in this package.

The foundation guarantees unit correctness, not universal distortion-free area measurement. A caller may deliberately choose a locally appropriate projected CRS. EPSG:6933 remains a useful default for broad cross-country area comparison.

### GeoPandas

Owns GeoDataFrame/GeoSeries orchestration, CRS-aware geometry arrays, cached spatial-index ownership, and common file/GeoParquet interoperability.

Expected 0.2 use:

- retain GeoDataFrame inputs and outputs where currently public;
- use `GeoSeries.sindex.query` directly in hot relation kernels instead of materializing a full `sjoin` result when only positional pairs are required;
- continue using `to_crs` rather than hand-implementing transformations;
- preserve analytical geometry authority and GeoDataFrame CRS metadata.

GeoPandas 1.1 stores the spatial index on its GeometryArray and wraps Shapely STRtree directly. This means a separate foundation-level tree cache is not justified in 0.2.

### Pyogrio / GDAL

Owns vector source inspection and efficient native file I/O.

Expected 0.2 use:

- inspect multi-layer sources with `list_layers` / `read_info` rather than trial-reading whole layers;
- read only required columns when practical;
- enable Arrow transfer when `pyarrow` is installed and the driver supports it;
- preserve explicit failure behavior on invalid/unreadable source material;
- keep network acquisition outside core materialization.

### PyArrow / GeoParquet

Owns efficient persisted columnar interchange.

Expected 0.2 use:

- retain GeoParquet as the silver geography format;
- do not enable GeoParquet covering-bbox columns by default yet: writing them has a cost and they should be activated only when a real downstream filtered-read workload justifies it;
- do not adopt experimental GeoArrow encoding as the canonical persisted geometry until interoperability requirements make that trade-off worthwhile.

### Pydantic and empirical-data-contracts

Own immutable semantic contracts, source snapshot identity, dataset identity, run provenance, and QA records.

The existing boundary stays unchanged:

- `GeographySpec` is dataset-level geography scheme identity;
- `GeographyUnit` is a row-level native geography record;
- `RunManifest.code_commit` may legitimately be `None` for an installed distribution;
- package version plus input/output hashes remain valid provenance when Git metadata is unavailable.

## Relation-engine architecture

### General rule

Do not perform an O(N x M) geometry scan for arbitrary vector relations.

For arbitrary polygons, the general relation shape is output-sensitive spatial indexing:

```text
validate inputs
     |
     v
compact geometry arrays
     |
     v
cached STRtree query + exact predicate
     |
     v
positional index pairs
     |
     +-------------------+
     |                   |
     v                   v
point membership      areal overlap
count/status          vectorized intersection
                       + vectorized area
     |                   |
     +---------+---------+
               v
       compact pandas result
```

A universal linear-time arbitrary polygon join should not be promised. Packed R-tree construction/query is the appropriate general strategy; performance is typically governed by input size, bounding-box overlap, geometry complexity, and output candidate count.

### Point -> polygon membership

Semantic contract remains:

- exact-boundary points remain candidates rather than being silently assigned;
- outside points remain explicit;
- multiple candidates remain ambiguous;
- missing/empty point geometry becomes `invalid_point` rather than being confused with outside coverage;
- non-point source geometry fails closed.

0.2 target hot path:

1. validate point and polygon invariants;
2. reproject the point geometry array once when CRS differs;
3. query `polygons.sindex` directly with `predicate="intersects"` and `sort=False`;
4. derive candidate counts from positional arrays;
5. construct only the compact requested ID/status columns.

The benchmark suite may compare `intersects` with `covered_by` for strict Point inputs, but predicate changes are accepted only with complete boundary parity.

### Polygon -> polygon relation

Semantic contract remains:

- foundation emits positive-area candidate facts;
- no winner/tie/ownership policy;
- invalid source geometry is explicit;
- invalid analytical geography fails closed;
- boundary-only touching produces no positive-area relation.

0.2 target hot path:

1. validate IDs/geometry/CRS;
2. query the analytical polygon spatial index directly for exact `intersects` candidate pairs;
3. reproject geometry for metric-area computation;
4. align candidate geometry arrays positionally;
5. compute intersections with Shapely vectorized ufuncs;
6. compute area and source-object share vectorially;
7. discard non-positive/sliver candidates;
8. assemble matched/unmatched/invalid statuses without a Python loop over source objects.

Whether to reproject every valid geometry or only unique geometries participating in candidates is a benchmark decision, not an architectural assumption.

## Index quality and pathological geometries

STRtree efficiency depends on bounding boxes. A sparse MultiPolygon whose components are far apart can have a very large envelope and generate many useless bounding-box candidates.

0.2 does not automatically explode analytical MultiPolygons. Instead the benchmark program must measure:

```text
bbox candidate count / exact predicate hit count
```

for representative and deliberately pathological MultiPolygon cases.

If that amplification is materially costly, a later private indexing strategy may explode MultiPolygon parts *for index construction only*, retain a mapping to the authoritative parent geometry, and deduplicate parent candidate pairs before exact relation work. Analytical geometry must remain unchanged.

This optimization is conditional evidence-driven work, not part of the default 0.2 semantic contract.

## Scaling strategy

### Stage 1 — remove avoidable Python/DataFrame overhead

- direct spatial-index pair query;
- NumPy positional manipulation;
- vectorized Shapely operations;
- no full `sjoin` frame when only IDs are needed.

### Stage 2 — reduce unnecessary I/O and transforms

- inspect layers before reading;
- read only required attributes;
- Arrow-backed GDAL transfer;
- benchmark candidate-only metric reprojection.

### Stage 3 — bound memory only when needed

If million-row relations demonstrate unacceptable peak memory, process query objects in deterministic batches against the same cached tree and concatenate relation chunks. This must preserve the same semantic result and must not become an orchestration framework.

### Stage 4 — parallelism only after vectorization

Shapely releases the GIL during GEOS-heavy operations, so threads can help some workloads. However, parallelism is not the first optimization. It adds scheduling and memory pressure and can obscure deterministic performance reasoning.

Threaded execution is considered only if:

- the single-thread vectorized kernel remains a measured bottleneck;
- a benchmark demonstrates useful scaling;
- output determinism is unchanged;
- peak memory remains acceptable.

No process pool, Dask, Ray, Spark, or distributed orchestration belongs in the 0.2 foundation sprint.

## Algorithm dispatch by spatial structure

The foundation should not force every future spatial problem through polygon STRtree relations.

```text
arbitrary point -> arbitrary polygon
    STRtree predicate query

arbitrary polygon -> arbitrary polygon
    STRtree candidate query + vectorized exact intersection

nearest / distance-bounded vector relation
    STRtree query_nearest / dwithin when a real consumer requires it

point -> regular grid
    future affine/grid-index arithmetic, potentially O(N)

raster zonal measurement
    future raster-native window/block operations
```

This distinction is important. If GHSL or another regular grid becomes a consumer, arithmetic grid indexing is where a genuinely linear relation algorithm may be appropriate. It should be added as a grid/raster kernel, not simulated through arbitrary polygon joins.

## Runtime provenance

Every persisted materialization should record enough runtime information to diagnose a later hash change.

Recommended `RunManifest.parameters["runtime_versions"]` fields:

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
pyarrow (when used)
```

`code_commit` is stronger optional provenance when running from a source checkout. It must not be required for an installed wheel.

## Dependency surface target

By the end of the sprint, declared dependencies should reflect actual direct imports.

Expected core roles after the planned implementation:

```text
empirical-data-contracts  semantic contracts
numpy                     positional relation arrays
pandas                    relation tables
geopandas                 spatial dataframe / CRS / index ownership
shapely                   vectorized geometry kernel
pyproj                    CRS unit validation
pyogrio                   native vector source inspection / I/O
pydantic                  local row-level models
```

`pyarrow` remains optional I/O support. Presentation remains optional.

Remove unused speculative extras (`duckdb` from `io`, `raster`, `cli`) until code that actually needs them exists.

## Public API discipline

The 0.2 sprint should preferably preserve existing public calls:

```python
assign_points(...)
relate_areal_objects(...)
normalize_gadm_frame(...)
materialize_gadm(...)
```

Low-level performance machinery should remain private until there are at least two concrete consumers that need direct control.

Do not expose:

- an STRtree wrapper class;
- a generic geometry-repair framework;
- an assignment/tie-break framework;
- a concurrency executor;
- provider-specific acquisition clients.

## 0.2 definition of architectural completion

The foundation is ready for the next cross-repository integration audit when all of the following are true:

1. an installed wheel can perform GADM materialization without Git metadata;
2. quantities labeled m²/km² cannot be computed in angular or non-metre coordinates;
3. point invalid/outside/ambiguous states are complete and tested;
4. hot spatial relation kernels contain no per-candidate Python geometry loop;
5. candidate discovery avoids full GeoPandas frame joins when only positional pairs are needed;
6. I/O uses source introspection and Arrow opportunistically rather than trial-reading unnecessary data;
7. dependency metadata describes actual direct architectural dependencies;
8. benchmark evidence records both runtime and candidate amplification, without brittle absolute CI timing gates;
9. public semantic outputs remain compatible with 0.1.0;
10. no speculative distributed, raster, CLI, repair, or domain-policy framework has been introduced.

## Primary external references

- GeoPandas spatial indexing: https://geopandas.org/en/stable/docs/user_guide/spatial_indexing.html
- GeoPandas `sjoin`: https://geopandas.org/en/stable/docs/reference/api/geopandas.sjoin.html
- Shapely STRtree: https://shapely.readthedocs.io/en/stable/strtree.html
- Shapely vectorized operations and multithreading: https://shapely.readthedocs.io/en/stable/
- PyProj CRS / coordinate-system API: https://pyproj4.github.io/pyproj/stable/api/crs/crs.html
- Pyogrio API: https://pyogrio.readthedocs.io/en/latest/api.html
- GeoPandas I/O: https://geopandas.org/en/stable/docs/user_guide/io.html
