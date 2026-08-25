from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd

from .runner import profile_areal_workload, profile_point_workload, run_suite, runtime_versions
from .workloads import ArealWorkload, PRESET_WIDTHS, PointWorkload


def _read_frame(path: Path) -> gpd.GeoDataFrame:
    if path.suffix.lower() in {".parquet", ".geoparquet"}:
        return gpd.read_parquet(path)
    return gpd.read_file(path)


def _local_payload(args: argparse.Namespace) -> dict:
    if args.objects is None or args.polygons is None or args.kind is None:
        raise SystemExit("local benchmarking requires --objects, --polygons, and --kind")

    objects = _read_frame(args.objects)
    polygons = _read_frame(args.polygons)
    if args.polygon_id_col not in polygons.columns:
        raise SystemExit(f"missing polygon id column: {args.polygon_id_col}")
    polygons = polygons.rename(columns={args.polygon_id_col: "geo_uid"})

    if args.kind == "point":
        if args.object_id_col not in objects.columns:
            raise SystemExit(f"missing point id column: {args.object_id_col}")
        points = objects.rename(columns={args.object_id_col: "point_id"})
        result = profile_point_workload(
            PointWorkload(name="point_local", points=points, polygons=polygons)
        )
    else:
        if args.object_id_col not in objects.columns:
            raise SystemExit(f"missing object id column: {args.object_id_col}")
        areal_objects = objects.rename(columns={args.object_id_col: "object_id"})
        result = profile_areal_workload(
            ArealWorkload(name="areal_local", objects=areal_objects, polygons=polygons),
            area_crs=args.area_crs,
        )

    return {
        "preset": "local",
        "runtime_versions": runtime_versions(),
        "results": [result],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic spatial relation benchmarks")
    parser.add_argument("--preset", choices=tuple(PRESET_WIDTHS), default="small")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--objects", type=Path, help="optional local point/polygon source")
    parser.add_argument("--polygons", type=Path, help="optional local target geography")
    parser.add_argument("--kind", choices=("point", "areal"))
    parser.add_argument("--object-id-col", default="object_id")
    parser.add_argument("--polygon-id-col", default="geo_uid")
    parser.add_argument("--area-crs", default="EPSG:3857")
    args = parser.parse_args()

    payload = (
        _local_payload(args)
        if args.objects is not None or args.polygons is not None or args.kind is not None
        else run_suite(args.preset)
    )
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered, encoding="utf-8")
        print(args.output)


if __name__ == "__main__":
    main()
