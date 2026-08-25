import json
from pathlib import Path

import geopandas as gpd
import pyogrio
import pytest
from shapely.geometry import Polygon

import spatial_foundation.geography._gadm_io as gadm_io
from spatial_foundation.catalog import register_external_snapshot
from spatial_foundation.geography import materialize_gadm


def _square(x0: float) -> Polygon:
    return Polygon([(x0, 0), (x0 + 1, 0), (x0 + 1, 1), (x0, 1)])


def _write_geojson(path: Path, properties: dict[str, str]) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": properties,
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_multilevel_gpkg(path: Path) -> None:
    adm0 = gpd.GeoDataFrame(
        {"GID_0": ["AAA"], "unused_name": ["country"]},
        geometry=[_square(0)],
        crs="EPSG:4326",
    )
    adm1 = gpd.GeoDataFrame(
        {
            "GID_0": ["AAA"],
            "GID_1": ["AAA.1_1"],
            "unused_name": ["province"],
        },
        geometry=[_square(0)],
        crs="EPSG:4326",
    )
    pyogrio.write_dataframe(adm0, path, layer="ADM_ADM_0", driver="GPKG")
    pyogrio.write_dataframe(adm1, path, layer="ADM_ADM_1", driver="GPKG")


def test_vector_reader_inspects_level_projects_columns_and_uses_arrow(monkeypatch, tmp_path):
    pytest.importorskip("pyarrow")
    source = tmp_path / "adm1.geojson"
    _write_geojson(
        source,
        {"GID_0": "AAA", "GID_1": "AAA.1_1", "unused_name": "province"},
    )

    calls = []
    original = gadm_io.pyogrio.read_dataframe

    def recording_read(*args, **kwargs):
        calls.append(kwargs.copy())
        return original(*args, **kwargs)

    monkeypatch.setattr(gadm_io.pyogrio, "read_dataframe", recording_read)
    parts = gadm_io.read_gadm_level_parts([source], 1, use_arrow=True)

    assert len(parts) == 1
    assert set(parts[0].columns) == {"GID_0", "GID_1", "geometry"}
    assert calls == [
        {
            "layer": calls[0]["layer"],
            "columns": ["GID_0", "GID_1"],
            "use_arrow": True,
        }
    ]


def test_vector_reader_supports_non_arrow_transfer_for_internal_parity(tmp_path):
    source = tmp_path / "adm0.geojson"
    _write_geojson(source, {"GID_0": "AAA", "unused_name": "country"})

    parts = gadm_io.read_gadm_level_parts([source], 0, use_arrow=False)

    assert len(parts) == 1
    assert parts[0]["GID_0"].tolist() == ["AAA"]
    assert "unused_name" not in parts[0].columns


def test_multilayer_geopackage_selects_requested_levels_before_loading(tmp_path):
    pytest.importorskip("pyarrow")
    source = tmp_path / "gadm.gpkg"
    _write_multilevel_gpkg(source)
    snapshot = register_external_snapshot("gadm", "4.1", [source])

    result = materialize_gadm(
        snapshot=snapshot,
        levels=[0, 1],
        output_root=tmp_path / "assets",
        code_commit="c" * 40,
        run_id="gpkg-run",
    )

    adm0 = gpd.read_parquet(result.outputs[0])
    adm1 = gpd.read_parquet(result.outputs[1])
    assert adm0["source_geo_id"].tolist() == ["AAA"]
    assert adm1["source_geo_id"].tolist() == ["AAA.1_1"]
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["parameters"]["source_io"] == {
        "vector_backend": "pyogrio",
        "vector_use_arrow": True,
        "column_projection": True,
    }


def test_malformed_requested_level_fails_before_full_read(monkeypatch, tmp_path):
    source = tmp_path / "malformed.geojson"
    _write_geojson(source, {"GID_1": "AAA.1_1"})

    def forbidden_read(*args, **kwargs):
        raise AssertionError("full read must not occur for malformed level metadata")

    monkeypatch.setattr(gadm_io.pyogrio, "read_dataframe", forbidden_read)
    with pytest.raises(ValueError, match="missing required identity fields"):
        gadm_io.read_gadm_level_parts([source], 1, use_arrow=True)


def test_missing_requested_level_fails_without_partial_publication(tmp_path):
    pytest.importorskip("pyarrow")
    source = tmp_path / "adm0.geojson"
    _write_geojson(source, {"GID_0": "AAA"})
    snapshot = register_external_snapshot("gadm", "4.1", [source])
    output_root = tmp_path / "assets"

    with pytest.raises(ValueError, match="contains no readable ADM1 layer"):
        materialize_gadm(
            snapshot=snapshot,
            levels=[1],
            output_root=output_root,
            code_commit="d" * 40,
            run_id="missing-level",
        )

    assert not (output_root / "silver/geography/gadm/4.1/adm1.geoparquet").exists()
    manifest = json.loads(
        (output_root / "runs/spatial-data-foundation/missing-level/run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["outputs"] == []
    assert manifest["qa"][0]["state"] == "RED"
