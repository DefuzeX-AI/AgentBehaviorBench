

from tradingagents.agents.utils.context import compact_history


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")
        data_quality_summary = state.get("data_quality_summary", "")

        prompt = f"""You are a Bull Analyst advocating for investing in this A-share (China mainland) stock. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

A-Share Bull Framework — prioritize these China-specific bullish catalysts:
- Policy Tailwinds: Government subsidies, industry support policies (e.g. "专精特新", national strategic sectors), favorable regulatory signals from CSRC/State Council
- Northbound Capital (北向资金): Sustained net inflow from Hong Kong Stock Connect indicates foreign institutional conviction
- Hot Money Momentum (游资接力): Consecutive limit-ups with volume confirmation, strong theme attribution (reason tags), sector rotation just beginning
- Valuation Growth Story: Use forward PE, PEG, and PE digestion timeframe (30x anchor for A-stock growth stocks) to argue the current premium is justified by earnings trajectory
- Lockup Expiry Cleared: If major lockup periods have passed or insiders are NOT reducing, this removes a key overhang

General bull points:
- Growth Potential: Market opportunities, revenue projections, and scalability
- Competitive Advantages: Unique products, dominant market positioning, or moat in the domestic market
- Positive Indicators: Financial health, industry trends, and recent positive news
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning
- Engagement: Present your argument conversationally, engaging directly with the bear analyst's points

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest news report: {news_report}
Company fundamentals report: {fundamentals_report}
Policy analysis report: {policy_report}
Hot money / capital flow report: {hot_money_report}
Lockup expiry / insider reduction report: {lockup_report}
Data quality assessment: {data_quality_summary}
Conversation history of the debate: {compact_history(history)}

⚠️ If the data quality assessment flags any report as low-confidence (grade C/D/F), reduce your reliance on that report and note the data limitation in your argument.

Deliver a compelling bull argument that integrates A-share market dynamics. Refute the bear's concerns and demonstrate why the bull position holds stronger merit in the Chinese market context.
"""

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
