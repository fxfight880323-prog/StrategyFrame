"""
CTA Strategy Evaluation System
===============================

Core Functions:
1. Performance metrics (Sharpe, Sortino, Information Ratio, etc.)
2. Risk metrics (VaR, CVaR, Max Drawdown, etc.)
3. Strategy comparison
4. Attribution analysis
"""

import sys
import io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except ValueError:
    pass

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from scipy import stats
from scipy.stats import norm, skew, kurtosis
import warnings
warnings.filterwarnings('ignore')


@dataclass
class PerformanceMetrics:
    strategy_name: str
    start_date: date
    end_date: date
    trading_days: int
    
    total_return: float
    annualized_return: float
    cagr: float
    
    annualized_volatility: float
    downside_volatility: float
    max_drawdown: float
    max_drawdown_duration: int
    var_95: float
    cvar_95: float
    
    sharpe_ratio: float
    sortino_ratio: float
    information_ratio: float
    calmar_ratio: float
    omega_ratio: float
    serenity_ratio: float
    
    win_rate: float
    profit_loss_ratio: float
    avg_win: float
    avg_loss: float
    expectancy: float
    skewness: float
    kurtosis_val: float
    
    alpha: float
    beta: float
    correlation_to_benchmark: float
    up_capture: float
    down_capture: float
    
    daily_returns: pd.Series = field(default=None)
    cumulative_returns: pd.Series = field(default=None)
    drawdown_series: pd.Series = field(default=None)


