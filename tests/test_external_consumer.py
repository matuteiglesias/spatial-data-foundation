from importlib.metadata import version

from empirical_contracts import GeographySpec, PeriodScheme
from spatial_foundation import DataRoot, PeriodIndex


def test_external_contracts_consumer_smoke(tmp_path):
    geography = GeographySpec(
        provider="gadm",
        version="4.1",
        scheme="native",
        level="adm1",
    )
    scheme = PeriodScheme(width_years=2, anchor_year=2001)

    period = PeriodIndex(scheme).period_for(2002)
    assert period.period_id == "2001-2002"

    root = DataRoot.from_path(tmp_path)
    assert root.silver("geography", "gadm", geography.version) == (
        tmp_path.resolve() / "silver" / "geography" / "gadm" / "4.1"
    )


def test_installed_contracts_version_is_compatible():
    installed = version("empirical-data-contracts")
    assert installed == "0.1" or installed.startswith("0.1.")
