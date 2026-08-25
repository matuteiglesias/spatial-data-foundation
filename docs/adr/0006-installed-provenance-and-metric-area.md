# ADR 0006 — Installed provenance and metric area correctness

## Status

Accepted for Build Pack B design.

## Context

`spatial-data-foundation` is now a normal installable distribution. A wheel may have no Git checkout, while `RunManifest.code_commit` is already optional. Separately, 0.1 accepts arbitrary `area_crs` values while emitting fields named in square metres / square kilometres.

## Decision

### Installed provenance

A materialization may proceed when Git metadata is unavailable.

Resolution priority:

```text
explicit code_commit
environment override
resolvable source-checkout Git SHA
None
```

Package version and input/output hashes remain mandatory provenance. Runtime spatial-library/native-library versions are recorded under run parameters.

### Metric area

Any operation emitting `_m2` or `_km2` quantities must validate the declared area CRS with PyProj.

The CRS must:

- be projected;
- have horizontal axes whose linear unit converts to metres with factor 1.

This validates unit correctness, not universal projection accuracy. A projected metre CRS such as EPSG:3857 passes the unit rule even though it is not an equal-area projection. Callers remain responsible for selecting an appropriate projected CRS for their scientific purpose; broad-area defaults remain explicit.

## Consequences

- PyPI-installed materialization no longer depends on repository layout;
- `code_commit=None` is valid rather than a provenance failure;
- area columns cannot silently contain square degrees or square feet;
- PyProj becomes an intentional direct correctness dependency;
- no projection whitelist or custom projection math is maintained locally.