class CTAEvaluator:
    def __init__(self, risk_free_rate: float = 0.03):
        self.risk_free_rate = risk_free_rate
    
    def evaluate(self, 
                 returns: pd.Series,
                 strategy_name: str = "Strategy",
                 benchmark_returns: pd.Series = None) -> PerformanceMetrics:
        returns = returns.dropna()
        if len(returns) < 30:
            raise ValueError("Insufficient return data (need at least 30 days)")
        
        start_date = returns.index[0]
        end_date = returns.index[-1]
        trading_days = len(returns)
        years = trading_days / 252
        
        total_return = (1 + returns).prod() - 1
        annualized_return = (1 + total_return) ** (1/years) - 1 if years > 0 else 0
        cagr = annualized_return
        
        daily_vol = returns.std()
        annualized_vol = daily_vol * np.sqrt(252)
        downside_vol = returns[returns < 0].std() * np.sqrt(252) if len(returns[returns < 0]) > 0 else 0
        
        cum_returns = (1 + returns).cumprod()
        running_max = cum_returns.cummax()
        drawdown = (cum_returns - running_max) / running_max
        max_drawdown = drawdown.min()
        max_dd_duration = self._calculate_max_drawdown_duration(drawdown)
        
        var_95 = np.percentile(returns, 5)
        cvar_95 = returns[returns <= var_95].mean() if len(returns[returns <= var_95]) > 0 else var_95
        
        excess_return = annualized_return - self.risk_free_rate
        sharpe = excess_return / annualized_vol if annualized_vol > 0 else 0
        sortino = excess_return / downside_vol if downside_vol > 0 else 0
        calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0
        omega = self._calculate_omega_ratio(returns)
        serenity = self._calculate_serenity_ratio(returns, max_drawdown)
        
        if benchmark_returns is not None:
            ir = self._calculate_information_ratio(returns, benchmark_returns)
            alpha, beta = self._calculate_alpha_beta(returns, benchmark_returns)
            correlation = returns.corr(benchmark_returns)
            up_capture = self._calculate_capture_ratio(returns, benchmark_returns, 'up')
            down_capture = self._calculate_capture_ratio(returns, benchmark_returns, 'down')
        else:
            ir = 0
            alpha = annualized_return
            beta = 0
            correlation = 0
            up_capture = 1.0
            down_capture = 1.0
        
        win_rate = (returns > 0).mean()
        avg_win = returns[returns > 0].mean() if len(returns[returns > 0]) > 0 else 0
        avg_loss = returns[returns < 0].mean() if len(returns[returns < 0]) > 0 else 0
        pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
        
        skew = returns.skew()
        kurt = returns.kurtosis()
        
        return PerformanceMetrics(
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            trading_days=trading_days,
            total_return=total_return,
            annualized_return=annualized_return,
            cagr=cagr,
            annualized_volatility=annualized_vol,
            downside_volatility=downside_vol,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_dd_duration,
            var_95=var_95,
            cvar_95=cvar_95,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            information_ratio=ir,
            calmar_ratio=calmar,
            omega_ratio=omega,
            serenity_ratio=serenity,
            win_rate=win_rate,
            profit_loss_ratio=pl_ratio,
            avg_win=avg_win,
            avg_loss=avg_loss,
            expectancy=expectancy,
            skewness=skew,
            kurtosis_val=kurt,
            alpha=alpha,
            beta=beta,
            correlation_to_benchmark=correlation,
            up_capture=up_capture,
            down_capture=down_capture,
            daily_returns=returns,
            cumulative_returns=cum_returns,
            drawdown_series=drawdown
        )
    
    def _calculate_max_drawdown_duration(self, drawdown: pd.Series) -> int:
        is_drawdown = drawdown < 0
        if not is_drawdown.any():
            return 0
        
        drawdown_periods = []
        current_start = None
        
        for i, in_dd in enumerate(is_drawdown):
            if in_dd and current_start is None:
                current_start = i
            elif not in_dd and current_start is not None:
                drawdown_periods.append(i - current_start)
                current_start = None
        
        if current_start is not None:
            drawdown_periods.append(len(is_drawdown) - current_start)
        
        return max(drawdown_periods) if drawdown_periods else 0
    
    def _calculate_information_ratio(self, returns: pd.Series, benchmark_returns: pd.Series) -> float:
        aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
        if len(aligned) < 30:
            return 0
        
        strategy_ret = aligned.iloc[:, 0]
        benchmark_ret = aligned.iloc[:, 1]
        
        active_returns = strategy_ret - benchmark_ret
        annual_active_return = active_returns.mean() * 252
        tracking_error = active_returns.std() * np.sqrt(252)
        
        if tracking_error == 0:
            return 0
        
        return annual_active_return / tracking_error
    
    def _calculate_alpha_beta(self, returns: pd.Series, benchmark_returns: pd.Series) -> Tuple[float, float]:
        aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
        if len(aligned) < 30:
            return 0, 0
        
        strategy_ret = aligned.iloc[:, 0]
        benchmark_ret = aligned.iloc[:, 1]
        
        beta = strategy_ret.cov(benchmark_ret) / benchmark_ret.var() if benchmark_ret.var() > 0 else 0
        alpha = strategy_ret.mean() - beta * benchmark_ret.mean()
        alpha_annual = alpha * 252
        
        return alpha_annual, beta
    
    def _calculate_capture_ratio(self, returns: pd.Series, benchmark_returns: pd.Series, direction: str = 'up') -> float:
        aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
        if len(aligned) < 30:
            return 1.0
        
        strategy_ret = aligned.iloc[:, 0]
        benchmark_ret = aligned.iloc[:, 1]
        
        if direction == 'up':
            mask = benchmark_ret > 0
        else:
            mask = benchmark_ret < 0
        
        if mask.sum() == 0:
            return 1.0
        
        strategy_capture = strategy_ret[mask].mean()
        benchmark_capture = benchmark_ret[mask].mean()
        
        if benchmark_capture == 0:
            return 1.0
        
        return strategy_capture / benchmark_capture
    
    def _calculate_omega_ratio(self, returns: pd.Series, threshold: float = None) -> float:
        if threshold is None:
            threshold = self.risk_free_rate / 252
        
        excess = returns - threshold
        upside = excess[excess > 0].sum()
        downside = abs(excess[excess < 0].sum())
        
        if downside == 0:
            return np.inf if upside > 0 else 1.0
        
        return upside / downside
    
    def _calculate_serenity_ratio(self, returns: pd.Series, max_drawdown: float) -> float:
        if max_drawdown == 0:
            return 0
        
        cagr = (1 + returns).prod() ** (252/len(returns)) - 1
        
        cum_returns = (1 + returns).cumprod()
        running_max = cum_returns.cummax()
        drawdowns = (cum_returns - running_max) / running_max
        pain_index = abs(drawdowns.mean())
        
        denominator = np.sqrt(max_drawdown**2 + pain_index**2)
        
        return cagr / denominator if denominator > 0 else 0
    
    def compare_strategies(self, metrics_list: List[PerformanceMetrics]) -> pd.DataFrame:
        if not metrics_list:
            return pd.DataFrame()
        
        comparison = []
        for m in metrics_list:
            comparison.append({
                'Strategy': m.strategy_name,
                'Period': f"{m.start_date} ~ {m.end_date}",
                'Days': m.trading_days,
                'Total Return (%)': m.total_return * 100,
                'Ann Return (%)': m.annualized_return * 100,
                'Volatility (%)': m.annualized_volatility * 100,
                'Max DD (%)': m.max_drawdown * 100,
                'Sharpe': m.sharpe_ratio,
                'Sortino': m.sortino_ratio,
                'Info Ratio': m.information_ratio,
                'Calmar': m.calmar_ratio,
                'Serenity': m.serenity_ratio,
                'Win Rate (%)': m.win_rate * 100,
                'P/L Ratio': m.profit_loss_ratio,
                'Beta': m.beta,
                'Alpha (%)': m.alpha * 100,
            })
        
        df = pd.DataFrame(comparison)
        df = df.set_index('Strategy')
        
        return df
    
    def generate_report(self, metrics: PerformanceMetrics) -> str:
        lines = []
        lines.append("=" * 70)
        lines.append(f"CTA Strategy Performance Report - {metrics.strategy_name}")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"Period: {metrics.start_date} ~ {metrics.end_date}")
        lines.append(f"Trading Days: {metrics.trading_days} days (~{metrics.trading_days/252:.1f} years)")
        lines.append("")
        
        lines.append("[Return Metrics]")
        lines.append(f"  Total Return:      {metrics.total_return*100:>10.2f}%")
        lines.append(f"  Annual Return:     {metrics.annualized_return*100:>10.2f}%")
        lines.append(f"  CAGR:              {metrics.cagr*100:>10.2f}%")
        lines.append("")
        
        lines.append("[Risk Metrics]")
        lines.append(f"  Annual Volatility: {metrics.annualized_volatility*100:>10.2f}%")
        lines.append(f"  Downside Vol:      {metrics.downside_volatility*100:>10.2f}%")
        lines.append(f"  Max Drawdown:      {metrics.max_drawdown*100:>10.2f}%")
        lines.append(f"  DD Duration:       {metrics.max_drawdown_duration:>10} days")
        lines.append(f"  VaR (95%):         {metrics.var_95*100:>10.2f}%")
        lines.append(f"  CVaR (95%):        {metrics.cvar_95*100:>10.2f}%")
        lines.append("")
        
        lines.append("[Risk-Adjusted Returns]")
        lines.append(f"  Sharpe Ratio:      {metrics.sharpe_ratio:>10.3f}")
        lines.append(f"  Sortino Ratio:     {metrics.sortino_ratio:>10.3f}")
        lines.append(f"  Information Ratio: {metrics.information_ratio:>10.3f}")
        lines.append(f"  Calmar Ratio:      {metrics.calmar_ratio:>10.3f}")
        lines.append(f"  Omega Ratio:       {metrics.omega_ratio:>10.3f}")
        lines.append(f"  Serenity Ratio:    {metrics.serenity_ratio:>10.3f}")
        lines.append("")
        
        lines.append("[Trade Statistics]")
        lines.append(f"  Win Rate:          {metrics.win_rate*100:>10.2f}%")
        lines.append(f"  P/L Ratio:         {metrics.profit_loss_ratio:>10.3f}")
        lines.append(f"  Avg Win:           {metrics.avg_win*100:>10.3f}%")
        lines.append(f"  Avg Loss:          {metrics.avg_loss*100:>10.3f}%")
        lines.append(f"  Expectancy:        {metrics.expectancy*100:>10.4f}%")
        lines.append("")
        
        if metrics.beta != 0 or metrics.alpha != 0:
            lines.append("[Benchmark Attribution]")
            lines.append(f"  Beta:              {metrics.beta:>10.3f}")
            lines.append(f"  Annual Alpha:      {metrics.alpha*100:>10.2f}%")
            lines.append(f"  Correlation:       {metrics.correlation_to_benchmark:>10.3f}")
            lines.append(f"  Up Capture:        {metrics.up_capture:>10.3f}")
            lines.append(f"  Down Capture:      {metrics.down_capture:>10.3f}")
            lines.append("")
        
        lines.append("=" * 70)
        
        return "\n".join(lines)


