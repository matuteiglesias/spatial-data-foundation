from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from empirical_contracts import SourceFileRef, SourceSnapshotRef


@dataclass(frozen=True)
class DataRoot:
    root: Path

    @classmethod
    def from_path(cls, value: str | Path) -> DataRoot:
        return cls(Path(value).expanduser().resolve())

    def bronze(self, source: str, release: str, snapshot_id: str) -> Path:
        return self.root / "bronze" / source / release / snapshot_id

    def silver(self, domain: str, dataset: str, version: str) -> Path:
        return self.root / "silver" / domain / dataset / version

    def gold(self, domain: str, dataset: str, version: str) -> Path:
        return self.root / "gold" / domain / dataset / version

    def run(self, package: str, run_id: str) -> Path:
        return self.root / "runs" / package / run_id


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def register_external_snapshot(source: str, release: str, paths: list[str | Path]) -> SourceSnapshotRef:
    resolved_paths = sorted(Path(raw).expanduser().resolve() for raw in paths)
    refs = []
    for path in resolved_paths:
        stat = path.stat()
        refs.append(SourceFileRef(path=str(path), sha256=sha256_file(path), size_bytes=stat.st_size))
    short = sha256("".join(ref.sha256 for ref in refs).encode()).hexdigest()[:12]
    return SourceSnapshotRef(
        source=source,
        release=release,
        snapshot_id=f"{source}-{release}-{short}",
        storage_mode="external_immutable",
        files=tuple(refs),
    )
