"""⑧ 公司情報 Agent：上網查證公司並彙整成 CompanyBrief。

查證優先序：
1) CLI 後端內建上網工具（claude_cli 的 WebSearch/WebFetch）→ 免額外金鑰、可附來源（主要）。
2) Tavily 金鑰 → 走 Tavily 搜尋。
3) 都沒有 → 用模型一般知識產 brief 並標記 data_limited + note，請使用者自行查證。
"""
from app.llm import get_llm, research_structured
from app.models import CompanyBrief
from app.tools.search import search_web

COMPANY_RESEARCH_SYSTEM = (
    "你是企業情報分析師。請『使用網路搜尋』查證這家公司的最新公開資訊，彙整成情報卡："
    "規模、產業、資金/募資狀況、薪資範圍、福利、文化與評價摘要、面試評價、避雷紅旗、近期新聞，"
    "並在 sources 欄填上你實際查到的來源連結。只根據查到的資料作答，不要臆測；"
    "查不到的欄位留空，不要捏造數字或來源。data_limited 設為 false。"
)

COMPANY_SYSTEM = (
    "你是企業情報分析師。根據提供的公開搜尋結果，彙整出公司情報卡："
    "規模、產業、資金/募資狀況、薪資範圍、福利、文化與評價摘要、"
    "面試評價、避雷紅旗、近期新聞，並附上來源連結。"
    "只根據提供的資料作答，不要臆測；資料不足的欄位留空。"
)

COMPANY_GENERAL_SYSTEM = (
    "你是熟悉台灣就業市場的企業情報分析師。目前沒有即時搜尋結果，"
    "請僅依你已知的一般知識，謹慎地彙整這家公司的情報卡（規模、產業、"
    "可能的薪資範圍、文化、面試方向、可留意的紅旗）。"
    "若對某公司不確定，寧可在欄位留空，也不要編造具體數字或新聞；"
    "不要捏造來源連結。"
)


def _llm_only_brief(company_name: str) -> CompanyBrief:
    """無搜尋金鑰時，用模型一般知識產 brief（標記 data_limited + note，請自行查證）。"""
    try:
        llm = get_llm("standard").with_structured_output(CompanyBrief)
        brief = llm.invoke([("system", COMPANY_GENERAL_SYSTEM),
                            ("human", f"公司名稱：{company_name}")])
        brief.data_limited = True
        brief.note = "未設定搜尋金鑰，以下為模型一般知識，請自行查證"
        return brief
    except Exception:
        return CompanyBrief(company=company_name, data_limited=True,
                            note="未設定搜尋金鑰，且一般知識彙整失敗")


def _cli_research_brief(company_name: str) -> CompanyBrief | None:
    """若後端有內建上網工具（claude_cli），用 WebSearch 查證並結構化成 CompanyBrief；失敗回 None。"""
    try:
        brief = research_structured(
            CompanyBrief,
            [("system", COMPANY_RESEARCH_SYSTEM), ("human", f"公司名稱：{company_name}")],
            tier="standard",
        )
    except Exception:
        return None  # CLI 上網查證失敗 → 交回呼叫端降級（Tavily / 一般知識）
    if brief is None:
        return None
    if not brief.company:
        brief.company = company_name
    return brief


def research_company(company_name: str) -> CompanyBrief:
    """查證公司並回傳 CompanyBrief（standard 分層）。

    CLI 後端可上網（claude_cli）→ 用 WebSearch 直接查證（免金鑰）；
    否則有 Tavily 結果 → 依資料彙整（data_limited=False）；查到但空 → 標記 data_limited；
    未設搜尋金鑰（search_web 拋含 TAVILY_API_KEY 的錯）→ 改用 LLM 一般知識 brief；
    其他搜尋失敗 → 標記 data_limited。
    """
    cli_brief = _cli_research_brief(company_name)
    if cli_brief is not None:
        return cli_brief
    try:
        results = search_web(f"{company_name} 公司 評價 薪資 福利 面試")
    except Exception as exc:
        if "TAVILY_API_KEY" in str(exc):  # 未設金鑰 → LLM 一般知識，不再回空殼
            return _llm_only_brief(company_name)
        return CompanyBrief(company=company_name, data_limited=True, note="即時搜尋失敗")

    if not results:
        return CompanyBrief(company=company_name, data_limited=True,
                            note="即時搜尋查無足夠公開資料")

    context = "\n\n".join(
        f"- {r['title']}\n{r['content']}\n來源: {r['url']}" for r in results
    )
    human = f"公司名稱：{company_name}\n\n公開搜尋結果：\n{context}"
    llm = get_llm("standard").with_structured_output(CompanyBrief)
    return llm.invoke([("system", COMPANY_SYSTEM), ("human", human)])
