

from tradingagents.agents.utils.context import compact_history


def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")
        data_quality_summary = state.get("data_quality_summary", "")

        prompt = f"""You are a Bear Analyst making the case against investing in this A-share (China mainland) stock. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators unique to the Chinese market. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

A-Share Bear Framework — prioritize these China-specific risk factors:
- Policy Headwinds: Sudden regulatory crackdowns (e.g. industry rectification, antitrust), CSRC window guidance (窗口指导), sector-wide trading restrictions, or political risk signals
- Lockup & Insider Selling: Upcoming lockup expiry dates with large overhang, controlling shareholders in pre-disclosure reduction windows, equity pledge liquidation risk
- Hot Money Withdrawal (游资撤退): Volume divergence after limit-ups (放量滞涨), declining limit-up board count (连板断裂), sector rotation moving away from this theme
- Valuation Bubble: PE far above 30x A-stock growth anchor with EPS unable to digest within 3 years, PEG > 2 indicating overpriced growth, retail-driven speculative premium
- T+1 Trap: After a sharp rally, buyers today cannot exit until tomorrow — if sentiment reverses overnight or a gap-down opens, losses are locked in
- Northbound Retreat: Net outflow from Stock Connect signals foreign institutions reducing exposure

General bear points:
- Risks and Challenges: Market saturation, financial instability, or macroeconomic threats
- Competitive Weaknesses: Weaker market positioning, declining innovation, or competitor threats
- Negative Indicators: Evidence from financial data, market trends, or adverse news
- Bull Counterpoints: Expose over-optimistic assumptions with specific data
- Engagement: Present your argument conversationally, directly engaging with the bull analyst's points

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

Deliver a compelling bear argument grounded in A-share market realities. Refute the bull's claims and demonstrate the risks of investing in this stock within the Chinese regulatory and market structure.
"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
