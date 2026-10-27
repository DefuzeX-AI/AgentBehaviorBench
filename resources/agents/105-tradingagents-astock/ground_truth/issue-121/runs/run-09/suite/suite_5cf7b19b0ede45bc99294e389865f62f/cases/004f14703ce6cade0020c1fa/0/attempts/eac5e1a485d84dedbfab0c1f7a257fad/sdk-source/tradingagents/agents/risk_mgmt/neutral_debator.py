

from tradingagents.agents.utils.context import compact_history


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Neutral Risk Analyst evaluating an A-share (China mainland) stock, your role is to provide a balanced perspective, weighing both the potential benefits and risks. Factor in A-share market structure, broader trends, and diversification strategies.

A-Share Neutral Framework — use these China-specific balancing considerations:
- T+1 as Double-Edged Sword: T+1 locks in losses (conservative point) BUT also prevents panic selling and allows multi-day momentum to develop (aggressive point). The neutral view: size positions so that a single overnight gap-down is survivable.
- Policy Sensitivity Calibration: Not all policy signals are equal. Distinguish between top-level State Council directives (high conviction) vs local government incentives (lower reliability) vs market rumors (noise). Weight your risk assessment accordingly.
- Northbound Flow as Smart Money Gauge: Foreign institutional flow via Stock Connect is more informed than retail flow, but also more fickle — they exit faster than domestic funds. Use it as a confirming signal, not a primary thesis.
- Valuation Band Approach: Rather than rigid "PE > 30x is expensive" or "PE doesn't matter in growth", propose a valuation band — what PE range is defensible given the earnings trajectory? Use the PE digestion timeframe as a practical anchor.
- Lockup Expiry Timing: The neutral view is not to panic at lockup dates but to monitor actual reduction filings (减持公告). The risk is real but the timing is uncertain — reducing exposure gradually near lockup windows is more sensible than binary all-in/all-out.
- Sector Rotation Awareness: A-share themes rotate fast (typically 2-4 weeks). The neutral question is: where are we in the rotation cycle? Early rotation = room to run; late rotation = reduced upside with elevated downside.
- Position Sizing over Direction: In a market with ±10-20% daily limits and T+1 settlement, position sizing is more important than directional conviction. A moderate position captures upside while limiting locked-in loss scenarios.

Here is the trader's decision:

{trader_decision}

Challenge both the aggressive and conservative analysts. Point out where each perspective is overly optimistic or overly cautious in the A-share context. Use these data sources:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest News Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Policy Analysis Report: {policy_report}
Hot Money / Capital Flow Report: {hot_money_report}
Lockup Expiry / Insider Reduction Report: {lockup_report}
Conversation history: {compact_history(history)} If no responses yet, present your own argument.

Advocate for a balanced, position-sized approach that captures A-share upside while respecting the market's structural constraints. Output conversationally without special formatting."""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
