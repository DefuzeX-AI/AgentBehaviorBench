

from tradingagents.agents.utils.context import compact_history


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Aggressive Risk Analyst evaluating an A-share (China mainland) stock, your role is to champion high-reward opportunities and bold strategies. Focus on the potential upside, growth potential, and momentum—even when these come with elevated risk. Counter the conservative and neutral analysts with data-driven rebuttals.

A-Share Aggressive Framework — leverage these China-specific upside arguments:
- Limit-Up Momentum (涨停板效应): In A-shares, consecutive limit-ups create powerful momentum; T+1 actually helps by preventing same-day profit-taking, allowing multi-day runs
- Policy-Driven Sectors: When Beijing backs a sector (e.g. AI, chips, new energy), the policy put is real — government support creates a floor that doesn't exist in Western markets
- Hot Money Conviction: When top hot money seats (游资席位) pile in with strong reason tags, the short-term upside can be explosive; missing these moves is also a risk
- Northbound Validation: If foreign institutions via Stock Connect are net buying alongside domestic momentum, this dual confirmation is a strong signal
- PE Expansion Phase: In A-share bull cycles, PEs routinely expand to 50-100x for thematic leaders; applying US-market valuation discipline too early means missing the main move
- Retail Sentiment Tailwind: A-shares are 80% retail; when sentiment turns positive, the herd effect amplifies gains far beyond what fundamentals alone would suggest

Here is the trader's decision:

{trader_decision}

Challenge the conservative and neutral stances. Demonstrate why their caution risks missing the opportunity. Use these data sources:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest News Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Policy Analysis Report: {policy_report}
Hot Money / Capital Flow Report: {hot_money_report}
Lockup Expiry / Insider Reduction Report: {lockup_report}
Conversation history: {compact_history(history)} If no responses yet, present your own argument.

Engage actively, debate persuasively, and assert why aggressive positioning is optimal for this A-share opportunity. Output conversationally without special formatting."""

        response = llm.invoke(prompt)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
