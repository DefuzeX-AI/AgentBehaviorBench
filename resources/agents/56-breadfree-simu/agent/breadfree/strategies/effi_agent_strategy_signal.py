from typing import TypedDict, List, Dict, Any, Optional, Literal
import pandas as pd
import numpy as np
import json
import re
import asyncio
from langgraph.graph import StateGraph, END
from collections import defaultdict
from .base_strategy import BreadFreeStrategy
from ..utils.llm_client import async_hunyuan_chat, parse_llm_response
from ..utils.metrics import calculate_efficiency_metrics
from ..utils.portfolio import normalize_weights

# --- Prompts ---

ANALYST_PROMPT = """
You are a Senior Quantitative ETF Analyst.
Your goal is to select the best assets for a "Rotation Strategy" based on provided technical metrics.

Strategy Definition:
- We want to buy ETFs with high Momentum (Return) and high Trend Stability (Efficiency/R2).
- We avoid high volatility if the return is not commensurate.
- You may select **any number of ETFs** (including zero) that you believe are suitable — do not force diversification if only one asset is strong, or go to cash if none are attractive.
- You can choose [bullish, neutral, bearish] viewpoints, and based on your judgment of the indicators, provide the corresponding confidence level (1-5).

Market Data (Top3 Candidates + Current Holdings 20day metrics):
{market_data_summary}

Task:
1. Analyze the candidates thoroughly. Note: "[HOLDING: qty]" indicates your current position in that asset.
2. Select the ETFs you believe should be held for the next period (0 to N symbols).
3. Provide a brief reason for your selection(s) based on the metrics.

Output Format (JSON):
{{
    "code1": {{"confidence": 3, "view": "bullish", "reason": "Consistent trend..."}},
    "code2": {{"confidence": 4, "view": "bearish", "reason": "Trend weakening, high volatility..."}}
}}
"""

RISK_MANAGER_PROMPT = """
You are a Risk Manager.
The Analyst has submitted the following analysis: {analyst_proposal} (which includes the analyst's views and confidence level (1-5) regarding the asset).

Current Portfolio State:
- Cash: {cash}
- Current Holdings: {positions}

Task:
1. Review the analyst's views for each asset provided in the analysis.
2. Determine the final target weights (sum <= 1.0) for the next period. A total sum less than 1 indicates holding a portion of cash.
3. You can reduce weights or hold cash if overall market conditions in the analyst's report look risky.
4. You should take into account the transaction costs and market liquidity of the A-share market. Do not frequently adjust your position when the signals are not clear enough; if the target stock indicators are not significantly different from your current holdings, there is no need to make any adjustments.

Output Format (JSON):
{{
    "target_weights": {{ "code1": 0.4, "code2": 0.0 }},
    "risk_comment": "Enforced exit on code2 due to bearish outlook...",
    "approved": true
}}
"""

# --- State Definition ---

class AgentState(TypedDict):
    date: str
    bars: Dict[str, Any]
    history_snapshot: Dict[str, List[float]]
    metrics: Dict[str, Dict[str, float]]
    broker_state: str
    cash: float
    positions: Dict[str, Any]
    analyst_output: Dict[str, Any]
    risk_output: Dict[str, Any]
    lot_size: int
    target_weights: Dict[str, float]
    holding_negative_streak: Dict[str, int]
    needs_rebalance: bool

# --- Helper Functions (Math) ---

