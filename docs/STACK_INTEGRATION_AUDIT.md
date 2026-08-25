# Modern Geospatial Stack Integration Audit

## Scope

This audit compares the 0.1.0 implementation with the capabilities of the current Python vector-geospatial stack and identifies where the foundation should delegate more work to external libraries rather than maintain local mechanics.

The audit is intentionally conservative: an external capability is adopted only when it improves correctness, performance, or maintenance without weakening the package's explicit semantic boundaries.

## Current installation surface

A clean Python 3.10 installation of `spatial-data-foundation==0.1.0` resolves approximately this runtime stack:

```text
spatial-data-foundation
├── empirical-data-contracts
│   └── pydantic / pydantic-core
└── geopandas
    ├── pandas / numpy
    ├── shapely / GEOS
    ├── pyproj / PROJ
    ├── pyogrio / GDAL
    └── packaging
```

This is a healthy base. The issue is not package count; it is whether the foundation uses the strongest layer for each job.

## Audit summary

| Layer | 0.1 use | 0.2 direction |
| --- | --- | --- |
| NumPy | mostly transitive | direct positional/counting work in hot kernels |
| pandas | directly imported but transitively declared | declare directly; final semantic table assembly |
| GeoPandas | orchestration + `sjoin` + I/O | keep orchestration; bypass full frame join in compact kernels |
| Shapely | mostly reached through GeoPandas | direct vectorized intersection/area; STRtree remains behind `sindex` by default |
| PyProj | mostly reached through GeoPandas | direct CRS/unit validation |
| Pyogrio | reached indirectly through `read_file` | direct source metadata/layer inspection + Arrow read path |
| PyArrow | optional write requirement | keep optional; Arrow I/O acceleration when installed |
| Pydantic | direct row-level spatial models | keep |
| empirical-data-contracts | provenance/grain/geography/run contracts | keep unchanged |
| contextily/xyzservices | optional presentation | keep isolated from analytical core |

## GeoPandas

### What it already does well

GeoPandas provides:

- CRS-bearing GeometryArrays;
- cached spatial index ownership;
- `to_crs` using cached PyProj transformer construction and vectorized geometry transforms;
- GeoParquet interoperability;
- a public `sindex.query` interface wrapping Shapely STRtree;
- file reading through Pyogrio by default in the modern stack.

The foundation should not replace these with home-grown equivalents.

### Where `sjoin` is too general for our kernels

GeoPandas `sjoin` first obtains positional pairs from `sindex.query`, then performs a generic DataFrame join that must support arbitrary columns, index restoration, suffixes, left/right/inner semantics, and optional attributes.

The foundation relation kernels usually need only:

```text
query position
target position
query ID
target ID
status / overlap facts
```

Therefore the generic frame-join phase is avoidable overhead.

Recommendation: use the public `sindex.query` interface directly while retaining GeoPandas as index owner.

### Do not call private GeoPandas internals

Do not import `_geom_predicate_query`, GeometryArray `_data`, or other underscore APIs. The performance design can reproduce the small public operation with `sindex.query` and public Series/array selection.

## Shapely / GEOS

### Vectorized ufuncs

Shapely 2 exposes NumPy-style array operations for geometry predicates, intersection, area, validity, and many other operations. These are the natural replacement for scalar candidate loops.

Recommendation:

```text
candidate positional arrays
      -> aligned geometry arrays
      -> shapely.intersection(...)
      -> shapely.area(...)
```

### STRtree

Shapely STRtree provides:

- packed immutable R-tree indexing;
- array queries returning pair indices;
- exact predicate filtering inside the query;
- prepared geometry use where possible;
- nearest and `dwithin` queries for later needs.

GeoPandas `sindex` already wraps this closely. Raw STRtree should therefore remain a benchmark alternative, not the default architectural seam.

### MultiPolygon index pathology

Shapely documents that widely spaced parts in a MultiPolygon can produce a large bounding box and reduce STRtree efficiency. This matters for administrative geographies with islands or fragmented units.

Recommendation: add candidate-amplification measurement to benchmarks. Consider an exploded-part index only if actual workloads show a problem.

### Prepared geometries

