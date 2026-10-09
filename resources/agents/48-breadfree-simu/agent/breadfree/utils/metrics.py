import pandas as pd
import numpy as np
from typing import Tuple, Dict, List, Optional
from scipy import stats

def calculate_max_drawdown(equity_series: pd.Series) -> float:
    """
    Calculate maximum drawdown
    :param equity_series: Equity series
    :return: Maximum drawdown (negative value)
    """
    if equity_series.empty:
        return 0.0
    running_max = equity_series.cummax()
    drawdown = (equity_series - running_max) / running_max
    return float(drawdown.min())

def calculate_sharpe_ratio(equity_series: pd.Series, risk_free_rate: float = 0.02, annual_days: int = 242) -> float:
    """
    Calculate Sharpe ratio (based on daily returns)
    :param equity_series: Equity series
    :param risk_free_rate: Risk-free rate (annualized), default 2%
    :param annual_days: Number of trading days, A-shares typically around 242
    :return: Sharpe ratio
    """
    if len(equity_series) < 2:
        return 0.0
    
    # Calculate daily returns
    daily_returns = equity_series.pct_change().dropna()
    
    if daily_returns.std() == 0:
        return 0.0
        
    # Daily excess returns
    daily_rf = risk_free_rate / annual_days
    excess_returns = daily_returns - daily_rf
    
    # Annualized return / Annualized volatility
    sharpe = (excess_returns.mean() / daily_returns.std()) * (annual_days ** 0.5)
    return float(sharpe)

def calculate_total_return(equity_series: pd.Series, initial_capital: float = None) -> float:
    """
    Calculate total return
    :param equity_series: Equity series
    :param initial_capital: Initial capital (optional, if provided calculate based on initial capital, otherwise based on first value of series)
    """
    if equity_series.empty:
        return 0.0
    
    final_value = equity_series.iloc[-1]
    start_value = initial_capital if initial_capital is not None else equity_series.iloc[0]
    
    if start_value == 0:
        return 0.0
        
    return (final_value - start_value) / start_value

def calculate_annualized_return(equity_series: pd.Series, annual_days: int = 242) -> float:
    """
    Calculate annualized return
    """
    if len(equity_series) < 2:
        return 0.0
    
    total_return = (equity_series.iloc[-1] / equity_series.iloc[0]) - 1
    num_days = len(equity_series)
    if num_days == 0:
        return 0.0
        
    annualized_return = (1 + total_return) ** (annual_days / num_days) - 1
    return float(annualized_return)

def calculate_calmar_ratio(annual_return: float, max_drawdown: float, risk_free_rate: float = 0.02) -> float:
    """
    Calculate Calmar ratio (Annual Return / Max Drawdown)
    :param annual_return: Annualized return
    :param max_drawdown: Maximum drawdown (absolute value, positive)
    :param risk_free_rate: Risk-free rate
    :return: Calmar ratio
    """
    if max_drawdown == 0:
        return 0.0
    return float((annual_return - risk_free_rate) / abs(max_drawdown))

def calculate_sortino_ratio(equity_series: pd.Series, risk_free_rate: float = 0.02,
                           annual_days: int = 242, target_return: float = 0.0) -> float:
    """
    Calculate Sortino ratio (downside risk adjusted)
    :param equity_series: Equity series
    :param risk_free_rate: Risk-free rate
    :param annual_days: Annual trading days
    :param target_return: Target return (default 0)
    :return: Sortino ratio
    """
    if len(equity_series) < 2:
        return 0.0
    
    daily_returns = equity_series.pct_change().dropna()
    daily_target = target_return / annual_days
    daily_rf = risk_free_rate / annual_days
    
    # Calculate downside deviation (only for returns below target)
    downside_returns = daily_returns[daily_returns < daily_target] - daily_target
    if len(downside_returns) == 0:
        downside_std = 0
    else:
        downside_std = downside_returns.std()
    
    if downside_std == 0:
        return 0.0
    
    annualized_excess_return = (daily_returns.mean() - daily_rf) * annual_days
    sortino_ratio = annualized_excess_return / (downside_std * np.sqrt(annual_days))
    
    return float(sortino_ratio)