def get_fallback_weights(metrics: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    if not metrics:
        return {}
    valid = {s: m for s, m in metrics.items() if m["efficiency"] > 0}
    if not valid:
        return {}
    sorted_symbols = sorted(valid.keys(), key=lambda x: valid[x]["efficiency"], reverse=True)
    selected = sorted_symbols[:5]
    weight = 1.0 / len(selected)
    return {s: weight for s in selected}

# --- Nodes ---

def data_analyst_node(state: AgentState) -> AgentState:
    history_snapshot = state.get("history_snapshot", {})
    positions = state.get("positions", {})
    streak_map = state.get("holding_negative_streak", {})
    
    metrics_map = {}
    for symbol, prices in history_snapshot.items():
        m = calculate_efficiency_metrics(prices, lookback=20)
        if m:
            metrics_map[symbol] = m
            
    # Get top 3 assets by efficiency ranking
    sorted_symbols = sorted(metrics_map.keys(), key=lambda x: metrics_map[x]["efficiency"], reverse=True)
    top_3 = sorted_symbols[:3]

    # Get current holdings
    current_holdings = [s for s, qty in positions.items() if qty > 0]

    # --- Analyze Signals ---
    trigger_streak = False
    new_streak_map = streak_map.copy()
    
    # 1. Clean up streak map for assets no longer held
    for s in list(new_streak_map.keys()):
        if s not in current_holdings:
            del new_streak_map[s]

    min_holding_efficiency = float('inf')
    
    # 2. Update streaks for current holdings & find min efficiency
    for symbol in current_holdings:
        eff = metrics_map.get(symbol, {}).get("efficiency", 0)
        if eff < min_holding_efficiency:
            min_holding_efficiency = eff
            
        if eff < 0:
            new_streak_map[symbol] = new_streak_map.get(symbol, 0) + 1
        else:
            new_streak_map[symbol] = 0
            
        if new_streak_map[symbol] >= 3:
            print(f"[DataAnalyst] Trigger: {symbol} has negative efficiency ({eff:.2f}) for {new_streak_map[symbol]} consecutive days.")
            trigger_streak = True

    # 3. Check Top 3 vs Holdings (Efficiency > 200% of lowest holding)
    trigger_opportunity = False
    
    if not current_holdings:
        # If cash only, trigger if we have decent candidates
        if any(metrics_map.get(c, {}).get("efficiency", 0) > 0.5 for c in top_3):
            trigger_opportunity = True
    elif min_holding_efficiency != float('inf'):
        # Threshold logic: if holding is negative, we just need a good positive substitute (e.g. > 0.5)
        # If holding is positive, we need 100% improvement (2x).
        threshold = 0.5 if min_holding_efficiency <= 0 else min_holding_efficiency * 2.0
        
        for cand in top_3:
            if cand not in current_holdings:
                cand_eff = metrics_map.get(cand, {}).get("efficiency", 0)
                if cand_eff > threshold:
                    print(f"[DataAnalyst] Trigger: Candidate {cand} ({cand_eff:.2f}) exceeds lowest holding efficiency ({min_holding_efficiency:.2f}) by significant margin.")
                    trigger_opportunity = True
                    break

    needs_rebalance = trigger_streak or trigger_opportunity

    # Combine and maintain deterministic order
    selected_symbols = top_3 + [s for s in current_holdings if s not in top_3]

    # Filter metrics
    filtered_metrics = {k: metrics_map[k] for k in selected_symbols if k in metrics_map}

    # Add holding markers
    for symbol in filtered_metrics:
        is_holding = symbol in current_holdings
        filtered_metrics[symbol]["is_current_holding"] = is_holding
        if is_holding:
            filtered_metrics[symbol]["holding_qty"] = positions[symbol]
    
    print(f"[DataAnalyst] Top 3: {top_3}. Rebalance Needed: {needs_rebalance}")
    return {
        "metrics": filtered_metrics, 
        "holding_negative_streak": new_streak_map,
        "needs_rebalance": needs_rebalance
    }

async def technical_analyst_node(state: AgentState) -> AgentState:
    metrics = state["metrics"]
    if not metrics:
        print("[TechAnalyst] Empty metrics, returning fallback")
        return {"analyst_output": {}}
    
    # Sort by Efficiency
    sorted_metrics_items = sorted(metrics.items(), key=lambda x: x[1].get('efficiency', 0), reverse=True)
    
    summary_lines = []
    for sym, data in sorted_metrics_items:
        holding_info = f" [HOLDING: {data['holding_qty']}]" if data.get("is_current_holding") else ""
        line = (f"- {sym}: Return={data['momentum']:.2%}, "
                f"Vol={data['volatility']:.2%}, "
                f"R2={data['r2']:.2f}, "
                f"Efficiency={data['efficiency']:.2f}{holding_info}")
        summary_lines.append(line)
    summary_text = "\n".join(summary_lines)
    print(f"[TechAnalyst] Sorted Market Data Summary:\n{summary_text}")
    prompt = ANALYST_PROMPT.format(market_data_summary=summary_text)
    
    fallback = {}
    fallback_weights = get_fallback_weights(metrics)
    for s, w in fallback_weights.items():
        fallback[s] = {"weight": w, "view": "bullish", "reason": "top efficiency"}
    
    try:
        response, _ = await async_hunyuan_chat(query="Technical analysis for ETF rotation.", prompt=prompt)
        analyst_decision = parse_llm_response(response, fallback)
    except Exception as e:
        print(f"[TechAnalyst ERROR] {e}")
        analyst_decision = fallback

    proposed = {s: (v.get("confidence") if isinstance(v, dict) else 0) for s, v in analyst_decision.items()}
    print(f"[TechAnalyst] Analysis Complete. Proposed Confidence: {proposed}")
    return {"analyst_output": analyst_decision}

async def risk_manager_node(state: AgentState) -> AgentState:
    analyst_output = state.get("analyst_output", {})
    if not analyst_output:
        print("[Risk Manager] 按兵不动，维持原有仓位（按当前持仓市值比例分配权重）")
        return {"risk_output": {}, "target_weights": {}}
    
    prompt = RISK_MANAGER_PROMPT.format(
        analyst_proposal=json.dumps(analyst_output),
        cash=f"{state['cash']:.2f}",
        positions=str(state['positions'])
    )
    fallback_weights = get_fallback_weights(state.get("metrics", {}))
    fallback = {"target_weights": fallback_weights, "approved": True}
    try:
        response, _ = await async_hunyuan_chat(query="Assess risk and allocate weights.", prompt=prompt)
        risk_decision = parse_llm_response(response, fallback)
    except Exception as e:
        print(f"[Risk ERROR] {e}")
        risk_decision = {"target_weights": {}, "approved": False}
        
    target_weights = risk_decision.get("target_weights", {})
    if not target_weights or sum(target_weights.values()) <= 0:
        # 按兵不动，维持原有仓位（按当前持仓市值比例分配权重）
        total_value = sum(state['positions'][s] * state['bars'][s]['close'] for s in state['positions'] if s in state['bars'])
        if total_value > 0:
            target_weights = {s: (state['positions'][s] * state['bars'][s]['close']) / total_value for s in state['positions'] if s in state['bars']}
        else:
            target_weights = {}
        
    target_weights = normalize_weights(target_weights)
    risk_decision["target_weights"] = target_weights
    print(f"[Risk Final] target_weights={target_weights}")
    return {"risk_output": risk_decision, "target_weights": target_weights}

# --- Graph Construction ---

def check_rebalance(state: AgentState) -> Literal["technical_analyst", "end"]:
    if state.get("needs_rebalance", False):
        return "technical_analyst"
    return "end"

def build_agent_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("data_analyst", data_analyst_node)
    workflow.add_node("technical_analyst", technical_analyst_node)
    workflow.add_node("risk_manager", risk_manager_node)
    
    workflow.set_entry_point("data_analyst")
    
    workflow.add_conditional_edges(
        "data_analyst",
        check_rebalance,
        {
            "technical_analyst": "technical_analyst",
            "end": END
        }
    )
    
    workflow.add_edge("technical_analyst", "risk_manager")
    workflow.add_edge("risk_manager", END)
    return workflow.compile()

# --- Strategy Class ---

class EffiAgentRotationStrategy(BreadFreeStrategy):
    def __init__(self, broker, lookback_period=20, hold_period=1, lot_size=100, **kwargs):
        super().__init__(broker, lot_size=lot_size)
        self.lookback_period = lookback_period
        self.hold_period = 1 # Force daily check
        self.days_counter = 0
        self.app = build_agent_graph()
        self.holding_negative_streak = defaultdict(int) 
        
    def on_bar(self, date, bars):
        for symbol, bar in bars.items():
            if symbol not in self.history:
                self.history[symbol] = []
            self.history[symbol].append(bar['close'])
        
        not_ready_symbols = [s for s in self.broker_positions_and_pool(bars) if len(self.history.get(s, [])) < self.lookback_period]
        data_ready = len(not_ready_symbols) == 0
        
        if not data_ready:
            print(f"[INFO] Data not ready on {date}. Missing lookback for: {not_ready_symbols}")
            return

        # Trigger Agents Every Trading Day (Data Analyst determines if we proceed)
        print(f"[INFO] Agents Triggered on {date}")
        
        history_snapshot = {s: list(self.history[s]) for s in bars.keys()}
        pos_snapshot = {s: getattr(self.broker.positions[s], 'quantity', self.broker.positions[s])
                        if s in self.broker.positions else 0
                        for s in self.broker.positions}
        
        initial_state = {
            "date": str(date),
            "bars": bars,
            "history_snapshot": history_snapshot,
            "metrics": {},
            "cash": self.broker.cash,
            "positions": pos_snapshot,
            "analyst_output": {},
            "risk_output": {},
            "lot_size": self.lot_size,
            "target_weights": {},
            "holding_negative_streak": dict(self.holding_negative_streak),
            "needs_rebalance": False
        }
        
        try:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    final_state = loop.run_until_complete(self.app.ainvoke(initial_state))
                else:
                    final_state = asyncio.run(self.app.ainvoke(initial_state))
            except RuntimeError:
                final_state = asyncio.run(self.app.ainvoke(initial_state))
            
            # Persist streak state
            updated_streak = final_state.get("holding_negative_streak", {})
            self.holding_negative_streak = defaultdict(int, updated_streak)

            if final_state.get("needs_rebalance", False):
                print(f"[GRAPH DONE] Rebalance Triggered. target_weights = {final_state.get('target_weights')}")
                self._execute_trades(date, final_state.get("target_weights", {}), bars)
            else:
                print("[GRAPH] No rebalance triggered.")
            
        except Exception as e:
            print(f"[GRAPH ERROR] {e}")
            import traceback
            traceback.print_exc()

    def broker_positions_and_pool(self, current_bars):
        return list(set(list(self.broker.positions.keys()) + list(current_bars.keys())))

    def _execute_trades(self, date, target_weights: Dict[str, float], bars):
        if not target_weights:
            pass

        # print(f"[EXECUTE] Allocation: {target_weights}")
        
        total_asset_value = self.broker.cash
        for s, pos in self.broker.positions.items():
            price = bars.get(s, {}).get('close', 0)
            qty = getattr(pos, 'quantity', pos) if hasattr(pos, 'quantity') else pos
            if price > 0:
                total_asset_value += qty * price
                
        # Sell first
        current_holdings = list(self.broker.positions.keys())
        for symbol in current_holdings:
            pos_obj = self.broker.positions[symbol]
            current_qty = getattr(pos_obj, 'quantity', pos_obj) if hasattr(pos_obj, 'quantity') else pos_obj
            price = bars.get(symbol, {}).get('close', 0)
            if price == 0:
                continue
            target_pct = target_weights.get(symbol, 0.0)
            target_val = total_asset_value * target_pct
            target_qty = int(target_val / price / self.lot_size) * self.lot_size
            if current_qty > target_qty:
                sell_qty = current_qty - target_qty
                self.broker.sell(date, symbol, price, sell_qty)
                print(f"[SELL] {symbol}: {sell_qty}")

        # Buy after
        current_cash = self.broker.cash
        for symbol, weight in target_weights.items():
            if symbol not in bars:
                continue
            price = bars[symbol]['close']
            target_val = total_asset_value * weight
            pos_obj = self.broker.positions.get(symbol, None)
            if pos_obj is not None:
                current_qty = getattr(pos_obj, 'quantity', pos_obj) if hasattr(pos_obj, 'quantity') else pos_obj
            else:
                current_qty = 0
            target_qty = int(target_val / price / self.lot_size) * self.lot_size
            if target_qty > current_qty:
                buy_qty = target_qty - current_qty
                cost = buy_qty * price
                if current_cash >= cost:
                    self.broker.buy(date, symbol, price, buy_qty)
                    current_cash -= cost
                    print(f"[BUY] {symbol}: {buy_qty}")
                else:
                    print(f"[WARN] Not enough cash to buy {symbol}") 

        # 汇报当前收益情况
        total_value = self.broker.cash
        for s, pos in self.broker.positions.items():
            price = bars.get(s, {}).get('close', 0)
            qty = getattr(pos, 'quantity', pos) if hasattr(pos, 'quantity') else pos
            if price > 0:
                total_value += qty * price
        print(f"[PORTFOLIO] Total Asset Value after trades: {total_value:.2f}, Cash: {self.broker.cash:.2f}")