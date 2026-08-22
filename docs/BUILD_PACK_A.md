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

## Stop rule

Build Pack A ends once GADM/time/membership infrastructure is stable and tested. Do not add GHSL or ACLED until this boundary can be reviewed in isolation.
