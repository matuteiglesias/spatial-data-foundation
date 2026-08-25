# Agent Instructions — spatial-data-foundation

## Product intent

Build a reusable spatial substrate that can serve FCV and unrelated research. Prefer a small, deterministic public API over many convenience functions.

## Invariants

- analytical geometry is authoritative; display simplification is a separate derivative;
- never infer source coverage from row presence;
- never convert missing rows to zero;
- geography identity is provider/version/source-id aware;
- period logic is centralized;
- point assignment reports ambiguity rather than silently resolving it;
- every real materialization must be attributable to a source snapshot and run manifest;
- specific FCV l1/l2/l3 mappings belong in FCV configuration, not this package;
- presentation helpers never mutate analytical geometry, membership, identifiers, or domain interpretation;
- core imports must not require optional presentation dependencies;
- live basemap access is explicit caller behavior; tests and core spatial execution remain network-free;
- no notebooks in production code.

## Do not add

- treatment/control concepts;
- regression/matching dependencies;
- ACLED/DHS/AFB-specific fields to core geography schemas;
- automatic network downloads in core spatial workflows;
- provider credentials or secrets;
- domain assignment/tie-break policy inside generic spatial relations;
- orchestration frameworks;
- global mutable configuration.

## Development style

Implement the smallest API satisfying current tests. When a future feature can be represented as data/configuration instead of another subclass, prefer data/configuration.
