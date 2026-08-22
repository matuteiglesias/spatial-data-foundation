from pathlib import Path

from spatial_foundation.catalog import DataRoot, register_external_snapshot


def test_data_root_paths_are_deterministic(tmp_path):
    root = DataRoot.from_path(tmp_path)
    assert root.bronze("gadm", "4.1", "snap") == tmp_path / "bronze/gadm/4.1/snap"
    assert root.silver("geography", "gadm_units", "4.1") == tmp_path / "silver/geography/gadm_units/4.1"
    assert root.gold("geography", "gadm_units", "4.1") == tmp_path / "gold/geography/gadm_units/4.1"
    assert root.run("spatial-foundation", "run-1") == tmp_path / "runs/spatial-foundation/run-1"


def test_external_snapshot_hashes_without_copying(tmp_path):
    p = tmp_path / "raw.txt"
    p.write_text("hello")
    snap = register_external_snapshot("example", "v1", [p])
    assert snap.storage_mode == "external_immutable"
    assert snap.files[0].path == str(p.resolve())
    assert snap.files[0].sha256 == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_snapshot_identity_is_independent_of_input_path_order(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("alpha")
    b.write_text("beta")
    forward = register_external_snapshot("example", "v1", [a, b])
    reverse = register_external_snapshot("example", "v1", [b, a])
    assert forward.snapshot_id == reverse.snapshot_id
    assert [ref.path for ref in forward.files] == sorted(ref.path for ref in forward.files)