class StressTester:
    def __init__(self, evaluator: CTAEvaluator):
        self.evaluator = evaluator
    
    def monte_carlo_simulation(self, 
                              historical_returns: pd.Series,
                              n_simulations: int = 1000,
                              n_days: int = 252) -> Dict:
        np.random.seed(42)
        
        mean = historical_returns.mean()
        std = historical_returns.std()
        skewness = historical_returns.skew()
        kurt = historical_returns.kurtosis()
        
        simulations = []
        for _ in range(n_simulations):
            df = max(3, 6 / (kurt / 3)) if kurt > 3 else 5
            returns = np.random.standard_t(df, n_days) * std + mean
            final_value = (1 + returns).prod()
            simulations.append(final_value - 1)
        
        sim_returns = np.array(simulations)
        
        return {
            'mean_return': np.mean(sim_returns),
            'median_return': np.median(sim_returns),
            'std_return': np.std(sim_returns),
            'worst_5_percent': np.percentile(sim_returns, 5),
            'best_5_percent': np.percentile(sim_returns, 95),
            'probability_of_loss': (sim_returns < 0).mean(),
            'probability_of_double_digit_return': (sim_returns > 0.10).mean(),
            'all_simulations': sim_returns
        }
    
    def crisis_scenario_analysis(self, 
                                returns: pd.Series,
                                crisis_periods: Dict[str, Tuple[str, str]] = None) -> pd.DataFrame:
        if crisis_periods is None:
            crisis_periods = {
                '2008 Crisis': ('2008-09-01', '2009-03-31'),
                '2015 Crash': ('2015-06-01', '2015-08-31'),
                '2018 Trade War': ('2018-03-01', '2018-12-31'),
                '2020 COVID': ('2020-02-01', '2020-04-30'),
                '2022 Ukraine': ('2022-02-01', '2022-04-30'),
            }
        
        results = []
        for crisis_name, (start, end) in crisis_periods.items():
            try:
                period_returns = returns[start:end]
                if len(period_returns) == 0:
                    continue
                
                total_ret = (1 + period_returns).prod() - 1
                vol = period_returns.std() * np.sqrt(252)
                max_dd = ((1 + period_returns).cumprod() / 
                         (1 + period_returns).cumprod().cummax() - 1).min()
                
                results.append({
                    'Crisis': crisis_name,
                    'Return (%)': total_ret * 100,
                    'Vol (%)': vol * 100,
                    'Max DD (%)': max_dd * 100,
                    'Days': len(period_returns)
                })
            except:
                continue
        
        return pd.DataFrame(results)


