from __future__ import annotations

import platform
from importlib import metadata

_PACKAGE_NAMES = (
    "spatial-data-foundation",
    "empirical-data-contracts",
    "geopandas",
    "pandas",
    "numpy",
    "shapely",
    "pyproj",
    "pyogrio",
    "pyarrow",
)


def runtime_versions() -> dict[str, str]:
    """Return installed Python/geospatial runtime versions for provenance."""
    versions = {"python": platform.python_version()}
    for name in _PACKAGE_NAMES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not-installed"

    try:
        import shapely

        versions["GEOS"] = shapely.geos_version_string
    except (ImportError, AttributeError):
        pass

    try:
        import pyproj

        versions["PROJ"] = pyproj.proj_version_str
    except (ImportError, AttributeError):
        pass

    try:
        import pyogrio

        versions["GDAL"] = ".".join(str(part) for part in pyogrio.__gdal_version__)
    except (ImportError, AttributeError):
        pass

    return versions
