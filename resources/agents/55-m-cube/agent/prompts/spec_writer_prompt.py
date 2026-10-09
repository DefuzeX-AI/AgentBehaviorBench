from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

PROMPT_VERSION = "spec_writer_v1"

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "spec_writer_zh.md"

_FALLBACK_TEMPLATE = """
【输出目标】
请基于交底书、技术摘要与已确认权利要求，生成符合 Specification schema 的完整说明书 JSON。

【章节要求】
1. 标题(title)准确反映发明主题；
2. 技术领域(technical_field)与背景技术(background_art)语义连贯；
3. 发明内容(invention_content)必须包含：
   - technical_problem
   - technical_solution
   - beneficial_effects
4. 具体实施方式(detailed_implementation)必须包含：
   - introductory_boilerplate
   - overall_architecture
   - component_details（数组，每项包含 feature_name/structure_and_connection/working_principle）
   - workflow_description
   - alternative_embodiments

【约束】
- 不得引入交底书未披露的新技术特征；
- 术语、部件命名、附图标注保持一致；
- 只输出 JSON，不输出解释文本。
""".strip()

SPEC_WRITER_RULES = (
    "你是中国专利说明书撰写助手。请严格遵守以下规则：\n"
    "1) 忠实于技术交底书与已确认权利要求，不得臆造未披露的技术特征。\n"
    "2) 术语前后一致，部件名称、附图标记、功能描述保持统一。\n"
    "3) 当提供附图结构化映射时，优先使用其中的部件名称和附图标记。\n"
    "4) 输出必须为符合 Specification schema 的完整 JSON。\n"
    "5) 不要输出 JSON 以外的解释性文字。\n"
)

SPEC_WRITER_SCHEMA_GUIDE = (
    "Specification 字段结构要求：\n"
    "1) invention_content 必须是对象，且包含 technical_problem / technical_solution / beneficial_effects。\n"
    "2) detailed_implementation 必须是对象，且包含 introductory_boilerplate / overall_architecture / "
    "component_details / workflow_description / alternative_embodiments。\n"
    "3) component_details 必须是数组，每项包含 feature_name / structure_and_connection / working_principle。\n"
)


@lru_cache(maxsize=1)
def load_spec_writer_template() -> str:
    if not _TEMPLATE_PATH.exists():
        # Packaged sidecar fallback: avoid hard-fail when template asset was not bundled.
        return _FALLBACK_TEMPLATE
    return _TEMPLATE_PATH.read_text(encoding="utf-8").strip()


def build_write_spec_prompt(
    *,
    disclosure_text: str,
    tech_summary: dict[str, Any] | None,
    claims: dict[str, Any] | None,
    drawing_map: dict[str, Any] | None,
) -> str:
    template = load_spec_writer_template()
    return (
        f"[PROMPT_VERSION]\n{PROMPT_VERSION}\n\n"
        f"[ROLE_AND_RULES]\n{SPEC_WRITER_RULES}\n\n"
        f"[SCHEMA_GUIDE]\n{SPEC_WRITER_SCHEMA_GUIDE}\n\n"
        f"[SPEC_FORMAT_GUIDE]\n{template}\n\n"
        "[OUTPUT_CONSTRAINT]\n"
        "Return valid JSON only.\n\n"
        f"[DISCLOSURE_TEXT]\n{disclosure_text}\n\n"
        f"[TECH_SUMMARY]\n{tech_summary}\n\n"
        f"[APPROVED_CLAIMS]\n{claims}\n\n"
        f"[DRAWING_MAP]\n{drawing_map}"
    )
