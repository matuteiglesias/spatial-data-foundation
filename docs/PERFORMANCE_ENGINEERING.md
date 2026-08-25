# Performance Engineering Program

## Purpose

The performance goal is not “make every function lower-level.” It is to identify the expensive phases of the two foundational relation kernels, remove avoidable Python/DataFrame overhead, and keep the algorithm appropriate to the geometry structure.

All optimization is subordinate to semantic parity.

## What can and cannot become linear

For arbitrary point/polygon or polygon/polygon relations there is no general guarantee of linear-time joining independent of geometry distribution. A naive scan is O(N x M). The appropriate general algorithm is a spatial index whose cost is driven by index construction, query count, bounding-box overlap, predicate work, and result cardinality.

The practical target is therefore:

```text
avoid N x M
make candidate generation output-sensitive
make exact geometry work vectorized
make result assembly O(N + K)
```

where K is the number of retained candidate relations.

Regular grids are different. A future point-to-grid kernel can use affine index arithmetic and approach O(N). Do not distort arbitrary administrative polygon relations into a grid problem merely to claim linear complexity.

## Current hot-path decomposition

### `assign_points`

Current shape:

1. select ID + geometry columns;
2. `to_crs` points to polygon CRS;
3. `gpd.sjoin(..., predicate="intersects")`;
4. retain only two ID columns from the joined frame;
5. pandas groupby candidate count;
6. Python loop over every point to assign status;
7. DataFrame merge of status back to candidates.

The spatial predicate itself is already index-backed. The likely waste is the full GeoPandas frame-join machinery plus Python-level status assembly.

### `relate_areal_objects`

Current shape:

1. select source and target ID + geometry columns;
2. transform source geometry to target CRS;
3. `gpd.sjoin(..., predicate="intersects")`;
4. retain ID pairs;
5. project all valid source objects and all target polygons to metric CRS;
6. construct indexed geometry Series;
7. Python loop over every candidate pair;
8. scalar intersection and scalar area;
9. pandas groupby relation count;
10. Python loop over every source object to emit invalid/unmatched/matched rows.

The two obvious hot spots are the full join materialization and scalar geometry loop.

## Why direct `sindex.query` is the first candidate optimization

GeoPandas 1.1 `sjoin` is implemented in two distinct phases:

```text
_geom_predicate_query()
    -> right_df.sindex.query(...)

_frame_join()
    -> DataFrame index reset / suffix handling / reindexing / concatenation
```

The foundation needs only compact positional relation pairs, not a general DataFrame join. The direct spatial-index interface therefore removes work that is semantically irrelevant to our result.

GeoPandas `SpatialIndex` is itself a thin wrapper around Shapely STRtree and supports array queries with predicate evaluation. The GeometryArray caches the spatial index. Consequently:

- use `GeoSeries.sindex.query` as the preferred 0.2 low-level seam;
- benchmark raw `shapely.STRtree` only as an alternative;
- do not create another persistent index/cache abstraction unless the wrapper demonstrably costs enough to matter.

## Candidate relation kernel

A private conceptual primitive may emerge during implementation, but should not be public in 0.2:

```python
query_idx, tree_idx = polygons.geometry.sindex.query(
    query_geometry,
    predicate="intersects",
    sort=False,
)
```

The pair arrays become the authority for downstream compact assembly.

Required properties:

- positional, not caller-index dependent;
- empty geometries cannot produce false candidates;
- no implicit sorting contract;
- exact predicate is evaluated in the query CRS;
- candidate pair order remains non-semantic.

## Vectorized polygon intersection

Candidate pair arrays can align geometry arrays directly:

```text
source_metric.take(source_idx)
target_metric.take(target_idx)
          |
          v
shapely.intersection(array_a, array_b)
          |
          v
shapely.area(intersections)
```

The implementation should use stable public GeoPandas/Shapely array access, not private `_data` attributes from GeoPandas internals.

Potential metric-projection strategies to benchmark:

### Strategy A — project all valid inputs

Simplest and likely best when most objects participate.

```text
all valid source -> metric CRS
all target -> metric CRS
candidate pair take
```

### Strategy B — project candidate-participating subsets only

Potentially cheaper when most source objects are unmatched or when target geography is very large relative to the queried region.

```text
unique source candidate indices
unique target candidate indices
project subsets once
map candidate pairs to subset positions
```

Do not select B solely because it transforms fewer geometries; extra indexing/mapping overhead can erase the benefit.

## Status assembly

### Point membership

Given query-side positional index array `q_idx`, candidate counts can be derived with NumPy:

```text
counts = bincount(q_idx, minlength=n_points)
```

Then status is an O(N) mask operation:

```text
invalid geometry      -> invalid_point
valid + count == 0    -> unmatched_outside
valid + count == 1    -> matched_unique
valid + count > 1     -> ambiguous_multiple
```

This avoids a groupby plus per-point Python loop.

### Areal relations

Use the same pattern for valid source objects:

```text
positive retained pairs
      -> bincount(source_pair_idx)
      -> matched_single / matched_multiple

valid source with zero retained pairs
      -> unmatched_outside

invalid source
      -> invalid_geometry
```

Result construction can concatenate:

1. matched relation rows;
2. one unmatched row per unmatched source;
3. one invalid row per invalid source.

No Python loop over each source object is required.

## Benchmark harness

### Goals

The benchmark harness decides whether an optimization is worth merging. It is not a marketing benchmark and should not be an absolute-time CI gate.

Record phase-level metrics so an apparent speedup can be explained:

```text
input objects
input polygons
invalid objects
bbox hits
predicate hits
retained positive-area pairs
candidate amplification = bbox hits / predicate hits
tree-query time
CRS-transform time
exact-intersection time
result-assembly time
total wall time
peak RSS when available
```

