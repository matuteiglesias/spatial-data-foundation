import os
import shutil
import subprocess
import sys
import sysconfig
import venv
from pathlib import Path

import pytest


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _build_wheel(repo_root: Path, tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    for filename in ("pyproject.toml", "README.md"):
        shutil.copy2(repo_root / filename, project_root / filename)
    shutil.copytree(repo_root / "src", project_root / "src")

    dist_dir = project_root / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
        cwd=project_root,
        check=True,
    )
    wheels = list(dist_dir.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def _create_clean_venv(path: Path) -> Path:
    venv.EnvBuilder(with_pip=True).create(path)
    return _venv_python(path)


def test_built_wheel_supports_clean_core_and_presentation_consumers(tmp_path):
    if os.environ.get("SPATIAL_FOUNDATION_FULL_DISTRIBUTION") != "1":
        pytest.skip("full clean-wheel installs run once in the dedicated CI distribution job")

    repo_root = Path(__file__).resolve().parents[1]
    wheel = _build_wheel(repo_root, tmp_path)

    core_python = _create_clean_venv(tmp_path / "core-venv")
    subprocess.run(
        [str(core_python), "-m", "pip", "install", str(wheel)],
        cwd=tmp_path,
        check=True,
    )
    core_verification = f"""
from pathlib import Path
import sys
import sysconfig

import geopandas as gpd
from shapely.geometry import Polygon
import spatial_foundation as sf

assert "contextily" not in sys.modules
package_path = Path(sf.__file__).resolve()
purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
assert package_path.is_relative_to(purelib), (package_path, purelib)

polygons = gpd.GeoDataFrame(
    {{"geo_uid": ["A"], "geometry_role": ["analytical"]}},
    geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])],
    crs="EPSG:3857",
)
objects = gpd.GeoDataFrame(
    {{"object_id": ["o1"]}},
    geometry=[Polygon([(1, 1), (2, 1), (2, 2), (1, 2)])],
    crs="EPSG:3857",
)
result, audit = sf.relate_areal_objects(
    objects,
    polygons,
    object_id_col="object_id",
    area_crs="EPSG:3857",
)
assert result.loc[0, "geo_uid"] == "A"
assert audit.matched_single == 1
"""
    subprocess.run([str(core_python), "-c", core_verification], cwd=tmp_path, check=True)

    presentation_python = _create_clean_venv(tmp_path / "presentation-venv")
    presentation_requirement = f"{wheel}[presentation]"
    subprocess.run(
        [str(presentation_python), "-m", "pip", "install", presentation_requirement],
        cwd=tmp_path,
        check=True,
    )
    presentation_verification = """
from pathlib import Path
import sysconfig

import spatial_foundation.presentation as presentation

package_path = Path(presentation.__file__).resolve()
purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
assert package_path.is_relative_to(purelib), (package_path, purelib)
assert presentation.resolve_basemap("neutral").name == "CartoDB.Positron"
assert presentation.resolve_basemap("imagery").name == "Esri.WorldImagery"
assert presentation.resolve_basemap("terrain").name == "OpenTopoMap"
"""
    subprocess.run(
        [str(presentation_python), "-c", presentation_verification],
        cwd=tmp_path,
        check=True,
    )
