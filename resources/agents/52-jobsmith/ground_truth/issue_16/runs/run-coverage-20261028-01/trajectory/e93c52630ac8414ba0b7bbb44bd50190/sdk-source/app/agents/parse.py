"""① 解析 Agent：把 JD 文字抽成結構化 ParsedJob。"""
from app.llm import get_llm
from app.models import ParsedJob

PARSE_SYSTEM = (
    "你是專業的職缺解析器。請從使用者提供的職缺描述（JD）中，"
    "抽取出結構化欄位：職稱、公司、地點、職責、必備條件、加分條件、"
    "最低年資、技術棧、主要語言（zh 或 en）、薪資。"
    "找不到的欄位留空或 null，不要捏造。"
)


def parse_job(jd_text: str) -> ParsedJob:
    """把 JD 文字解析為 ParsedJob（使用 cheap 分層）。"""
    llm = get_llm("cheap").with_structured_output(ParsedJob)
    return llm.invoke(
        [("system", PARSE_SYSTEM), ("human", jd_text)]
    )