Do not pre-prepare everything merely because the API exists. STRtree predicate queries already use prepared geometry where possible. Explicit preparation is useful only for a distinct repeated-predicate workload, for example a small fixed polygon set tested many times outside the indexed relation path.

### Multithreading

Shapely releases the GIL around GEOS-heavy functions, so threaded vectorized work can scale. Treat this as a second-order optimization after Python loops are removed.

## PyProj / PROJ

### Current correctness gap

0.1 accepts an arbitrary `area_crs` but names results `overlap_area_m2` and `area_km2`.

A geographic CRS or a projected CRS expressed in feet would make those names false.

### 0.2 invariant

Before any planar area quantity is emitted under metre-based names:

1. parse with `pyproj.CRS.from_user_input`;
2. require `is_projected`;
3. inspect coordinate-system axes;
4. require horizontal axis unit conversion factor to metres to be 1 (within a small numeric tolerance);
5. raise a descriptive `ValueError` otherwise.

Do not manually parse EPSG strings or maintain a whitelist.

### What not to guarantee

A projected metre CRS can still distort area. The invariant guarantees linear units, not universal area accuracy. The default broad-area CRS remains explicit and documented.

## Pyogrio / GDAL

### Current inefficiency

The GADM materializer trial-reads source files/layers with `gpd.read_file`, catches errors, and then inspects loaded columns to infer whether a level matches.

For GeoPackages this can read considerably more data than needed.

### Metadata-first path

Pyogrio provides cheap source inspection:

```text
list_layers(path)
read_info(path, layer=...)
```

`read_info` exposes layer name, fields, CRS, geometry type, feature count when cheap, driver, and capabilities without materializing the complete GeoDataFrame.

Recommendation:

1. inspect candidate layer metadata;
2. identify the layer whose fields contain the requested GADM identifiers;
3. read only that layer;
4. request only required attributes + geometry.

### Arrow transfer

With PyArrow installed, Pyogrio can use GDAL's Arrow stream interface (`use_arrow=True`) for a faster transfer to Python.

The materializer already requires PyArrow for GeoParquet publication. Therefore the I/O path can opportunistically enable Arrow without adding another runtime dependency to that workflow.

### Filtering and future scaling

Pyogrio supports `bbox`, `mask`, `where`, row limits, and direct bound reading. These are useful for future regional or partitioned ingestion but should not be exposed in the 0.2 public API absent a real consumer.

### Streaming

Pyogrio can expose Arrow record batches. Do not build a streaming materializer in 0.2. It becomes relevant only if actual source files exceed acceptable memory for bulk GeoDataFrame normalization.

## GeoParquet / PyArrow

### Current choice

Full analytical geography in GeoParquet is appropriate.

### Covering bbox

Modern GeoPandas can write a covering bbox column and later filter `read_parquet(..., bbox=...)`. This can be valuable for large downstream regional reads.

However writing the bbox column has a cost and the feature is not needed by current consumers. Keep it as an evaluated future optimization rather than changing the canonical output immediately.

### GeoArrow encoding

Native GeoArrow geometry encoding can reduce conversion overhead in some ecosystems but has weaker interoperability than canonical WKB today. Keep WKB as the persisted default in this sprint.

## pandas / NumPy

### Current mismatch

The package directly imports pandas while `pyproject.toml` relies on GeoPandas to install it transitively.

After the optimized kernels, NumPy will also become a direct implementation dependency.

Recommendation: declare direct dependencies when production code imports them. This makes the package architecture and compatibility surface honest even if the same packages would be installed transitively.

### Avoid DataFrame work in the geometry hot path

Use pandas after geometry computation, not as the mechanism for geometry candidate discovery. Positional NumPy arrays are the more natural bridge from STRtree to Shapely vectorized calls.

## Pydantic / empirical-data-contracts

No consolidation is recommended.

`empirical-data-contracts` owns portable empirical contracts:

- `SourceSnapshotRef`;
- `DatasetRef`;
- `GeographySpec`;
- `PeriodScheme`;
- `RunManifest`;
- QA/grain/coverage models.

`spatial-data-foundation` owns spatial row semantics and computation.

The apparent overlap between `GeographySpec` and `GeographyUnit` is intentional:

