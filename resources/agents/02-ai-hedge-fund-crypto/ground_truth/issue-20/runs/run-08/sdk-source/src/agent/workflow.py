from typing import List
from langgraph.graph import END, StateGraph
from graph import AgentState, StartNode, DataNode, EmptyNode, RiskManagementNode, PortfolioManagementNode
from utils import import_strategy_class, Interval


class Workflow:
    @staticmethod
    def create_workflow(intervals: List[Interval], strategies: List[str]) -> StateGraph:
        """Create the workflow with Strategy."""
        workflow = StateGraph(AgentState)

        start_node = StartNode()
        workflow.add_node("start_node", start_node)

        merged_data_node = EmptyNode()
        workflow.add_node("merge_data_node", merged_data_node)

        for interval in intervals:
            node_name = f"{interval.value}_node"
            data_node = DataNode(interval)
            workflow.add_node(node_name, data_node)
            workflow.add_edge("start_node", node_name)
            workflow.add_edge(node_name, "merge_data_node")

        for strategy_node_name in strategies:
            strategy_class = import_strategy_class(f"src.strategies.{strategy_node_name}")
            strategy_instance = strategy_class()
            workflow.add_node(strategy_node_name, strategy_instance)
            workflow.add_edge("merge_data_node", strategy_node_name)

        # Always add risk and portfolio management
        risk_management_node = RiskManagementNode()
        portfolio_management_node = PortfolioManagementNode()
        workflow.add_node("risk_management_node", risk_management_node)
        workflow.add_node("portfolio_management_node", portfolio_management_node)
        #
        # # Connect selected analysts to risk management
        for strategy_node_name in strategies:
            workflow.add_edge(strategy_node_name, "risk_management_node")
        # #
        # workflow.add_edge("start_node", "risk_management_node")
        workflow.add_edge("risk_management_node", "portfolio_management_node")
        workflow.add_edge("portfolio_management_node", END)
        #
        workflow.set_entry_point("start_node")

        return workflow
