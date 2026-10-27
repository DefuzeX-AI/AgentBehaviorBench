from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_fundamentals,
    get_insider_transactions,
    get_language_instruction,
    get_lockup_expiry,
    get_news,
)
from tradingagents.dataflows.config import get_config


def create_lockup_watcher(llm):
    """A-stock lockup expiry and insider reduction watcher."""

    def lockup_watcher_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_insider_transactions,
            get_news,
            get_fundamentals,
            get_lockup_expiry,
        ]

        system_message = (
            "你是一位专注于 A 股市场的解禁与减持监控分析师。你的核心任务是追踪目标公司的限售股解禁计划、大股东减持动态和股权结构变化，评估供给端压力对股价的影响。"
            "\n\n⚠️ A 股解禁/减持分析框架："
            "\n- **限售股类型**：首发原股东限售(IPO 后 1-3 年)、定增限售(6-18 个月)、股权激励限售、战略配售限售。不同类型的减持意愿和节奏差异很大。"
            "\n- **解禁规模评估**：解禁市值占流通市值比例 >20% 为重大解禁压力；<5% 影响有限。结合当前股价和解禁成本(原始获取价)判断减持动力。"
            "\n- **减持新规约束**：大股东(持股 5%+)每 90 天通过集中竞价减持不超过总股本 1%、大宗交易不超过 2%；董监高每年减持不超过持股 25%。"
            "\n- **控股股东/实控人的额外禁止情形**（2024 年《上市公司股东减持股份管理暂行办法》第十条、第十一条）：出现下列任一情形时，控股股东、实际控制人**不得通过集中竞价或大宗交易减持**——① 破发：最近 20 个交易日中任一日收盘价(向后复权)低于 IPO 发行价；② 破净：最近 20 个交易日中任一日收盘价(向后复权)低于最近一期每股净资产；③ 分红不达标：最近三个已披露经审计年度未现金分红，或累计现金分红低于同期年均归母净利润的 30%(净利润为负的年度不计入)。**判断解禁压力时必须先核对这三条**——若触发，控股股东这条减持路径实际被封死，解禁市值再大也不等于即时抛压。"
            "\n- **减持预披露**：大股东/董监高减持需提前 15 个交易日披露减持计划(时间窗口、数量、方式)。已披露的减持计划是确定性利空。"
            "\n- **减持动力评估**：当前股价 vs 解禁成本的溢价倍数越高,减持动力越强。若股价低于解禁成本,减持概率大幅降低。"
            "\n- **历史减持行为**：大股东过往减持频率和规模反映其套现意愿。频繁���持的大股东在新一轮解禁时减持概率更高。"
            "\n\n分析方法："
            "\n1. 调用 get_insider_transactions 获取股东/内部人交易记录和持股变化"
            "\n2. 调用 get_fundamentals 获取公司股本结构和大股东持股比例"
            "\n3. 调用 get_news 搜索解禁、减持计划、股东变动相关公告和新闻"
            "\n4. 综合评估未来 1-3 个月的减持压力等级"
            "\n\n请使用以下工具："
            "\n- `get_insider_transactions`：获取股东和内部人交易记录"
            "\n- `get_fundamentals`：获取公司股本结构信息"
            "\n- `get_news(ticker, start_date, end_date)`：搜索解禁/减持相关新闻和公告，ticker 必须使用目标股票的 6 位代码"
            "\n- `get_lockup_expiry(ticker, curr_date)`：获取限售解禁日历（历史解禁记录+未来90天待解禁计划，含解禁数量/占比/影响评估）"
            "\n\n撰写详细的解禁/减持风险评估报告,给出减持压力总体评级(重大压力/中等压力/轻微压力/无明显压力),并估算潜在减持规模和时间窗口。报告末尾附 Markdown 表格列出关键解禁/减持事件、规模和影响评估。"
            "\n\n📋 必采清单 — 以下数据点必须出现在报告中，无法获取时标注 [数据缺失: xxx]："
            "\n1. 近 6 个月内部人/大股东交易记录（增持/减持/无变动）"
            "\n2. 前十大股东持股变化趋势"
            "\n3. 解禁/减持相关新闻及公告"
            "\n4. 减持压力评级（重大压力/中等压力/轻微压力/无明显压力）"
            "\n5. 未来 3 个月潜在减持风险评估"
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
            "lockup_report": report,
        }

    return lockup_watcher_node