```text
GeographySpec
    dataset-level geography scheme identity

GeographyUnit
    one native spatial unit row
```

Do not merge them.

## Installed-distribution provenance

### Current bug

`materialize_gadm` currently falls back to `git rev-parse HEAD` and raises when Git metadata is unavailable.

That conflicts with normal PyPI wheel use.

### Correct rule

```text
source checkout
    package_version = installed/local distribution version
    code_commit = Git SHA when resolvable

installed wheel
    package_version = wheel version
    code_commit = None unless caller explicitly provides one
```

The existing `RunManifest` already permits `code_commit=None`.

### Runtime stack evidence

Add runtime library/native versions to manifest parameters rather than changing the upstream contract schema.

This keeps `empirical-data-contracts` generic while preserving useful forensic data for spatial rebuilds.

## Dependency-floor recommendation

0.1 declares a much older GeoPandas floor than the stack being actively tested and designed against.

For 0.2, prefer a deliberate modern floor rather than accidental compatibility with untested 2023-era combinations.

Provisional target, to be confirmed by a minimum-dependency CI install before merge:

```text
Python >= 3.10
GeoPandas >= 1.1
Shapely >= 2.1
PyProj >= 3.7
pandas >= 2.2
NumPy >= 1.24
Pyogrio >= 0.8
Pydantic >= 2.7,<3
empirical-data-contracts >= 0.1,<0.2
```

Do not raise a floor merely because a newer release exists. Each floor should correspond to an API actually used by the 0.2 implementation.

## Optional-extra cleanup

Current extras include capabilities with no implementation surface.

Target after 0.2 audit:

```toml
io = ["pyarrow>=..."]
presentation = ["matplotlib", "contextily", "xyzservices"]
dev = [...]
```

Remove until needed:

```text
duckdb from io
raster extra
cli extra
```

This does not reject DuckDB, Rasterio, or Typer forever. It removes metadata promises until an owned feature consumes them.

## External capabilities explicitly deferred

### DuckDB spatial

Potentially useful for analytical querying of large persisted spatial tables, but unnecessary for the current in-memory foundation kernels and not a reason to retain an unused extra.

### Rasterio / raster engines

Will deserve a dedicated design when GHSL or another raster/grid consumer enters the foundation. Raster work should use raster-native algorithms rather than converting every cell to vector polygons.

### Distributed geospatial engines

Dask-GeoPandas, Spark/Sedona, PostGIS, and similar systems can be appropriate at much larger scales. They are not justified for the current reusable Python package and would violate the package's small deterministic scope.

## Integration decisions

### Adopt in 0.2

- public GeoPandas `sindex.query` for compact candidate pairs;
- Shapely vectorized intersection/area;
- PyProj metric-CRS validation;
- Pyogrio metadata-first layer selection;
- Pyogrio Arrow transfer when I/O extra is present;
- explicit NumPy/pandas/Pyogrio direct dependencies if imported;
- runtime native-stack version provenance.

### Benchmark before adopting

- raw Shapely STRtree instead of GeoPandas sindex;
- candidate-only reprojection;
- exploded MultiPolygon index;
- chunked candidate querying;
- multithreaded exact geometry work;
- GeoParquet covering bbox.

### Reject for this sprint

- custom R-tree;
- custom projection math;
- automatic geometry repair;
- precision snapping as hidden optimization;
- generic distributed executor;
- speculative raster/CLI/query layers.

## Primary references

- GeoPandas source / spatial join architecture: https://github.com/geopandas/geopandas/blob/v1.1.1/geopandas/tools/sjoin.py
- GeoPandas spatial index: https://geopandas.org/en/stable/docs/user_guide/spatial_indexing.html
- Shapely STRtree: https://shapely.readthedocs.io/en/stable/strtree.html
- Shapely prepared geometry: https://shapely.readthedocs.io/en/stable/reference/shapely.prepare.html
- PyProj coordinate systems: https://pyproj4.github.io/pyproj/stable/api/crs/coordinate_system.html
- Pyogrio introduction/API: https://pyogrio.readthedocs.io/en/latest/introduction.html
- GeoPandas GeoParquet API: https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoDataFrame.to_parquet.html
