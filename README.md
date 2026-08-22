# spatial-data-foundation

Reusable spatial/time infrastructure for research systems.

This repository owns geography authority, period indexing, source registration, auditable spatial membership, and materialization provenance. It does not own FCV treatments, outcomes, matching, survey harmonization, or regressions.

Initial provider: GADM. Initial clients in the next build pack: GHSL and ACLED.

## Operational GADM materialization

After registering local GADM files as an immutable source snapshot, install the IO extra and materialize the native levels needed by downstream work:

```python
from spatial_foundation import materialize_gadm

materialize_gadm(
    snapshot=gadm_4_1_snapshot,
    levels=[0, 1, 2, 3],
    output_root=data_root,
)
```

This publishes full-geometry GeoParquet under `silver/geography/gadm/<version>/` and writes `run_manifest.json` plus `geography_qa.json` under the run directory. Registered source hashes are rechecked before publication; source drift produces a RED run instead of silently accepting changed bytes.
