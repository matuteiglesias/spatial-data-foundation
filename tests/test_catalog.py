from pathlib import Path

from spatial_foundation.catalog import DataRoot, register_external_snapshot


def test_data_root_paths_are_deterministic(tmp_path):
    root = DataRoot.from_path(tmp_path)
    assert root.silver("geography", "gadm_units", "4.1") == tmp_path / "silver/geography/gadm_units/4.1"
    assert root.run("spatial-foundation", "run-1") == tmp_path / "runs/spatial-foundation/run-1"


def test_external_snapshot_hashes_without_copying(tmp_path):
    p = tmp_path / "raw.txt"
    p.write_text("hello")
    snap = register_external_snapshot("example", "v1", [p])
    assert snap.storage_mode == "external_immutable"
    assert snap.files[0].path == str(p.resolve())
    assert snap.files[0].sha256 == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
