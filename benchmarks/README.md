# Spatial relation benchmarks

This directory is development infrastructure for Build Pack B. It is deliberately
outside the public `spatial_foundation` package.

The generated workloads are deterministic, network-free, and cover ordinary and
adversarial relation shapes. Timings are evidence, not CI thresholds: runner,
hardware, native-library, and operating-system differences can move absolute wall
clock measurements substantially.

## Generated suite

```bash
python -m benchmarks.run --preset small --output /tmp/spatial-benchmark.json
python -m benchmarks.run --preset medium
```

Presets scale a deterministic grid width (`small=8`, `medium=32`, `large=128`).
The suite covers point uniform/boundary/outside/dense-overlap cases and areal
tiles/cross-boundary/sliver/outside/sparse-MultiPolygon cases.

Each result records input and candidate cardinality, bounding-box versus exact
predicate candidate amplification, phase timings, public-kernel total time, audit
counts, and Python/native geospatial runtime versions.

The phase timings intentionally expose the seams later optimization work needs to
study:

1. CRS transformation;
2. cached spatial-index bounding-box query;
3. predicate-filtered spatial-index query;
4. scalar exact polygon intersection in the current baseline;
5. compact result assembly;
6. complete public-kernel wall time.

Build Pack B2 may add alternate `KernelAdapter` callables without replacing this
harness.

## Optional local data

No benchmark command downloads data. A caller may point the runner at local vector
or GeoParquet assets:

```bash
python -m benchmarks.run \
  --kind areal \
  --objects /data/radios.geoparquet \
  --polygons /data/departments.geoparquet \
  --object-id-col radio_id \
  --polygon-id-col geo_uid \
  --area-crs EPSG:5348 \
  --output /tmp/local-overlap.json
```

For point data use `--kind point` and supply the point identifier with
`--object-id-col`. Input files remain caller-owned and are never copied or
registered by the benchmark harness.

## Interpretation

Do not infer that a lower-level implementation is better merely because it exists.
GeoPandas' public spatial index is already a cached wrapper around Shapely STRtree.
The primary optimization question is whether avoiding generic DataFrame join
materialization and scalar Python geometry loops produces a meaningful measured
benefit while preserving the public relation semantics.
