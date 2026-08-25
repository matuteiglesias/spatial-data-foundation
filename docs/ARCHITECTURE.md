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

## Cross-repository areal relation boundary

`relate_areal_objects(...)` exposes geometric candidate facts for polygonal source objects. It accepts an explicit metric CRS and positive-area threshold, then returns one row per retained object/geography relation with intersection area and the share of the source object's area. Legitimate many-to-many relations remain many-to-many.

The foundation does **not** turn those facts into a domain assignment. For example:

```text
FOUNDATION
----------
A overlaps X: 40 m²
A overlaps Y: 60 m²

DOMAIN PRODUCER
---------------
minimum winner share = 0.50
tie tolerance = declared by the producer
therefore A -> Y
```

Largest-overlap selection, minimum-winner thresholds, tie handling, duplicate-source policy, geometry-repair acceptance, population allocation, exposure allocation, and comparable substantive rules remain consumer responsibilities.

Areal-relation row order is not a public semantic contract. Consumers that need deterministic serialized output must sort by their declared identifiers before serialization or comparison.

The foundational layer should therefore answer questions such as "which analytical polygons does this source object positively overlap, by how much?" A domain producer should answer questions such as "given those candidates and this declared methodology, which administrative or electoral unit owns this record?"

## Next-version engineering program

The 0.2 design keeps these semantic boundaries and changes how the foundation delegates work to the modern geospatial stack. The implementation program is documented as a reviewable bundle:

- [`NEXT_VERSION_ARCHITECTURE.md`](NEXT_VERSION_ARCHITECTURE.md) — target ownership and execution architecture;
- [`PERFORMANCE_ENGINEERING.md`](PERFORMANCE_ENGINEERING.md) — spatial-index/vectorization benchmark and optimization rules;
- [`STACK_INTEGRATION_AUDIT.md`](STACK_INTEGRATION_AUDIT.md) — GeoPandas/Shapely/PyProj/Pyogrio/PyArrow integration audit;
- [`BUILD_PACK_B.md`](BUILD_PACK_B.md) — ordered 0.2 implementation waves and stop rules;
- [`AGENT_EXECUTION_PACK_B.md`](AGENT_EXECUTION_PACK_B.md) — bounded jobs for autonomous implementation agents.

ADRs 0005 and 0006 record the low-level relation-kernel and installed-provenance/metric-area decisions.
