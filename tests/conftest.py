import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import geopandas as gpd
import pytest
from shapely.geometry import Polygon


@pytest.fixture
def synthetic_gadm_level2():
    return gpd.GeoDataFrame(
        {
            "GID_0": ["AAA", "AAA"],
            "GID_1": ["AAA.1_1", None],
            "GID_2": ["AAA.1.1_1", "AAA.2.1_1"],
        },
        geometry=[
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            Polygon([(1, 0), (2, 0), (2, 1), (1, 1)]),
        ],
        crs="EPSG:4326",
    )
