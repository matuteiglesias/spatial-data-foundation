# spatial-data-foundation

Reusable spatial/time infrastructure for research systems.

This repository owns geography authority, period indexing, source registration, auditable spatial relations, and materialization provenance. It does **not** own FCV treatments, outcomes, matching, survey harmonization, regressions, domain assignment policy, or source acquisition.

The current implementation is the completed engineering candidate produced by Build Pack B: the public spatial semantics remain small, while the internals use the modern GeoPandas/Shapely/PyProj/Pyogrio stack deliberately. See [`docs/RELEASE_READINESS_0_2.md`](docs/RELEASE_READINESS_0_2.md) for the evidence and release gates. The package is not published as `0.2.0` until a separate human-approved release step.

## Public spatial contracts

### Point membership

`assign_points(...)` returns candidate memberships without silently resolving ambiguity.

```python
from spatial_foundation import assign_points

result, audit = assign_points(
    points,
    analytical_polygons,
    point_id_col="event_id",
)
```

The supported source geometry family is Point. Interior one-candidate points are `matched_unique`; points with no candidate are `unmatched_outside`; exact-boundary/multiple candidates remain `ambiguous_multiple`; and missing, empty, or invalid Point geometry is `invalid_point`. Unsupported source geometry families fail closed.

Target geography must have a CRS, unique/non-missing IDs, valid non-empty Polygon/MultiPolygon geometry, and analytical geometry role when that role is present.

### Areal relations

`relate_areal_objects(...)` returns positive-area geometric relation facts without assigning ownership.

```python
from spatial_foundation import relate_areal_objects

relations, audit = relate_areal_objects(
    source_polygons,
    analytical_polygons,
    object_id_col="source_id",
    area_crs="EPSG:6933",
)
```

One source object may legitimately relate to multiple target units. The foundation emits `matched_single`, `matched_multiple`, `unmatched_outside`, or `invalid_geometry`, plus `overlap_area_m2` and `overlap_share_of_object`. Boundary-only touches do not become positive-area relations. Winner/tie rules, allocation, exposure, population, or treatment interpretation remain downstream policy.

Any CRS used to produce `_m2` / `_km2` quantities must be projected with metre horizontal axes. This guarantees unit correctness, not universal distortion-free area measurement.

## Relation engine

The implementation intentionally delegates spatial mechanics to mature libraries rather than creating a custom GIS layer:

```text
GeoPandas CRS-aware geometry arrays + cached spatial index
                         |
                         v
              sindex.query positional pairs
                         |
                         v
           Shapely vectorized GEOS operations
                         |
                         v
                NumPy counts / masks
                         |
                         v
                compact pandas results
```

Candidate row order is not a public contract. The benchmark suite protects semantic parity and records candidate amplification and phase timings without turning absolute wall time into a brittle CI threshold.

## Operational GADM materialization

Materialization works from registered immutable **local** source snapshots; it does not download GADM or other source data.

Install the I/O extra and materialize the native levels required by downstream work:

```bash
pip install "spatial-data-foundation[io]"
```

```python
from spatial_foundation import materialize_gadm

materialize_gadm(
    snapshot=gadm_4_1_snapshot,
    levels=[0, 1, 2, 3],
    output_root=data_root,
)
```

Before loading complete geometry, vector sources are inspected through Pyogrio/GDAL to identify requested ADM layers and required identity fields. Reads are column-projected and the PyArrow-backed materialization workflow uses GDAL Arrow transfer where applicable. Separate-level vector files, multi-layer GeoPackages, and GeoParquet sources are supported.

The workflow publishes full analytical geometry as GeoParquet under `silver/geography/gadm/<version>/` and writes `run_manifest.json` plus `geography_qa.json` under the run directory. Registered source hashes are rechecked before interpretation; source drift or malformed requested levels produce a RED run rather than partial silver publication.

Installed wheels are first-class. Git metadata is optional: when no checkout SHA exists, `code_commit` is `null` and the manifest still records installed package version, runtime/native stack versions, source snapshot hashes, output hashes, parameters, and QA.

## Dependency boundary

Core implementation dependencies are declared directly rather than relying on GeoPandas transitively:

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

Optional extras are deliberately limited to capabilities the repository actually owns:

- `io` — PyArrow / GeoParquet materialization support;
- `presentation` — contextual map presentation;
- `dev` — tests, lint, build, and development dependencies.

Raster, DuckDB query, and CLI surfaces are not advertised until owned implementations exist.

## Optional contextual presentation

Presentation helpers are an optional, non-analytical surface. Core imports do not require plotting or tile dependencies:

```bash
pip install "spatial-data-foundation[presentation]"
```

Add contextual imagery beneath an existing analytical plot:

```python
from spatial_foundation.presentation import add_basemap

ax = gdf.plot(column="value", alpha=0.65)
add_basemap(ax, crs=gdf.crs, kind="imagery", alpha=0.55)
```

Or use the compact GeoDataFrame helper:

```python
from spatial_foundation.presentation import plot_context

ax = plot_context(
    gdf,
    basemap="neutral",
    column="value",
)
```

The governed convenience aliases are `neutral`, `imagery`, and `terrain`. A concrete tile source or local raster path can also be supplied. Local rasters allow reproducible/offline presentation; web providers may perform network requests only when explicitly selected by the caller.

Presentation never changes analytical geometry, membership, identifiers, or domain interpretation. Provider attribution remains enabled, and no provider credentials are bundled with this package.

## Scope discipline

The foundation deliberately does not contain:

- treatment/control/exposure semantics;
- census/electoral winner or crosswalk policy;
- automatic provider downloads;
- generic geometry repair or precision policy;
- public STRtree/cache classes;
- distributed orchestration;
- speculative raster, query, or CLI frameworks.

New primitives should enter this package only when they are reusable geometric/spatiotemporal mechanics with a concrete consumer, not merely because a GIS library makes them possible.