def calculate_information_ratio(portfolio_returns: pd.Series, 
                               benchmark_returns: pd.Series,
                               annual_days: int = 242) -> float:
    """
    Calculate Information Ratio (stability of excess returns)
    :param portfolio_returns: Portfolio return series (daily)
    :param benchmark_returns: Benchmark return series (daily)
    :param annual_days: Annual trading days
    :return: Information ratio
    """
    if len(portfolio_returns) != len(benchmark_returns) or len(portfolio_returns) < 2:
        return 0.0
    
    excess_returns = portfolio_returns - benchmark_returns
    if excess_returns.std() == 0:
        return 0.0
    
    info_ratio = (excess_returns.mean() / excess_returns.std()) * np.sqrt(annual_days)
    return float(info_ratio)

def calculate_alpha_beta(portfolio_returns: pd.Series,
                        benchmark_returns: pd.Series,
                        risk_free_rate: float = 0.02,
                        annual_days: int = 242) -> Tuple[float, float]:
    """
    Calculate Alpha and Beta coefficients
    :return: (Annualized Alpha, Beta)
    """
    if len(portfolio_returns) != len(benchmark_returns) or len(portfolio_returns) < 2:
        return 0.0, 1.0
    
    daily_rf = risk_free_rate / annual_days
    excess_portfolio = portfolio_returns - daily_rf
    excess_benchmark = benchmark_returns - daily_rf
    
    # Calculate Beta (Covariance / Variance)
    covariance = np.cov(excess_portfolio, excess_benchmark)[0, 1]
    benchmark_var = np.var(excess_benchmark)
    
    if benchmark_var == 0:
        beta = 1.0
    else:
        beta = covariance / benchmark_var
    
    # Calculate Alpha
    alpha_daily = excess_portfolio.mean() - beta * excess_benchmark.mean()
    alpha_annual = alpha_daily * annual_days
    
    return float(alpha_annual), float(beta)

def calculate_tracking_error(portfolio_returns: pd.Series,
                           benchmark_returns: pd.Series,
                           annual_days: int = 242) -> float:
    """
    Calculate Tracking Error (annualized)
    """
    if len(portfolio_returns) != len(benchmark_returns) or len(portfolio_returns) < 2:
        return 0.0
    
    excess_returns = portfolio_returns - benchmark_returns
    tracking_error = excess_returns.std() * np.sqrt(annual_days)
    
    return float(tracking_error)

def calculate_win_rate(trade_returns: List[float]) -> Tuple[float, int, int]:
    """
    Calculate win rate, win count, and total trades
    :param trade_returns: List of returns per trade
    :return: (Win rate, win count, total trades)
    """
    if not trade_returns:
        return 0.0, 0, 0
    
    wins = sum(1 for r in trade_returns if r > 0)
    total = len(trade_returns)
    win_rate = wins / total if total > 0 else 0.0
    
    return float(win_rate), wins, total

def calculate_profit_factor(gross_profits: float, gross_losses: float) -> float:
    """
    Calculate Profit Factor (Gross Profits / Gross Losses)
    """
    if gross_losses == 0:
        return float('inf') if gross_profits > 0 else 0.0
    return float(gross_profits / abs(gross_losses))

def calculate_average_win_loss(trade_returns: List[float]) -> Tuple[float, float]:
    """
    Calculate average profit and average loss
    """
    if not trade_returns:
        return 0.0, 0.0
    
    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r < 0]
    
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = np.mean(losses) if losses else 0.0
    
    return float(avg_win), float(avg_loss)

def calculate_max_consecutive_wins_losses(trade_returns: List[float]) -> Tuple[int, int]:
    """
    Calculate maximum consecutive wins and losses
    """
    if not trade_returns:
        return 0, 0
    
    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0
    
    for ret in trade_returns:
        if ret > 0:
            current_wins += 1
            current_losses = 0
            max_wins = max(max_wins, current_wins)
        elif ret < 0:
            current_losses += 1
            current_wins = 0
            max_losses = max(max_losses, current_losses)
    
    return max_wins, max_losses

