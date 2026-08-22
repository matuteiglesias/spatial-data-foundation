from datetime import date

from empirical_contracts import PeriodScheme
from spatial_foundation.periods import PeriodIndex


def test_legacy_t2_y2001_semantics():
    index = PeriodIndex(PeriodScheme(width_years=2, anchor_year=2001))
    assert index.period_for(date(2001, 1, 1)).period_id == "2001-2002"
    assert index.period_for(date(2002, 12, 31)).period_id == "2001-2002"
    assert index.period_for(date(2003, 1, 1)).period_id == "2003-2004"
    assert index.period_for(date(1997, 6, 1)).period_id == "1997-1998"
    assert index.period_for(date(1985, 3, 1)).period_id == "1985-1986"


def test_t3_and_t4_parameterize_without_new_code():
    assert PeriodIndex(PeriodScheme(width_years=3, anchor_year=2001)).period_for(2004).period_id == "2004-2006"
    assert PeriodIndex(PeriodScheme(width_years=4, anchor_year=2001)).period_for(2005).period_id == "2005-2008"


def test_alternate_anchor_and_range_use_same_indexing_rule():
    index = PeriodIndex(PeriodScheme(width_years=2, anchor_year=2000))
    assert index.period_for(1999).period_id == "1998-1999"
    assert index.period_for(2000).period_id == "2000-2001"
    assert [p.period_id for p in index.range(1999, 2003)] == ["1998-1999", "2000-2001", "2002-2003"]
