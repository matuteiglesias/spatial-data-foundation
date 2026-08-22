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
- no notebooks in production code.

## Do not add

- treatment/control concepts;
- regression/matching dependencies;
- ACLED/DHS/AFB-specific fields to core geography schemas;
- automatic network downloads in Build Pack A;
- orchestration frameworks;
- global mutable configuration.

## Development style

Implement the smallest API satisfying current tests. When a future feature can be represented as data/configuration instead of another subclass, prefer data/configuration.