if __name__ == "__main__":
    print("="*70)
    print("CTA Strategy Evaluation System")
    print("="*70)
    print()
    
    np.random.seed(42)
    dates = pd.date_range(start='2020-01-01', end='2024-12-31', freq='B')
    n = len(dates)
    
    returns1 = np.random.normal(0.0003, 0.012, n)
    returns1[returns1 > 0] *= 1.5
    
    returns2 = np.random.normal(0.0002, 0.015, n)
    benchmark = np.random.normal(0.0002, 0.016, n)
    
    series1 = pd.Series(returns1, index=dates)
    series2 = pd.Series(returns2, index=dates)
    bench_series = pd.Series(benchmark, index=dates)
    
    evaluator = CTAEvaluator(risk_free_rate=0.03)
    
    metrics1 = evaluator.evaluate(series1, "TSMOM_Strategy", bench_series)
    metrics2 = evaluator.evaluate(series2, "Trend_Strategy", bench_series)
    
    print(evaluator.generate_report(metrics1))
    print()
    print(evaluator.generate_report(metrics2))
    
    print()
    print("="*70)
    print("Strategy Comparison")
    print("="*70)
    comparison = evaluator.compare_strategies([metrics1, metrics2])
    print(comparison.to_string())
    
    print()
    print("="*70)
    print("Monte Carlo Simulation (Next Year)")
    print("="*70)
    stress_tester = StressTester(evaluator)
    mc_result = stress_tester.monte_carlo_simulation(series1, n_simulations=5000)
    print(f"Mean Expected Return: {mc_result['mean_return']*100:.2f}%")
    print(f"Median Return: {mc_result['median_return']*100:.2f}%")
    print(f"5th Percentile (Worst): {mc_result['worst_5_percent']*100:.2f}%")
    print(f"95th Percentile (Best): {mc_result['best_5_percent']*100:.2f}%")
    print(f"Loss Probability: {mc_result['probability_of_loss']*100:.1f}%")
    
    print()
    print("="*70)
    print("Evaluation Complete!")
    print("="*70)
