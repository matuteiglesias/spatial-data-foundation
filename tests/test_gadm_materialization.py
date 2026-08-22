import json
from pathlib import Path

import geopandas as gpd
import pytest

from spatial_foundation.catalog import register_external_snapshot, sha256_file
from spatial_foundation.geography import materialize_gadm


pytest.importorskip("pyarrow")


def _write_geojson(path: Path, *, level: int, rows: list[tuple[str, ...]]) -> None:
    features = []
    for index, gids in enumerate(rows):
        properties = {f"GID_{i}": gid for i, gid in enumerate(gids)}
        x0 = float(index * 2)
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [x0, 0.0],
                            [x0 + 1.0, 0.0],
                            [x0 + 1.0, 1.0],
                            [x0, 1.0],
                            [x0, 0.0],
                        ]
                    ],
                },
            }
        )
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )


def _synthetic_snapshot(tmp_path: Path):
    adm0 = tmp_path / "gadm41_SYN_0.geojson"
    adm1 = tmp_path / "gadm41_SYN_1.geojson"
    _write_geojson(adm0, level=0, rows=[("AAA",), ("BBB",)])
    _write_geojson(adm1, level=1, rows=[("AAA", "AAA.1_1"), ("BBB", "BBB.1_1")])
    return register_external_snapshot("gadm", "4.1", [adm0, adm1]), adm0, adm1


def test_materialize_gadm_publishes_geoparquet_manifest_and_qa(tmp_path):
    snapshot, _, _ = _synthetic_snapshot(tmp_path)
    output_root = tmp_path / "asset-root"
    code_commit = "a" * 40

    result = materialize_gadm(
        snapshot=snapshot,
        levels=[0, 1],
        output_root=output_root,
        area_crs="EPSG:6933",
        code_commit=code_commit,
        run_id="acceptance-run",
    )

    adm0_path = output_root / "silver/geography/gadm/4.1/adm0.geoparquet"
    adm1_path = output_root / "silver/geography/gadm/4.1/adm1.geoparquet"
    run_root = output_root / "runs/spatial-data-foundation/acceptance-run"
    assert result.outputs == {0: adm0_path, 1: adm1_path}
    assert result.manifest_path == run_root / "run_manifest.json"
    assert result.qa_path == run_root / "geography_qa.json"
    assert adm0_path.exists()
    assert adm1_path.exists()

    adm1 = gpd.read_parquet(adm1_path)
    assert adm1.crs.to_string() == "EPSG:4326"
    assert set(adm1["geo_uid"]) == {
        "gadm:4.1:adm1:AAA.1_1",
        "gadm:4.1:adm1:BBB.1_1",
    }
    assert set(adm1["parent_geo_uid"]) == {
        "gadm:4.1:adm0:AAA",
        "gadm:4.1:adm0:BBB",
    }

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == "acceptance-run"
    assert manifest["package"] == "spatial-data-foundation"
    assert manifest["code_commit"] == code_commit
    assert manifest["parameters"]["area_crs"] == "EPSG:6933"
    assert manifest["parameters"]["available_levels"] == [0, 1]
    assert manifest["inputs"][0]["snapshot_id"] == snapshot.snapshot_id
    assert {f["sha256"] for f in manifest["inputs"][0]["files"]} == {
        ref.sha256 for ref in snapshot.files
    }
    assert {output["content_sha256"] for output in manifest["outputs"]} == {
        sha256_file(adm0_path),
        sha256_file(adm1_path),
    }

    qa = json.loads(result.qa_path.read_text(encoding="utf-8"))
    assert qa["provider"] == "gadm"
    assert qa["version"] == "4.1"
    assert qa["area_crs"] == "EPSG:6933"
    assert qa["available_levels"] == [0, 1]
    assert qa["levels"]["0"] == {
        "row_count": 2,
        "country_count": 2,
        "null_geometry_count": 0,
        "invalid_geometry_count": 0,
        "duplicate_id_count": 0,
        "output_path": str(adm0_path),
        "output_sha256": sha256_file(adm0_path),
    }
    assert qa["levels"]["1"]["row_count"] == 2
    assert qa["levels"]["1"]["country_count"] == 2
    assert qa["source_snapshot"]["snapshot_id"] == snapshot.snapshot_id


def test_materialize_gadm_rejects_snapshot_drift_and_leaves_no_silver_output(tmp_path):
    snapshot, adm0, _ = _synthetic_snapshot(tmp_path)
    adm0.write_text(adm0.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    output_root = tmp_path / "asset-root"

    with pytest.raises(ValueError, match="source snapshot hash mismatch"):
        materialize_gadm(
            snapshot=snapshot,
            levels=[0, 1],
            output_root=output_root,
            code_commit="b" * 40,
            run_id="drift-run",
        )

    assert not (output_root / "silver/geography/gadm/4.1/adm0.geoparquet").exists()
    run_root = output_root / "runs/spatial-data-foundation/drift-run"
    manifest = json.loads((run_root / "run_manifest.json").read_text(encoding="utf-8"))
    qa = json.loads((run_root / "geography_qa.json").read_text(encoding="utf-8"))
    assert manifest["qa"][0]["state"] == "RED"
    assert manifest["outputs"] == []
    assert qa["state"] == "RED"
    assert "hash mismatch" in qa["error"]
