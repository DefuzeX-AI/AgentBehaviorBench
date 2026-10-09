import sys
import os
import argparse
from datetime import datetime, timedelta

# Add the project root to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from breadfree.engine.backtest_engine import BacktestEngine
from breadfree.strategies.ma_strategy import DoubleMAStrategy
from breadfree.strategies.agent_strategy import AgentStrategy
from breadfree.strategies.benchmark_strategy import BenchmarkStrategy
from breadfree.strategies.effi_rotation_strategy import RotationStrategy
from breadfree.strategies.effi_agent_strategy import EffiAgentRotationStrategy
from breadfree.strategies.triple_momentum_strategy import TripleMomentumStrategy

def main():
    # 1. Define command line arguments
    parser = argparse.ArgumentParser(description='BreadFree Backtest Engine')
    parser.add_argument('--strategy', type=str, help='Strategy name', choices=[
        'DoubleMAStrategy', 'BenchmarkStrategy', 'AgentStrategy', 'RotationStrategy', 'EffiA', 'TripleMomentumStrategy'
    ])
    parser.add_argument('--start_date', type=str, help='Start date YYYYMMDD')
    parser.add_argument('--end_date', type=str, help='End date YYYYMMDD')
    parser.add_argument('--initial_cash', type=float, help='Initial cash')
    parser.add_argument('--lookback_period', type=int, help='Rebalancing lookback period', default=20)
    parser.add_argument('--hold_period', type=int, help='Holding period', default=20)
    parser.add_argument('--top_n', type=int, help='Number of assets to hold', )
    parser.add_argument('--min_momentum', type=float, help='Minimum momentum threshold')

    # Triple Momentum Strategy Arguments
    parser.add_argument('--bias_n', type=int, help='Bias MA window')
    parser.add_argument('--momentum_day', type=int, help='Momentum regression window')
    parser.add_argument('--slope_n', type=int, help='Slope and efficiency window')
    parser.add_argument('--rebalance_threshold', type=float, help='Rebalance threshold multiplier')

    parser.add_argument('--use_efficiency', type=bool, choices=[True, False], help='Whether to enable efficiency score', default=True)

    parser.add_argument('--output_file', type=str, default='', help='Output PNG filename')
    
    args = parser.parse_args()

    # 2. Read configuration file
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "breadfree", "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    # 3. Parameter priority: command line arguments > config file > default values
    strategy_name = args.strategy or config.get("strategy", "RotationStrategy")
    start_date = args.start_date or config.get("start_date", datetime.now().strftime("%Y%m%d"))
    end_date = args.end_date or config.get("end_date", (datetime.now() - timedelta(days=30)).strftime("%Y%m%d"))
    initial_cash = args.initial_cash or config.get("initial_cash", 100000.0)
    asset_type = config.get("asset_type", "stock")
    lot_size = config.get("lot_size", 100)
    data_source = config.get("data_source", "akshare")
    tushare_token = config.get("tushare_token", None)
    symbols = list(config.get("etf_pool", {"510300": "CSI300ETF"}).keys())  # Default ETFs

    # Strategy class selection
    strategy_map = {
        "DoubleMAStrategy": DoubleMAStrategy,
        "BenchmarkStrategy": BenchmarkStrategy,
        "AgentStrategy": AgentStrategy,
        "RotationStrategy": RotationStrategy,
        "EffiA": EffiAgentRotationStrategy,
        "TripleMomentumStrategy": TripleMomentumStrategy
    }
    # Print current experiment hyperparameters
    print(f"Strategy: {strategy_name}")
    print(f"Start Date: {start_date}, End Date: {end_date}, Initial Cash: {initial_cash}")
    print(f"Data Source: {data_source}")
    print(f"Symbols: {symbols}")
    print("Hyperparameters:")
    for param in ["lookback_period", "hold_period", "top_n", "min_momentum", "use_efficiency"]:
        val = getattr(args, param)
        if val is not None:
            print(f"  {param}: {val}")
    strategy_cls = strategy_map.get(strategy_name, RotationStrategy)

    print(f"Running backtest with {strategy_cls.__name__}...")

    # Extract strategy parameters (configurations other than common parameters)
    # Strategy parameter mapping
    strategy_params = {}
    
    # Manually map potential hyperparameters
    param_keys = [
        "lookback_period", "hold_period", "top_n", 
        "bias_n", "momentum_day", "slope_n", "rebalance_threshold"
    ]
    for key in param_keys:
        val = getattr(args, key)
        if val is not None:
            strategy_params[key] = val
        elif key in config:
            strategy_params[key] = config[key]
            
    # Special handling for boolean values
    if args.use_efficiency is not None:
        strategy_params["use_efficiency"] = args.use_efficiency == True
    elif "use_efficiency" in config:
        strategy_params["use_efficiency"] = config["use_efficiency"]

    # Create and run backtest
    # Note: BacktestEngine now accepts symbols list
    engine = BacktestEngine(
        strategy_cls=strategy_cls,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        asset_type=asset_type,
        lot_size=lot_size,
        data_source=data_source,
        tushare_token=tushare_token,
        **strategy_params
    )
    engine.run()

    # Plot results (generates HTML file)
    try:
        if args.output_file!='':
            # engine.plot_results_png(args.output_file)
            engine.plot_results_html()
    except Exception as e:
        print(f"Could not plot results: {e}")

if __name__ == "__main__":
    main()
