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

The governed convenience aliases are `neutral`, `imagery`, and `terrain`. A concrete tile source or local raster path can also be supplied. Local rasters allow reproducible/offline presentation; web providers may perform network requests when explicitly selected by the caller.

Presentation never changes analytical geometry, membership, identifiers, or domain interpretation. Provider attribution remains enabled, and no provider credentials are bundled with this package.
