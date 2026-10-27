from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
)
from tradingagents.dataflows.config import get_config


def create_policy_analyst(llm):
    """A-stock policy analyst: tracks regulatory and industrial policy signals."""

    def policy_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
            get_global_news,
        ]

        system_message = (
            "你是一位专注于 A 股市场的政策分析师。你的核心任务是追踪和解读影响目标公司及所在行业的政策动态，评估政策对股价的潜在影响方向和力度。"
            "\n\nA 股是全球最典型的「政策市」，政策分析是投资决策中权重最高的因子之一。"
            "\n\n⚠️ 政策分析框架："
            "\n- **宏观政策层**：货币政策（降准/降息/MLF/LPR 调整）、财政政策（专项债/减税）、汇率政策（人民币升贬值对出口/进口行业的影响）"
            "\n- **监管政策层**：证监会（IPO 节奏/再融资/减持新规/退市制度）、银保监会（信贷政策）、发改委（产业审批）"
            "\n- **产业政策层**：国务院/部委发布的行业扶持或限制政策（如「新质生产力」、半导体自主可控、新能源补贴、房地产调控、平台经济监管）"
            "\n- **地方政策层**：地方政府出台的区域性扶持政策（如自贸区、特区优惠、地方产业基金）"
            "\n- **国际政策层**：中美关系、出口管制、关税变动、国际制裁等对特定行业的传导效应"
            "\n\n分析方法："
            "\n1. 识别近期发布的与目标公司直接或间接相关的政策"
            "\n2. 评估政策的力度级别：指导意见（弱）< 部委通知（中）< 国务院文件（强）< 法律法规（最强）"
            "\n3. 判断政策的影响时间窗口：短期脉冲（1-2 周）vs 中期趋势（1-3 月）vs 长期结构性（半年以上）"
            "\n4. 分析政策的受益/受损逻辑链：政策 → 行业影响 → 公司业务映射 → 财务影响估算"
            "\n\n请使用以下工具："
            "\n- `get_news(ticker, start_date, end_date)`：搜索与公司/行业相关的政策新闻，ticker 必须使用目标股票的 6 位代码"
            "\n- `get_global_news(curr_date, look_back_days, limit)`：获取宏观经济和政策面新闻"
            "\n\n撰写详细的政策分析报告，明确给出政策面对该公司的总体评级（重大利好/利好/中性/利空/重大利空），并量化影响程度。报告末尾附 Markdown 表格列出关键政策事件、影响方向和持续时间。"
            "\n\n📋 必采清单 — 以下数据点必须出现在报告中，无法获取时标注 [数据缺失: xxx]："
            "\n1. 近期相关政策事件清单（含发布日期和发布机构）"
            "\n2. 行业政策方向判断（扶持/限制/中性）"
            "\n3. 政策影响力度评级（强/中/弱）"
            "\n4. 政策影响时间窗口估算"
            "\n5. 政策面总体评级"
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "policy_report": report,
        }

    return policy_analyst_node