def calculate_r_squared(portfolio_returns: pd.Series, 
                       benchmark_returns: pd.Series) -> float:
    """
    Calculate R-squared (goodness of fit)
    """
    if len(portfolio_returns) != len(benchmark_returns) or len(portfolio_returns) < 2:
        return 0.0
    
    # Use linear regression for R-squared
    slope, intercept, r_value, p_value, std_err = stats.linregress(
        benchmark_returns, portfolio_returns
    )
    
    return float(r_value ** 2)

def calculate_volatility(returns_series: pd.Series, annual_days: int = 242) -> float:
    """
    Calculate annualized volatility
    """
    if len(returns_series) < 2:
        return 0.0
    
    return float(returns_series.std() * np.sqrt(annual_days))

def calculate_value_at_risk(returns_series: pd.Series, 
                           confidence_level: float = 0.95,
                           method: str = 'historical') -> float:
    """
    Calculate Value at Risk (VaR)
    :param confidence_level: Confidence level
    :param method: Method - 'historical' or 'parametric'
    :return: VaR value (negative denotes loss)
    """
    if len(returns_series) < 2:
        return 0.0
    
    if method == 'historical':
        # Historical simulation
        var = np.percentile(returns_series, (1 - confidence_level) * 100)
    else:
        # Parametric method (Assuming normal distribution)
        mean = returns_series.mean()
        std = returns_series.std()
        from scipy.stats import norm
        var = norm.ppf(1 - confidence_level, mean, std)
    
    return float(var)

def calculate_conditional_var(returns_series: pd.Series,
                            confidence_level: float = 0.95) -> float:
    """
    Calculate Conditional Value at Risk (CVaR / Expected Shortfall)
    Represents the average loss exceeding VaR
    """
    if len(returns_series) < 2:
        return 0.0
    
    var = calculate_value_at_risk(returns_series, confidence_level, 'historical')
    cvar = returns_series[returns_series <= var].mean()
    
    return float(cvar)

def calculate_skewness_kurtosis(returns_series: pd.Series) -> Tuple[float, float]:
    """
    Calculate skewness and kurtosis of returns series
    """
    if len(returns_series) < 2:
        return 0.0, 0.0
    
    skewness = float(returns_series.skew())
    kurtosis = float(returns_series.kurtosis())  # Excess kurtosis
    
    return skewness, kurtosis

def calculate_jensen_alpha(portfolio_returns: pd.Series,
                          benchmark_returns: pd.Series,
                          risk_free_rate: float = 0.02,
                          annual_days: int = 242) -> float:
    """
    Calculate Jensen's Alpha (based on CAPM)
    """
    alpha, beta = calculate_alpha_beta(
        portfolio_returns, benchmark_returns, risk_free_rate, annual_days
    )
    return alpha

def calculate_ulcer_index(equity_series: pd.Series) -> float:
    """
    Calculate Ulcer Index (measures downside volatility)
    """
    if len(equity_series) < 2:
        return 0.0
    
    running_max = equity_series.cummax()
    drawdown = ((equity_series - running_max) / running_max) * 100
    squared_dd = drawdown ** 2
    
    ulcer_index = np.sqrt(squared_dd.mean())
    return float(ulcer_index)

def calculate_omega_ratio(returns_series: pd.Series,
                         threshold: float = 0.0) -> float:
    """
    Calculate Omega Ratio (probability-weighted ratio of gains vs losses)
    """
    if len(returns_series) < 2:
        return 0.0
    
    gains = returns_series[returns_series > threshold] - threshold
    losses = threshold - returns_series[returns_series < threshold]
    
    if len(losses) == 0 or losses.sum() == 0:
        return float('inf')
    
    omega = gains.sum() / losses.sum()
    return float(omega)

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """
    Calculate Exponential Moving Average (EMA)
    :param series: Input series
    :param period: EMA period
    :return: EMA series
    """
    return series.ewm(span=period, adjust=False).mean()

