"""Regression tests for the Sina financial-statement response shape.

The API returns ``result.data.report_list{报告期: {..., data: [{item_title, item_value}]}}``.
The parser written in v0.2.5 only read ``result.data.<fzb|lrb|llb>`` (a flat list of
rows), so all three statements silently came back as "No ... data found" instead of
raising — the agent then reported "this stock has no financial statements" as a fact.
"""

import copy
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows import a_stock

# Shape the live API returns.
NEW_SHAPE = {
    "result": {
        "status": {"code": 0},
        "data": {
            "report_count": "2",
            "report_date": [
                {
                    "date_value": "20260630",
                    "date_description": "2026半年报",
                    "date_type": 2,
                },
                {
                    "date_value": "20260331",
                    "date_description": "2026一季报",
                    "date_type": 1,
                },
            ],
            "report_list": {
                "20260630": {
                    "rType": "合并期末",
                    "data": [
                        {"item_field": "", "item_title": "流动资产", "item_value": ""},
                        {
                            "item_field": "CURFDS",
                            "item_title": "货币资金",
                            "item_value": "53518798979.08",
                        },
                    ],
                },
                "20260331": {
                    "rType": "合并期末",
                    "data": [
                        {
                            "item_field": "CURFDS",
                            "item_title": "货币资金",
                            "item_value": "50000000000.0",
                        },
                    ],
                },
            },
        },
    }
}

# Flat-list shape the v0.2.5 parser was written against; kept for compatibility.
LEGACY_SHAPE = {
    "result": {
        "data": {
            "fzb": [
                {"报告日": "20260630", "货币资金": "53518798979.08"},
                {"报告日": "20260331", "货币资金": "50000000000.0"},
            ]
        }
    }
}


def _response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_new_report_list_shape_is_parsed(mock_get):
    """The newer payload shape must produce real rows, not an empty table."""
    mock_get.return_value = _response(NEW_SHAPE)

    out = a_stock.get_balance_sheet("600519", "quarterly", "2026-09-30")

    assert "No balance sheet data found" not in out
    assert "货币资金" in out
    assert "53518798979.08" in out
    assert "2026-06-30" in out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_legacy_shape_still_parsed(mock_get):
    """Compatibility: the shape the parser was written for must keep working."""
    mock_get.return_value = _response(LEGACY_SHAPE)

    out = a_stock.get_balance_sheet("600519", "quarterly", "2026-09-30")

    assert "No balance sheet data found" not in out
    assert "53518798979.08" in out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_all_three_statements_parse_the_new_shape(mock_get):
    mock_get.return_value = _response(NEW_SHAPE)

    for getter, empty_msg in (
        (a_stock.get_balance_sheet, "No balance sheet data found"),
        (a_stock.get_cashflow, "No cash flow data found"),
        (a_stock.get_income_statement, "No income statement data found"),
    ):
        out = getter("600519", "quarterly", "2026-09-30")
        assert empty_msg not in out, out
        assert "货币资金" in out, out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_unrecognised_shape_degrades_to_empty_table(mock_get):
    """An unknown payload must not raise; it degrades to "no data"."""
    mock_get.return_value = _response({"result": {"data": {"unexpected": []}}})

    out = a_stock.get_balance_sheet("600519", "quarterly", "2026-09-30")

    assert "No balance sheet data found" in out



def _with_publish_dates(h1_published, q1_published):
    """NEW_SHAPE plus the per-period publish_date the live API returns."""
    payload = copy.deepcopy(NEW_SHAPE)
    report_list = payload["result"]["data"]["report_list"]
    report_list["20260630"]["publish_date"] = h1_published
    report_list["20260331"]["publish_date"] = q1_published
    return payload


