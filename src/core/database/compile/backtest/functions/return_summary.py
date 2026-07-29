"""定义与聚宽一致的回测收益汇总口径。"""

from core.database.compile import DolphinDBFunction


STANDARDIZE_RETURN_SUMMARY = DolphinDBFunction(
    module="backtest",
    definition="""
    def standardize_return_summary(summary, daily_portfolios, annual_trading_days, risk_free_rate) {
        /*
        使用指定交易日数和无风险收益率重算策略收益汇总。

        年化收益按完整日频净值序列复利计算；年化波动率使用相邻净值的
        简单收益率总体标准差。函数保留 Backtest 插件返回的其余字段，
        只替换受年化口径影响的 annualReturn、annualVolatility、
        sharpeRatio 和 drawdownRatio。
        */
        if (summary.rows() == 0 || daily_portfolios.rows() == 0) {
            return summary
        }
        result = select * from summary

        values = exec double(netValue)
        from daily_portfolios
        where !isNull(netValue)
        order by tradeDate
        if (size(values) == 0) {
            return summary
        }

        trading_days = int(annual_trading_days)
        annual_return = double(NULL)
        if (last(values) > 0) {
            annual_return = pow(
                last(values),
                double(trading_days) / size(values)
            ) - 1
        }

        daily_returns = deltas(values) / prev(values)
        daily_returns = daily_returns[!isNull(daily_returns)]
        annual_volatility = double(NULL)
        if (size(daily_returns) > 1) {
            annual_volatility = stdp(daily_returns) * sqrt(trading_days)
        }

        sharpe_ratio = double(NULL)
        if (
            !isNull(annual_return) &&
            !isNull(annual_volatility) &&
            annual_volatility != 0
        ) {
            sharpe_ratio =
                (annual_return - double(risk_free_rate)) /
                annual_volatility
        }

        column_names = result.colNames()
        row_count = result.rows()
        if ("annualReturn" in column_names) {
            replaceColumn!(
                result,
                `annualReturn,
                take(annual_return, row_count)
            )
        }
        if ("annualVolatility" in column_names) {
            replaceColumn!(
                result,
                `annualVolatility,
                take(annual_volatility, row_count)
            )
        }
        if ("sharpeRatio" in column_names) {
            replaceColumn!(
                result,
                `sharpeRatio,
                take(sharpe_ratio, row_count)
            )
        }
        if ("drawdownRatio" in column_names) {
            drawdown_ratio = take(double(NULL), row_count)
            for (index in 0:row_count) {
                drawdown = result.maxDrawdown[index]
                if (
                    !isNull(annual_return) &&
                    !isNull(drawdown) &&
                    drawdown != 0
                ) {
                    drawdown_ratio[index] = annual_return / drawdown
                }
            }
            replaceColumn!(
                result,
                `drawdownRatio,
                drawdown_ratio
            )
        }
        return result
    }
    """,
)
