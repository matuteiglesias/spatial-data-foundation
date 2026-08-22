# Build Pack A — Developer Specification

## Deliverable A0: contracts

See sibling `empirical-data-contracts` seed. Freeze API only after its tests and serialization formats are accepted.

## Deliverable A1: source registration + data root + time

Required behavior:

- no source copy required;
- SHA-256 for registered files;
- deterministic medallion paths;
- period indexing reproduces T2_y2001 legacy boundaries;
- same implementation supports T3/T4 and alternate anchors.

## Deliverable A2: GADM provider

Input: caller-supplied GeoDataFrame or explicit local source path in later adapter.

Output native schema:

```text
geo_uid
provider
version
source_geo_id
country_iso3
native_admin_level
parent_geo_uid
area_km2
geometry_role
geometry
```

Required gates:

- CRS declared;
- unique geo_uid;
- country identity resolvable;
- parent identity present when source provides it;
- geometry non-null/valid profile reported;
- area calculation CRS declared in run parameters.

Do not implement FCV adaptive mappings here. Instead design a later `CompositeGeographyScheme` that consumes a configuration mapping country → native admin level.

## Deliverable A3: point assignment

Return candidate memberships plus point-level status:

```text
matched_unique
unmatched_outside
ambiguous_multiple
invalid_point   # reserved/next implementation step
```

Do not silently pick one side of an administrative boundary. The consumer may supply a future resolution policy.

## Deliverable A4: operational GADM acceptance

Bridge normalized GADM frames to reusable empirical assets without adding network acquisition.

```python
materialize_gadm(
    snapshot=gadm_4_1_snapshot,
    levels=[0, 1, 2, 3],
    output_root=data_root,
)
```

Expected publication:

```text
silver/geography/gadm/4.1/
    adm0.geoparquet
    adm1.geoparquet
    adm2.geoparquet
    adm3.geoparquet

runs/spatial-data-foundation/<run_id>/
    run_manifest.json
    geography_qa.json
```

Required behavior:

- revalidate registered source hashes before reading;
- support registered separate level files and standard GADM 4.x GeoPackages with `ADM_ADM_<level>` layers;
- use `normalize_gadm_frame()` and preserve full analytical geometry;
- calculate area with the declared `area_crs`;
- stage every requested level before publishing final silver paths;
- refuse silent overwrite of an existing versioned asset;
- record source snapshot hashes, GADM version, code commit, area CRS, available levels, output paths and output hashes;
- report row count, country count, null geometry count, invalid geometry count, and duplicate ID count per level;
- persist provenance through the shared `RunManifest` / `DatasetRef` / `QAResult` contracts rather than relying on in-memory `GeoDataFrame.attrs`;
- on source drift or materialization failure, emit a RED run/QA record and do not publish staged outputs.

GeoParquet IO requires the package `io` extra.

## Stop rule

Build Pack A ends once GADM/time/membership infrastructure is stable, materially persisted, and tested. Do not add GHSL or ACLED until this boundary can be reviewed in isolation.