@pytest.mark.unit
def test_report_deadline_follows_disclosure_rules():
    """一季报 / 三季报 +1 个月、半年报 +2 个月、年报次年 4 月底；非标准期按 4 个月，缺失仍为缺失。"""
    dates = pd.to_datetime(
        pd.Series(["20260331", "20260630", "20260930", "20261231", "20260531", None]),
        errors="coerce",
    )
    got = a_stock._report_deadline(dates)
    assert [d.strftime("%Y-%m-%d") for d in got[:5]] == [
        "2026-04-30", "2026-08-31", "2026-10-31", "2027-04-30", "2026-09-30",
    ]
    assert pd.isna(got.iloc[5])


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_report_not_yet_published_on_analysis_date_is_excluded(mock_get):
    """No look-ahead: on 07-15 the 06-30 half-year report (published 08-15) is not out yet."""
    mock_get.return_value = _response(_with_publish_dates("20260815", "20260425"))

    out = a_stock.get_balance_sheet("600519", "quarterly", "2026-07-15")

    assert "53518798979.08" not in out
    assert "2026-06-30" not in out
    assert "50000000000.0" in out
    assert "2026-03-31" in out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_report_published_before_analysis_date_is_kept(mock_get):
    mock_get.return_value = _response(_with_publish_dates("20260815", "20260425"))

    for curr_date in ("2026-08-16", "2026-09-30"):
        out = a_stock.get_balance_sheet("600519", "quarterly", curr_date)
        assert "53518798979.08" in out, (curr_date, out)
        assert "50000000000.0" in out, (curr_date, out)


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_publish_day_itself_is_not_enough(mock_get):
    """Reports often go out after the close on their publish_date; the analysis day must be later."""
    mock_get.return_value = _response(_with_publish_dates("20260815", "20260425"))

    out = a_stock.get_balance_sheet("600519", "quarterly", "2026-08-15")

    assert "53518798979.08" not in out
    assert "50000000000.0" in out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_late_republish_date_does_not_hide_report_past_deadline(mock_get):
    """Sina stamps older periods with the date they were re-printed as next year's comparatives.

    The 2026 half-year report is long out by 2026-09-30 (deadline 08-31) even though its
    publish_date says 2027-08-14; it must not be dropped.
    """
    mock_get.return_value = _response(_with_publish_dates("20270814", "20270424"))

    out = a_stock.get_balance_sheet("600519", "quarterly", "2026-09-30")

    assert "53518798979.08" in out
    assert "50000000000.0" in out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_publish_date_column_is_not_returned(mock_get):
    """公告日 of older periods is a re-print date; showing it would mislead the analyst."""
    mock_get.return_value = _response(_with_publish_dates("20260815", "20260425"))

    for curr_date in (None, "2026-09-30"):
        out = a_stock.get_balance_sheet("600519", "quarterly", curr_date)
        assert "公告日" not in out, out
        assert "53518798979.08" in out, out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_legacy_shape_without_publish_date_waits_for_deadline(mock_get):
    mock_get.return_value = _response(LEGACY_SHAPE)

    out = a_stock.get_balance_sheet("600519", "quarterly", "2026-07-15")

    assert "53518798979.08" not in out
    assert "50000000000.0" in out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_all_three_statements_respect_publication(mock_get):
    mock_get.return_value = _response(_with_publish_dates("20260815", "20260425"))

    for getter in (a_stock.get_balance_sheet, a_stock.get_cashflow, a_stock.get_income_statement):
        out = getter("600519", "quarterly", "2026-07-15")
        assert "53518798979.08" not in out, out
        assert "50000000000.0" in out, out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_annual_filter_still_applies_with_publish_dates(mock_get):
    """freq='annual' keeps only December report periods, publish dates or not."""
    mock_get.return_value = _response(_with_publish_dates("20260815", "20260425"))

    out = a_stock.get_balance_sheet("600519", "annual", "2026-09-30")

    assert "No balance sheet data found" in out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_deadline_day_itself_is_not_enough(mock_get):
    """Reports due by 08-31 may come out that evening; only the day after counts without a publish date."""
    mock_get.return_value = _response(LEGACY_SHAPE)

    assert "53518798979.08" not in a_stock.get_balance_sheet("600519", "quarterly", "2026-08-31")
    assert "53518798979.08" in a_stock.get_balance_sheet("600519", "quarterly", "2026-09-01")


def _ts(beijing_time):
    """Unix seconds as Sina's update_time, from a Beijing wall-clock time."""
    return str(int(pd.Timestamp(beijing_time, tz="Asia/Shanghai").timestamp()))


