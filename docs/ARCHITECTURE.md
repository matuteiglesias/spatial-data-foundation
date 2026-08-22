# Spatial Data Foundation Architecture

## Public responsibilities

1. Register immutable source snapshots or references.
2. Normalize authoritative geography providers.
3. Expose version-safe geography identity and hierarchy.
4. Generate shared period dimensions.
5. Assign spatial objects to geography with auditable ambiguity.
6. Emit provenance and QA required by downstream empirical systems.

## Non-responsibilities

This package does not decide which area is treated, whether a missing ACLED row is zero, which aid source is preferable, how survey questions are harmonized, or which regression should run.

## Geography model

A native polygon has a version-safe UID:

```text
provider:version:adm<level>:source_geo_id
```

A research geography scheme (for example FCV adaptive l2) is a *membership/configuration over native polygons*. It should not mutate GADM identity.

## Geometry policy

- Source / analytical geometry: full precision, normalized to EPSG:4326 for storage.
- Metric calculations: explicit projected/equal-area CRS recorded in run parameters.
- Display geometry: optional simplified derivative with an explicit `geometry_role=display`.
- Scientific joins and raster zonal statistics use analytical geometry unless a measurement contract explicitly says otherwise.

## Spatial membership policy

The foundational assignment returns candidate relationships. Exact boundary/multiple candidates remain ambiguous. Source-specific consumers may choose a declared resolution policy, but the raw assignment audit remains available.

Future extensions can add uncertainty envelopes (DHS displacement, low-precision project geocodes, Afrobarometer location precision) without changing the core point/polygon identity model.