### Implementations to compare

For point membership:

- P0: current `gpd.sjoin` baseline;
- P1: `GeoSeries.sindex.query` + compact assembly;
- P2: raw `shapely.STRtree.query` only if P1 leaves measurable wrapper overhead.

For areal overlap:

- A0: current `gpd.sjoin` + scalar pair loop;
- A1: direct `sindex.query` + scalar intersection;
- A2: direct `sindex.query` + vectorized Shapely intersection;
- A3: A2 + candidate-subset reprojection, benchmark-only until justified.

### Synthetic profiles

#### Point cases

`point_uniform`
- grid-like non-overlapping polygons;
- most points have one candidate;
- measures normal administrative assignment.

`point_boundary`
- deliberate exact-boundary points;
- two candidates for a controlled fraction;
- protects ambiguity semantics.

`point_outside`
- many points outside geography;
- tests sparse candidate behavior and the value of avoiding unnecessary downstream work.

`point_dense_overlap`
- overlapping polygons;
- intentionally high K;
- demonstrates output-sensitive behavior.

#### Areal cases

`areal_tiles`
- mostly one-to-one rectangles;
- low candidate amplification.

`areal_cross_boundary`
- controlled 60/40 and near-tie source polygons;
- protects current contract.

`areal_slivers`
- many tiny positive intersections around the configured threshold;
- tests exact area/filter cost.

`areal_sparse_multipolygon`
- widely separated MultiPolygon parts whose combined bounding boxes overlap many unrelated objects;
- detects STRtree envelope pathology.

`areal_outside`
- many source polygons with no match.

### Sizes

The committed benchmark generator should support deterministic sizes rather than committing huge fixtures.

Suggested presets:

```text
small   1e3 query objects
medium  1e4–1e5 query objects
large   1e6 points or a candidate-pair scale that remains practical locally
```

Polygon counts should be independently configurable so the benchmark can distinguish input scaling from output density.

### Real-data optional benchmark

The benchmark runner may accept caller-provided local GADM or crosswalk data. It must never download data automatically and must never make the test suite depend on those local files.

## Merge evidence thresholds

Performance timings vary across machines. Use relative evidence, not absolute milliseconds.

### Replacing `sjoin` with direct index query

Merge only if:

- candidate/result parity is exact;
- median runtime is not materially worse on small cases;
- at least one medium/large realistic case shows a meaningful wall-time or memory reduction;
- implementation complexity remains smaller than or comparable to the removed DataFrame machinery.

A 10–20% improvement may be sufficient if the new implementation is also simpler and uses less memory. Do not require an artificial 2x result.

### Vectorizing exact intersection

Expected to be a stronger improvement. Merge if:

- output parity is exact or numerically identical within an explicit floating tolerance where projection libraries make bitwise identity unrealistic;
- medium/high-K cases show clear improvement;
- small cases do not regress enough to matter;
- no precision snapping/repair is introduced.

### Raw STRtree instead of GeoPandas sindex

Default decision: **do not** replace `sindex.query`.

Use raw STRtree only if benchmark evidence shows a repeatable material improvement that cannot be obtained through the public `sindex` interface. The GeoPandas wrapper is already thin, gives cached tree ownership, and reduces dependency on Shapely index-management details.

### MultiPolygon part indexing

Do not merge by default. Consider only if:

- `bbox_hits / predicate_hits` is very high for realistic inputs;
- exploded-part indexing materially reduces query time overall;
- extra deduplication/mapping does not erase the gain;
- authoritative analytical geometry remains untouched.

### Chunking

Do not add for speed alone. Add only if large-case peak memory is a real constraint. The chunked and unchunked relation outputs must be semantically identical after canonical sorting.

### Threading

Do not add until after vectorization. Merge only if benchmark scaling is convincing and deterministic output/memory behavior remain acceptable.

## Correctness/performance interaction hazards

### Do not use `overlay` as the overlap kernel

GeoPandas overlay can repair invalid geometry by default. Generic relation semantics intentionally fail/record invalidity rather than silently choosing repair policy.

### Do not use precision grids as an optimization

Shapely precision models can improve robustness and sometimes performance, but they change geometry. Any precision reduction would need its own explicit analytical contract.

### Do not sort hot-path candidate arrays unless necessary

STRtree result order is not semantic. Sorting adds O(K log K) work. Sort only at the serialization/comparison boundary where deterministic ordering is required.

### Do not infer outside coverage from no spatial match

The relation kernel may report `unmatched_outside` with respect to the supplied geography geometry. Downstream scientific coverage semantics remain separate.

## Profiling questions for implementation agents

Every performance PR should answer:

1. What fraction of time was in tree query, transformation, exact geometry, and table assembly before the change?
2. Did the change reduce wall time, peak memory, or both?
3. How does benefit change as K/N grows?
4. Is the spatial index being rebuilt unnecessarily?
5. Are sparse MultiPolygon envelopes generating excess bounding-box hits?
6. Are we transforming geometries that never participate in a candidate relation?
7. Is any remaining Python loop proportional to K or N in a hot path?
8. Would a lower-level API add enough benefit to justify losing GeoPandas guarantees?

## Expected end state

The common relation path should read conceptually as:

```text
GeoPandas owns CRS-aware geometry arrays and cached STRtree
            |
            v
sindex.query returns NumPy positional pairs
            |
            v
Shapely vectorized GEOS work where exact geometry is needed
            |
            v
NumPy computes counts/masks
            |
            v
pandas materializes the small semantic result
```

That is a lower-level spatial engine without becoming a custom GIS library.