def _periods(**periods):
    """report_list with one 货币资金 row per period: name -> (value, publish_date, update_time)."""
    report_list = {}
    for name, (value, published, updated) in periods.items():
        payload = {"data": [{"item_field": "CURFDS", "item_title": "货币资金", "item_value": value}]}
        if published:
            payload["publish_date"] = published
        if updated:
            payload["update_time"] = updated
        report_list[name[1:]] = payload
    return {"result": {"data": {"report_list": report_list}}}


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_late_filer_is_not_shown_once_the_deadline_passes(mock_get):
    """A company that files its annual report in July must not appear published on 04-30.

    Real case: 300630's 2023 annual and 2024 Q1 reports both came out on 2024-07-05.
    """
    mock_get.return_value = _response(_periods(
        d20251231=("111.0", "20260705", _ts("2026-07-05 23:42")),
        d20250930=("222.0", "20251030", _ts("2025-10-29 18:12")),
    ))

    for curr_date in ("2026-05-15", "2026-07-05"):
        out = a_stock.get_balance_sheet("600519", "quarterly", curr_date)
        assert "111.0" not in out, (curr_date, out)
        assert "222.0" in out, (curr_date, out)
    assert "111.0" in a_stock.get_balance_sheet("600519", "quarterly", "2026-07-06")

    # Same late filer with no update_time: its publish_date alone is still the original date.
    mock_get.return_value = _response(_periods(d20251231=("111.0", "20260705", None)))
    assert "111.0" not in a_stock.get_balance_sheet("600519", "quarterly", "2026-05-15")
    assert "111.0" in a_stock.get_balance_sheet("600519", "quarterly", "2026-07-06")


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_update_time_is_read_in_beijing_time(mock_get):
    """07:30 Beijing is still the previous day in UTC; it must not count as entered the day before."""
    mock_get.return_value = _response(_periods(
        d20251231=("111.0", "20270420", _ts("2026-07-06 07:30")),
    ))

    assert "111.0" not in a_stock.get_income_statement("600519", "quarterly", "2026-07-06")
    assert "111.0" in a_stock.get_income_statement("600519", "quarterly", "2026-07-07")


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_update_time_admits_report_whose_publish_date_was_rewritten(mock_get):
    """600519's 2025 year-end balance sheet: published 2026-04-17, but publish_date now says
    2026-08-15 (re-printed in the half-year report as the opening balance). update_time still
    holds the original evening entry and must let it through from the next day."""
    mock_get.return_value = _response(_periods(
        d20251231=("111.0", "20260815", _ts("2026-04-16 22:54")),
    ))

    assert "111.0" not in a_stock.get_balance_sheet("600519", "quarterly", "2026-04-16")
    for curr_date in ("2026-04-17", "2026-05-15"):
        assert "111.0" in a_stock.get_balance_sheet("600519", "quarterly", curr_date), curr_date


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_deadline_applies_only_when_both_dates_were_rewritten(mock_get):
    """Both dates more than a year after the period: the original date is lost, so assume on time.

    600519's 2021-09-30 income statement: publish_date 2022-10-17, update_time 2022-10-16.
    """
    mock_get.return_value = _response(_periods(
        d20210930=("111.0", "20221017", _ts("2022-10-16 15:57")),
    ))

    assert "111.0" not in a_stock.get_income_statement("600519", "quarterly", "2021-10-31")
    assert "111.0" in a_stock.get_income_statement("600519", "quarterly", "2021-11-01")


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_late_filer_with_rewritten_publish_date_still_waits_for_update_time(mock_get):
    """Income statement re-printed in next year's annual: publish_date moves a year on, but
    update_time keeps the late July entry, so the original date is not lost."""
    mock_get.return_value = _response(_periods(
        d20251231=("111.0", "20270420", _ts("2026-07-05 23:42")),
    ))

    assert "111.0" not in a_stock.get_income_statement("600519", "quarterly", "2026-05-15")
    assert "111.0" in a_stock.get_income_statement("600519", "quarterly", "2026-07-06")


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_sina_batch_import_time_does_not_count_as_original_entry(mock_get):
    """Sina bulk-loaded every period up to 2019Q3 on 2020-03-13 (600519 income statement: 76
    periods share 1584086440). For 2019Q1-Q3 that time is within a year and publish_date was
    rewritten by the 2020 reports; they must not stay hidden until 2020-03-14."""
    batch = "1584086440"
    mock_get.return_value = _response(_periods(
        d20191231=("444.0", "20210202", batch),
        d20190930=("333.0", "20201026", batch),
        d20190630=("222.0", "20200729", batch),
        d20190331=("111.0", "20200428", batch),
        d20181231=("100.0", "20200428", batch),
        d20180930=("90.0", "20191026", batch),
    ))

    def latest(curr_date):
        df = a_stock._get_financial_report_sina("600519", "利润表", "quarterly", curr_date)
        return df["货币资金"].iloc[0]

    assert latest("2019-04-30") == "90.0"  # 2018 annual and 2019Q1 deadlines are both 04-30
    assert latest("2019-05-01") == "111.0"
    assert latest("2019-09-01") == "222.0"
    assert latest("2019-11-15") == "333.0"
    # The batch still proves the data was public by then: 000001's 2019 annual was in it,
    # six weeks before the annual-report deadline.
    assert latest("2020-03-13") == "333.0"
    assert latest("2020-03-14") == "444.0"


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_two_periods_sharing_an_entry_time_are_not_a_batch(mock_get):
    """A late filer's annual and Q1 reports entered together (300630, 2024-07-05) must still
    wait for that entry time even after next year's reports rewrite their publish_date."""
    late = _ts("2026-07-05 23:42")
    mock_get.return_value = _response(_periods(
        d20260331=("222.0", "20270428", late),
        d20251231=("111.0", "20270420", late),
        d20250930=("90.0", "20261030", _ts("2025-10-29 18:12")),
    ))

    out = a_stock.get_income_statement("600519", "quarterly", "2026-05-15")
    assert "111.0" not in out and "222.0" not in out, out
    out = a_stock.get_income_statement("600519", "quarterly", "2026-07-06")
    assert "111.0" in out and "222.0" in out, out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_late_filer_catching_up_three_periods_at_once_is_not_a_batch(mock_get):
    """Only Sina's 2020-03-13 bulk load counts as a batch. A company that files its annual,
    Q1 and H1 reports together on 2024-09-20 must stay hidden until then, even after next
    year's reports rewrite all three publish dates."""
    late = _ts("2024-09-20 22:10")
    mock_get.return_value = _response(_periods(
        d20240630=("333.0", "20250830", late),
        d20240331=("222.0", "20250430", late),
        d20231231=("111.0", "20250425", late),
        d20230930=("90.0", "20241030", _ts("2023-10-30 19:00")),
    ))

    for curr_date in ("2024-06-15", "2024-09-01", "2024-09-20"):
        out = a_stock.get_income_statement("600519", "quarterly", curr_date)
        assert "111.0" not in out and "222.0" not in out and "333.0" not in out, (curr_date, out)
    out = a_stock.get_income_statement("600519", "quarterly", "2024-09-21")
    assert "111.0" in out and "222.0" in out and "333.0" in out, out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_single_entry_on_the_batch_day_is_not_a_batch(mock_get):
    """A late 2019Q3 report genuinely entered on 2020-03-13 is not part of the bulk load."""
    mock_get.return_value = _response(_periods(
        d20190930=("333.0", "20201026", _ts("2020-03-13 20:15")),
        d20190630=("222.0", "20200729", _ts("2019-08-07 18:00")),
    ))

    assert "333.0" not in a_stock.get_income_statement("600519", "quarterly", "2019-12-01")
    assert "333.0" in a_stock.get_income_statement("600519", "quarterly", "2020-03-14")


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_publish_date_on_the_period_end_is_ignored(mock_get):
    """Pre-listing rows can carry publish_date == report date (600519 19981231); no report is
    public on its own period end, so fall back to the deadline."""
    mock_get.return_value = _response(_periods(d19981231=("111.0", "19981231", None)))

    assert "111.0" not in a_stock.get_income_statement("600519", "quarterly", "1999-01-15")
    assert "111.0" in a_stock.get_income_statement("600519", "quarterly", "1999-05-01")


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_internal_date_columns_are_not_returned(mock_get):
    mock_get.return_value = _response(_periods(
        d20251231=("111.0", "20260417", _ts("2026-04-16 22:54")),
    ))

    for curr_date in (None, "2026-09-30"):
        out = a_stock.get_balance_sheet("600519", "quarterly", curr_date)
        assert "111.0" in out, out
        assert "公告日" not in out and "入库时间" not in out, out
        assert "20260417" not in out, out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_duplicate_item_titles_do_not_overwrite_each_other(mock_get):
    """利润表 has 利息收入 under 营业总收入 and again under 财务费用; both values must survive."""
    payload = {"result": {"data": {"report_list": {"20260630": {
        "publish_date": "20260815",
        "data": [
            {"item_field": "BIZTOTINCO", "item_title": "营业总收入", "item_display": "大类", "item_value": "92278072083.21"},
            {"item_field": "INTEINCO", "item_title": "利息收入", "item_display": "小类", "item_value": "1574811118.73"},
            {"item_field": "FINEXPE", "item_title": "财务费用", "item_display": "小类", "item_value": "-243237716.96"},
            {"item_field": "INTEINCOOPCOST", "item_title": "利息收入", "item_display": "缩进", "item_value": "266574096.14"},
            {"item_field": "OTHERA", "item_title": "其他", "item_display": "小类", "item_value": "11.0"},
            {"item_field": "OTHERB", "item_title": "其他", "item_display": "小类", "item_value": "22.0"},
        ],
    }}}}}
    mock_get.return_value = _response(payload)

    df = a_stock._get_financial_report_sina("600519", "利润表", "quarterly", "2026-09-30")

    assert df.loc[df.index[0], "利息收入"] == "1574811118.73"
    assert df.loc[df.index[0], "财务费用-利息收入"] == "266574096.14"
    assert df.loc[df.index[0], "其他"] == "11.0"
    assert df.loc[df.index[0], "其他（OTHERB）"] == "22.0"


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_newest_published_periods_come_first(mock_get):
    """Output order must not depend on the order the API happens to list periods in."""
    periods = {}
    for i, period in enumerate(pd.period_range("2023Q1", "2025Q4", freq="Q")):
        end = period.end_time.strftime("%Y%m%d")
        periods["d" + end] = (f"{1000 + i}.0", None, None)
    mock_get.return_value = _response(_periods(**periods))  # oldest first

    df = a_stock._get_financial_report_sina("600519", "资产负债表", "quarterly", "2026-09-30")

    assert list(df["货币资金"]) == [f"{1000 + i}.0" for i in range(11, 3, -1)]


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_missing_report_date_column_is_not_returned_unfiltered(mock_get):
    """Without 报告日 there is no way to tell what was published by the analysis date."""
    mock_get.return_value = _response({"result": {"data": {"report_list": [{"货币资金": "111.0"}]}}})

    assert "No balance sheet data found" in a_stock.get_balance_sheet("600519", "quarterly", "2026-09-30")
    assert "111.0" in a_stock.get_balance_sheet("600519", "quarterly", None)


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_older_analysis_dates_fetch_more_periods(mock_get):
    """The API lists newest first; 20 periods only reach back ~5 years."""
    mock_get.return_value = _response(NEW_SHAPE)
    today = pd.Timestamp.now()

    def num_for(curr_date):
        a_stock.get_balance_sheet("600519", "quarterly", curr_date)
        return int(mock_get.call_args.kwargs["params"]["num"])

    assert num_for(None) == 20
    assert num_for(today.strftime("%Y-%m-%d")) == 20
    ten_years_ago = num_for((today - pd.DateOffset(years=10)).strftime("%Y-%m-%d"))
    assert ten_years_ago >= 20 + 40 - 1, ten_years_ago
    assert num_for("1990-01-01") == 120
