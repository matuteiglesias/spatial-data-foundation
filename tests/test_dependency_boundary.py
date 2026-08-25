from importlib import metadata

from packaging.requirements import Requirement


def test_distribution_declares_direct_runtime_dependencies_and_only_owned_extras():
    dist = metadata.distribution("spatial-data-foundation")
    requirements = [Requirement(value) for value in dist.requires or ()]
    direct = {requirement.name for requirement in requirements if requirement.marker is None}

    assert direct == {
        "empirical-data-contracts",
        "numpy",
        "pandas",
        "geopandas",
        "shapely",
        "pyproj",
        "pyogrio",
        "pydantic",
    }
    assert set(dist.metadata.get_all("Provides-Extra") or ()) == {
        "dev",
        "io",
        "presentation",
    }
