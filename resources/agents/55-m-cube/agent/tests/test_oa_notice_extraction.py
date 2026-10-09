from __future__ import annotations

from api.routers import _extract_examiner_opinion_text


def test_extract_examiner_opinion_by_headings() -> None:
    notice = """
一、结论
本申请目前不具备授权条件。

二、审查员具体意见
1. 权利要求1相对于对比文件D1不具备新颖性。
2. 权利要求2-5相对于D1与D2的结合不具备创造性。
3. 说明书中术语“模块A”定义不清楚。

三、检索报告
检索式：...
引用文件：D1, D2
""".strip()

    extracted, used = _extract_examiner_opinion_text(notice)
    assert used is True
    assert "不具备新颖性" in extracted
    assert "不具备创造性" in extracted
    assert "检索式" not in extracted
    assert "一、结论" not in extracted


def test_extract_examiner_opinion_by_second_issue_title_to_retrieval() -> None:
    notice = """
国家知识产权局
第1次审查意见通知书
（首页摘要）

第2次审查意见通知书
审查员认为：
1. 权利要求1-3相对于D1不具备新颖性。
2. 权利要求4-6相对于D1与D2结合不具备创造性。
3. 说明书实施例支持关系需进一步说明。

检索报告
检索式：A01B...
引用文件：D1、D2
""".strip()

    extracted, used = _extract_examiner_opinion_text(notice)
    assert used is True
    assert extracted.startswith("审查员认为")
    assert "不具备新颖性" in extracted
    assert "检索报告" not in extracted
    assert "第1次审查意见通知书" not in extracted


def test_extract_examiner_opinion_by_page3_to_examiner_signature() -> None:
    pages = [
        "第1页：结论页",
        "第2页：程序性内容",
        "第3页：审查具体意见开始。权利要求1-5存在创造性问题。",
        "第4页：继续意见。说明书支持关系不足。\n审查员姓名：张三\n审查员代码：12345",
    ]
    notice = "\n\n".join(pages)

    extracted, used = _extract_examiner_opinion_text(notice, notice_pages=pages)
    assert used is True
    assert "第3页：审查具体意见开始" in extracted
    assert "继续意见" in extracted
    assert "审查员姓名" not in extracted
    assert "审查员代码" not in extracted


def test_extract_examiner_opinion_fallback_to_original() -> None:
    notice = "这是一段没有明确章节标题的短通知文本。"
    extracted, used = _extract_examiner_opinion_text(notice)
    assert used is False
    assert extracted == notice