def calculate_macd(series: pd.Series,
                   short_period: int = 12,
                   long_period: int = 26,
                   signal_period: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate MACD indicators
    :param series: Input series
    :param short_period: Short EMA period
    :param long_period: Long EMA period
    :param signal_period: Signal line EMA period
    :return: (MACD line, Signal line, Histogram)
    """
    ema_short = calculate_ema(series, short_period)
    ema_long = calculate_ema(series, long_period)
    
    macd_line = ema_short - ema_long
    signal_line = calculate_ema(macd_line, signal_period)
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram

def calculate_all_metrics(equity_series: pd.Series,
                         trade_returns: List[float] = None,
                         benchmark_returns: pd.Series = None,
                         risk_free_rate: float = 0.02,
                         annual_days: int = 242) -> Dict:
    """
    Comprehensive function to calculate all performance metrics
    """
    metrics = {}
    
    # Base return metrics
    metrics['total_return'] = calculate_total_return(equity_series)
    metrics['annualized_return'] = calculate_annualized_return(equity_series, annual_days)
    metrics['max_drawdown'] = calculate_max_drawdown(equity_series)
    
    # Risk-adjusted return metrics
    daily_returns = equity_series.pct_change().dropna() if len(equity_series) > 1 else pd.Series()
    if not daily_returns.empty:
        metrics['sharpe_ratio'] = calculate_sharpe_ratio(equity_series, risk_free_rate, annual_days)
        metrics['sortino_ratio'] = calculate_sortino_ratio(equity_series, risk_free_rate, annual_days)
        metrics['calmar_ratio'] = calculate_calmar_ratio(equity_series, risk_free_rate, annual_days)
        metrics['volatility'] = calculate_volatility(daily_returns, annual_days)
        
        # Distribution characteristics
        metrics['skewness'], metrics['kurtosis'] = calculate_skewness_kurtosis(daily_returns)
        
        # Risk metrics
        metrics['var_95'] = calculate_value_at_risk(daily_returns, 0.95)
        metrics['cvar_95'] = calculate_conditional_var(daily_returns, 0.95)
        metrics['ulcer_index'] = calculate_ulcer_index(equity_series)
        metrics['omega_ratio'] = calculate_omega_ratio(daily_returns)
    
    # Trade statistics
    if trade_returns:
        win_rate, wins, total = calculate_win_rate(trade_returns)
        metrics['win_rate'] = win_rate
        metrics['total_trades'] = total
        metrics['profit_trades'] = wins
        metrics['loss_trades'] = total - wins
        
        avg_win, avg_loss = calculate_average_win_loss(trade_returns)
        metrics['avg_win'] = avg_win
        metrics['avg_loss'] = avg_loss
        
        if avg_loss != 0:
            metrics['win_loss_ratio'] = abs(avg_win / avg_loss)
        else:
            metrics['win_loss_ratio'] = float('inf')
        
        # Calculate gross profit and loss
        gross_profits = sum(r for r in trade_returns if r > 0)
        gross_losses = sum(r for r in trade_returns if r < 0)
        metrics['gross_profit'] = gross_profits
        metrics['gross_loss'] = gross_losses
        metrics['profit_factor'] = calculate_profit_factor(gross_profits, gross_losses)
        
        # Consecutive statistics
        max_wins, max_losses = calculate_max_consecutive_wins_losses(trade_returns)
        metrics['max_consecutive_wins'] = max_wins
        metrics['max_consecutive_losses'] = max_losses
    
    # Relative benchmark metrics
    if benchmark_returns is not None and not daily_returns.empty:
        metrics['information_ratio'] = calculate_information_ratio(
            daily_returns, benchmark_returns, annual_days
        )
        metrics['alpha'], metrics['beta'] = calculate_alpha_beta(
            daily_returns, benchmark_returns, risk_free_rate, annual_days
        )
        metrics['tracking_error'] = calculate_tracking_error(
            daily_returns, benchmark_returns, annual_days
        )
        metrics['r_squared'] = calculate_r_squared(daily_returns, benchmark_returns)
        metrics['jensen_alpha'] = calculate_jensen_alpha(
            daily_returns, benchmark_returns, risk_free_rate, annual_days
        )
    
    return metrics

def calculate_profit_loss_ratio(trade_returns: List[float]) -> float:
    """
    Calculate Profit/Loss ratio (average profit / average loss)
    :param trade_returns: List of returns per trade
    :return: Profit/Loss ratio
    """
    avg_win, avg_loss = calculate_average_win_loss(trade_returns)
    if avg_loss == 0:
        return float('inf') if avg_win > 0 else 0.0
    return float(avg_win / abs(avg_loss))

def stable_linear_regression(prices: np.ndarray) -> Tuple[float, float, float]:
    """
    Perform a stable linear regression using numpy vectorization.
    :param prices: Array of prices
    :return: (slope, intercept, r2)
    """
    n = len(prices)
    if n < 2:
        return 0.0, 0.0, 0.0
    try:
        x = np.arange(n)
        
        x_mean = np.mean(x)
        y_mean = np.mean(prices)
        
        numerator = np.sum((x - x_mean) * (prices - y_mean))
        denominator = np.sum((x - x_mean) ** 2)
        
        if denominator == 0:
            return 0.0, 0.0, 0.0
            
        slope = numerator / denominator
        intercept = y_mean - slope * x_mean
        
        # R2 Calculation
        y_pred = slope * x + intercept
        ss_res = np.sum((prices - y_pred) ** 2)
        ss_tot = np.sum((prices - y_mean) ** 2)
        
        if ss_tot == 0:
             r2 = 0.0
        else:
             r2 = 1 - (ss_res / ss_tot)
             
        return slope, intercept, r2
    except Exception:
        return 0.0, 0.0, 0.0

def calculate_efficiency_metrics(history: List[float], lookback: int) -> Optional[Dict[str, float]]:
    """
    Calculate momentum, volatility, R2 and efficiency for a given price history.
    """
    if len(history) < lookback:
        return None
    prices = np.array(history[-lookback:])
    if len(prices) < 2:
        return None
        
    momentum = (prices[-1] / prices[0] - 1) if prices[0] > 0 else 0
    returns = np.diff(prices) / prices[:-1]
    volatility = np.std(returns) if len(returns) > 1 else 0

    # Scale daily volatility to the full period volatility
    period_volatility = volatility * np.sqrt(len(returns))

    slope, _, r2 = stable_linear_regression(prices)
    epsilon = 1e-6
    
    # Efficiency factor: risk-adjusted momentum scaled by trend quality (R2)
    efficiency = (momentum / (period_volatility + epsilon)) * r2
    
    return {
        "momentum": momentum,
        "volatility": volatility,
        "r2": r2,
        "efficiency": efficiency,
        "close": float(prices[-1])
    }

# 使用示例
if __name__ == "__main__":
    # 创建示例数据
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    np.random.seed(42)
    
    # 模拟净值曲线
    returns = np.random.normal(0.0005, 0.02, 100)
    equity = 1000000 * (1 + returns).cumprod()
    equity_series = pd.Series(equity, index=dates)
    
    # 模拟交易记录
    trade_returns = np.random.normal(0.001, 0.05, 50).tolist()
    
    # 模拟基准
    benchmark_returns = pd.Series(np.random.normal(0.0003, 0.015, 100), index=dates)
    
    # 计算所有指标
    metrics = calculate_all_metrics(
        equity_series=equity_series,
        trade_returns=trade_returns,
        benchmark_returns=benchmark_returns,
        risk_free_rate=0.02,
        annual_days=242
    )
    
    # 打印结果
    print("=== Performance Metrics Summary ===")
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"{key:25s}: {value:.4f}")
        else:
            print(f"{key:25s}: {value}")