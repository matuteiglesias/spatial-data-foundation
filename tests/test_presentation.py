import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pytest
from shapely.geometry import Polygon

import spatial_foundation.presentation.basemaps as basemap_module
import spatial_foundation.presentation.plotting as plotting_module
from spatial_foundation.presentation import add_basemap, plot_context, resolve_basemap


def _square(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_governed_aliases_resolve_to_provider_objects():
    assert resolve_basemap("neutral").name == "CartoDB.Positron"
    assert resolve_basemap("imagery").name == "Esri.WorldImagery"
    assert resolve_basemap("terrain").name == "OpenTopoMap"


def test_add_basemap_forwards_crs_and_preserves_extent_and_attribution(monkeypatch):
    calls = {}

    def fake_add_basemap(ax, **kwargs):
        calls.update(kwargs)
        ax.set_xlim(-100, 100)
        ax.set_ylim(-200, 200)

    monkeypatch.setattr(basemap_module.cx, "add_basemap", fake_add_basemap)
    _, ax = plt.subplots()
    ax.set_xlim(10, 20)
    ax.set_ylim(30, 40)

    returned = add_basemap(
        ax,
        crs="EPSG:4326",
        kind="imagery",
        alpha=0.55,
    )

    assert returned is ax
    assert calls["crs"] == "EPSG:4326"
    assert calls["source"].name == "Esri.WorldImagery"
    assert calls["alpha"] == pytest.approx(0.55)
    assert calls["attribution"] is None
    assert calls["reset_extent"] is True
    assert ax.get_xlim() == pytest.approx((10, 20))
    assert ax.get_ylim() == pytest.approx((30, 40))
    plt.close(ax.figure)


def test_add_basemap_requires_crs_and_refuses_attribution_suppression():
    _, ax = plt.subplots()
    with pytest.raises(ValueError, match="CRS"):
        add_basemap(ax, crs=None)
    with pytest.raises(ValueError, match="attribution"):
        add_basemap(ax, crs="EPSG:3857", attribution=False)
    plt.close(ax.figure)


def test_local_raster_path_is_passed_through_without_network(monkeypatch, tmp_path):
    calls = {}

    def fake_add_basemap(_ax, **kwargs):
        calls.update(kwargs)

    monkeypatch.setattr(basemap_module.cx, "add_basemap", fake_add_basemap)
    _, ax = plt.subplots()
    raster_path = tmp_path / "cached-context.tif"

    add_basemap(ax, crs="EPSG:3857", source=raster_path)

    assert calls["source"] == str(raster_path)
    plt.close(ax.figure)


def test_plot_context_keeps_geodataframe_semantics_outside_presentation(monkeypatch):
    calls = {}

    def fake_add_basemap(ax, **kwargs):
        calls.update(kwargs)
        return ax

    monkeypatch.setattr(plotting_module, "add_basemap", fake_add_basemap)
    gdf = gpd.GeoDataFrame(
        {"value": [1]},
        geometry=[_square(0, 0, 10, 10)],
        crs="EPSG:3857",
    )

    ax = plot_context(
        gdf,
        basemap="imagery",
        basemap_alpha=0.4,
        column="value",
    )

    assert calls["crs"] == gdf.crs
    assert calls["source"] == "imagery"
    assert calls["alpha"] == pytest.approx(0.4)
    assert gdf.geometry.iloc[0].equals(_square(0, 0, 10, 10))
    plt.close(ax.figure)


def test_plot_context_rejects_missing_crs_before_rendering():
    gdf = gpd.GeoDataFrame({"value": [1]}, geometry=[_square(0, 0, 1, 1)])
    with pytest.raises(ValueError, match="requires a CRS"):
        plot_context(gdf, column="value")


def test_core_import_does_not_load_presentation_dependencies(tmp_path):
    code = "import sys; import spatial_foundation; assert 'contextily' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], cwd=tmp_path, check=True)


def test_missing_presentation_extra_has_actionable_import_hint(tmp_path):
    code = r'''
import sys

class BlockContextily:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "contextily" or fullname.startswith("contextily."):
            raise ModuleNotFoundError("blocked contextily for presentation-extra test")
        return None

sys.meta_path.insert(0, BlockContextily())
try:
    import spatial_foundation.presentation  # noqa: F401
except ModuleNotFoundError as exc:
    assert "spatial-data-foundation[presentation]" in str(exc), str(exc)
else:
    raise AssertionError("presentation import unexpectedly succeeded without contextily")
'''
    subprocess.run([sys.executable, "-c", code], cwd=tmp_path, check=True)


def test_concrete_string_source_is_not_rewritten():
    source = "https://tiles.example.test/{z}/{x}/{y}.png"
    assert resolve_basemap(source) == source
    assert resolve_basemap(Path("local.tif")) == "local.tif"
