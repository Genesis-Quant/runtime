"""复用 DolphinDB 行情表运行 ETF 动量与风险平价研究。"""

from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from core.database.core import CORE_TABLE
from core.utils import DateLike, normalize_date_range
from core.workers.fund_daily import FUND_CODES

STRATEGY_FUNCTIONS = """
def etfMomentumScore(history, targetCode, window, annualTradingDays) {
    rows = select
        time,
        close
    from history
    where
        code == targetCode,
        !isNull(close),
        close > 0
    order by time desc
    if (rows.rows() < window) return double(NULL)
    rows = rows[0:window]

    prices = double(reverse(rows.close))
    logReturns =
        log(prices[1:window]) -
        log(prices[0:(window - 1)])
    volatility = stdp(logReturns) * sqrt(annualTradingDays)

    x = double(0..(window - 1))
    regressionWeights = square(1.0 + x / (window - 1))
    y = log(prices)
    xMean = sum(regressionWeights * x) / sum(regressionWeights)
    yMean = sum(regressionWeights * y) / sum(regressionWeights)
    denominator = sum(
        regressionWeights * (x - xMean) * (x - xMean)
    )
    if (denominator <= 0) return double(NULL)

    slope = sum(
        regressionWeights *
        (x - xMean) *
        (y - yMean)
    ) / denominator
    annualReturn = exp(slope * annualTradingDays) - 1.0
    return annualReturn / (volatility + 1e-6)
}

def etfRiskParityCovariance(history, codes, window, maxHistoryRows, annualTradingDays) {
    priceHistory = select
        time,
        code,
        close
    from history
    where
        code in codes,
        !isNull(close),
        close > 0
    if (priceHistory.rows() == 0) {
        return (matrix(DOUBLE, size(codes), size(codes)), 0)
    }

    historyWide = select first(close) as close
    from priceHistory
    pivot by time, code
    historyWide = select *
    from historyWide
    order by time desc
    historyWide = historyWide[
        0:min(maxHistoryRows, historyWide.rows())
    ]

    availableCodes = columnNames(historyWide)[1:]
    missingCodes = string(codes)[
        !(string(codes) in availableCodes)
    ]
    if (size(missingCodes) > 0) {
        return (matrix(DOUBLE, size(codes), size(codes)), 0)
    }

    priceColumns = historyWide[codes]
    validRows = take(true, historyWide.rows())
    for (index in 0..(size(codes) - 1)) {
        validRows = validRows && !isNull(priceColumns[index])
    }
    validIndices = (0..(historyWide.rows() - 1))[validRows]
    observationCount = min(size(validIndices), window)
    if (observationCount < window) {
        return (
            matrix(DOUBLE, size(codes), size(codes)),
            observationCount
        )
    }
    validIndices = reverse(validIndices[0:observationCount])

    count = size(codes)
    returns = array(ANY, 0)
    for (index in 0..(count - 1)) {
        prices = double(priceColumns[index][validIndices])
        returns.append!(
            log(prices[1:window]) -
            log(prices[0:(window - 1)])
        )
    }

    covariance = matrix(DOUBLE, count, count)
    for (leftIndex in 0..(count - 1)) {
        for (rightIndex in leftIndex..(count - 1)) {
            value = annualTradingDays * covar(
                returns[leftIndex],
                returns[rightIndex]
            )
            covariance[leftIndex, rightIndex] = value
            covariance[rightIndex, leftIndex] = value
        }
    }
    for (index in 0..(count - 1)) {
        covariance[index, index] += 1e-6
    }
    return (covariance, observationCount)
}

def etfRiskParityObjective(weights, covariance) {
    count = size(weights)
    covarianceTimesWeights = take(0.0, count)
    for (index in 0..(count - 1)) {
        covarianceTimesWeights[index] = sum(
            flatten(covariance[index,]) * weights
        )
    }
    portfolioVolatility = sqrt(
        sum(weights * covarianceTimesWeights)
    )
    if (portfolioVolatility <= 0) return double("inf")
    riskContributions =
        weights * covarianceTimesWeights / portfolioVolatility
    targetContribution = portfolioVolatility / count
    return sum(square(riskContributions - targetContribution))
}

def etfWeightSumConstraint(weights) {
    return sum(weights) - 1.0
}

def etfWeightSumJacobian(weights) {
    return take(1.0, size(weights))
}

def etfNonnegativeConstraint(weights) {
    return weights
}

def etfNonnegativeJacobian(weights) {
    count = size(weights)
    result = matrix(DOUBLE, count, count, 0)
    for (index in 0..(count - 1)) {
        result[index, index] = 1.0
    }
    return result
}

def etfRiskParityWeights(covariance, maxIterations, tolerance) {
    count = rows(covariance)
    if (count == 0 || cols(covariance) != count) {
        throw "协方差矩阵必须是非空方阵"
    }

    equalityConstraint = dict(STRING, ANY)
    equalityConstraint[`type] = `eq
    equalityConstraint[`fun] = etfWeightSumConstraint
    equalityConstraint[`jac] = etfWeightSumJacobian
    nonnegativeConstraint = dict(STRING, ANY)
    nonnegativeConstraint[`type] = `ineq
    nonnegativeConstraint[`fun] = etfNonnegativeConstraint
    nonnegativeConstraint[`jac] = etfNonnegativeJacobian
    bounds = matrix(take(0.0, count), take(1.0, count))
    optimization = fminSLSQP(
        etfRiskParityObjective{, covariance},
        take(1.0 / count, count),
        constraints=[equalityConstraint, nonnegativeConstraint],
        bounds=bounds,
        ftol=tolerance,
        maxIter=maxIterations
    )
    if (optimization[`mode] != 0) {
        throw "SLSQP 风险平价优化失败"
    }
    return optimization[`xopt]
}

def etfInitialize(mutable context) {
    context["rebalanceCount"] = 0
}

def etfOnBar(parameters, mutable context, msg, indicator) {
    strategyCodes = parameters["codes"]
    strategySymbols = parameters["symbols"]
    momentumWindow = parameters["momentumWindow"]
    selectCount = parameters["selectCount"]
    riskWindow = parameters["riskWindow"]
    maxHistoryRows = parameters["maxHistoryRows"]
    targetVolatility = parameters["targetVolatility"]
    maxInvestedRatio = parameters["maxInvestedRatio"]
    slippageRate = parameters["slippageRate"]
    pricePrecision = parameters["pricePrecision"]
    lotSize = parameters["lotSize"]
    annualTradingDays = parameters["signalAnnualizationDays"]
    optimizerMaxIterations = parameters["optimizerMaxIterations"]
    optimizerTolerance = parameters["optimizerTolerance"]

    if (msg.rows() == 0) return
    currentDate = date(msg.tradeTime[0])
    slippage = slippageRate / 2.0
    messageSymbols = symbol(string(msg.symbol))
    messageVolumes = long(msg.volume)
    calendarData = context["coreBacktestUnfilteredFactorData"]
    nextTradeDate = exec min(date(time))
    from calendarData
    where date(time) > currentDate
    if (
        !isNull(nextTradeDate) &&
        weekOfYear(nextTradeDate) == weekOfYear(currentDate)
    ) return

    history = backtest::getHistoryData(context, msg, false)
    if (history.rows() == 0) return

    scores = take(double(NULL), size(strategyCodes))
    for (index in 0..(size(strategyCodes) - 1)) {
        scores[index] = etfMomentumScore(
            history,
            strategyCodes[index],
            momentumWindow,
            annualTradingDays
        )
    }
    scoreTable = table(strategyCodes as code, scores as score)
    selected = select *
    from scoreTable
    where !isNull(score)
    order by score desc
    if (selected.rows() == 0) return
    selected = selected[0:min(selectCount, selected.rows())]

    selectedCodes = selected.code
    selectedSymbols = symbol(
        strReplace(
            strReplace(string(selectedCodes), ".SZ", ".XSHE"),
            ".SH",
            ".XSHG"
        )
    )
    covarianceResult = etfRiskParityCovariance(
        history,
        selectedCodes,
        riskWindow,
        maxHistoryRows,
        annualTradingDays
    )
    if (covarianceResult[1] < riskWindow) return

    covariance = covarianceResult[0]
    weights = etfRiskParityWeights(
        covariance,
        optimizerMaxIterations,
        optimizerTolerance
    )
    marginalRisk = take(0.0, size(weights))
    for (index in 0..(size(weights) - 1)) {
        marginalRisk[index] = sum(
            flatten(covariance[index,]) * weights
        )
    }
    portfolioVolatility = sqrt(sum(weights * marginalRisk))
    if (portfolioVolatility > targetVolatility) {
        weights *= targetVolatility / portfolioVolatility
    }

    totalEquity = Backtest::getAvailableCash(context.engine)
    pausedValue = 0.0
    for (index in 0..(size(strategySymbols) - 1)) {
        currentSymbol = strategySymbols[index]
        position = Backtest::getPosition(
            context.engine,
            currentSymbol
        )
        currentPosition = long(
            nullFill(position.longPosition.sum(), 0)
        )
        messageIndex = find(messageSymbols, currentSymbol)
        paused = messageIndex < 0
        if (!paused) {
            paused = messageVolumes[messageIndex] <= 0
        }
        if (currentPosition > 0 && !paused) {
            totalEquity +=
                currentPosition * msg.open[messageIndex]
        }
        if (currentPosition > 0 && paused) {
            lastPrice = select top 1 close
            from history
            where code == strategyCodes[index]
            order by time desc
            if (lastPrice.rows() > 0) {
                positionValue =
                    currentPosition * lastPrice.close[0]
                pausedValue += positionValue
                totalEquity += positionValue
            }
        }
    }
    if (isNull(totalEquity) || totalEquity <= 0) return

    allocatableEquity =
        maxInvestedRatio * (totalEquity - pausedValue)
    if (allocatableEquity <= 0) return
    targetPositions = take(long(0), size(selectedSymbols))
    executionPrices = take(double(NULL), size(selectedSymbols))
    for (index in 0..(size(selectedSymbols) - 1)) {
        currentSymbol = selectedSymbols[index]
        messageIndex = find(messageSymbols, currentSymbol)
        position = Backtest::getPosition(
            context.engine,
            currentSymbol
        )
        currentPosition = long(
            nullFill(position.longPosition.sum(), 0)
        )
        paused = messageIndex < 0
        if (!paused) {
            paused = messageVolumes[messageIndex] <= 0
        }
        if (paused) {
            targetPositions[index] = currentPosition
        } else {
            executionPrices[index] = msg.open[messageIndex]
            targetValue = allocatableEquity * weights[index]
            positionDifference =
                targetValue / executionPrices[index] -
                currentPosition
            positionAdjustment = long(
                floor(abs(positionDifference) / lotSize) *
                lotSize
            )
            targetPositions[index] = iif(
                positionDifference < 0,
                currentPosition - positionAdjustment,
                currentPosition + positionAdjustment
            )
        }
    }

    for (index in 0..(size(strategySymbols) - 1)) {
        currentSymbol = strategySymbols[index]
        messageIndex = find(messageSymbols, currentSymbol)
        if (
            messageIndex < 0 ||
            messageVolumes[messageIndex] <= 0
        ) continue

        position = Backtest::getPosition(
            context.engine,
            currentSymbol
        )
        currentPosition = long(
            nullFill(position.longPosition.sum(), 0)
        )
        selectedIndex = find(selectedSymbols, currentSymbol)
        targetPosition = iif(
            selectedIndex < 0,
            long(0),
            targetPositions[selectedIndex]
        )
        if (currentPosition > targetPosition) {
            Backtest::submitOrder(
                context.engine,
                (
                    currentSymbol,
                    context.tradeTime,
                    5,
                    round(
                        msg.open[messageIndex] *
                        (1.0 - slippage),
                        pricePrecision
                    ),
                    currentPosition - targetPosition,
                    3
                ),
                "etf-risk-parity-sell"
            )
        }
    }

    for (index in 0..(size(selectedSymbols) - 1)) {
        currentSymbol = selectedSymbols[index]
        messageIndex = find(messageSymbols, currentSymbol)
        if (
            messageIndex < 0 ||
            messageVolumes[messageIndex] <= 0
        ) continue

        position = Backtest::getPosition(
            context.engine,
            currentSymbol
        )
        currentPosition = long(
            nullFill(position.longPosition.sum(), 0)
        )
        targetPosition = targetPositions[index]
        if (currentPosition <= targetPosition - lotSize) {
            Backtest::submitOrder(
                context.engine,
                (
                    currentSymbol,
                    context.tradeTime,
                    5,
                    round(
                        executionPrices[index] *
                        (1.0 + slippage),
                        pricePrecision
                    ),
                    targetPosition - currentPosition,
                    1
                ),
                "etf-risk-parity-buy"
            )
        }
    }

    context["rebalanceCount"] += 1
}
"""


def get_data(
        session: Any,
        factor_names: Sequence[str],
        start_date: DateLike,
        end_date: DateLike,
        history_buffer_days: int,
) -> dict[str, int]:
    """查询全部 FUND_CODES，并在当前会话中缓存行情表和消息表。"""
    output_start, output_end = normalize_date_range(start_date, end_date)
    session.upload(
        {
            "strategyStartDate": output_start.to_datetime64().astype(
                "datetime64[D]"
            ),
            "strategyEndDate": output_end.to_datetime64().astype(
                "datetime64[D]"
            ),
            "strategyDataCodeNames": np.asarray(FUND_CODES, dtype=str),
            "strategyFactorNames": np.asarray(factor_names, dtype=str),
            "strategyHistoryBufferDays": int(history_buffer_days),
        }
    )
    session.run("use backtest")
    profile = session.run(
        f"""
        strategyDataCodes = symbol(strategyDataCodeNames)

        strategyMarketData = select
            time,
            code,
            double(open * adj_factor) as open,
            double(low * adj_factor) as low,
            double(high * adj_factor) as high,
            double(close * adj_factor) as close,
            long(round(vol * 100, 0)) as volume,
            double(
                iif(
                    high > round(pre_close * 1.1, 3),
                    high,
                    round(pre_close * 1.1, 3)
                ) * adj_factor
            ) as upLimitPrice,
            double(
                iif(
                    low < round(pre_close * 0.9, 3),
                    low,
                    round(pre_close * 0.9, 3)
                ) * adj_factor
            ) as downLimitPrice,
            double(pre_close * adj_factor) as prevClosePrice
        from (
            select first(value) as value
            from {CORE_TABLE}
            where
                time >= temporalAdd(
                    strategyStartDate,
                    -strategyHistoryBufferDays,
                    "d"
                ),
                time <= strategyEndDate,
                code in strategyDataCodes,
                factor in symbol(strategyFactorNames)
            pivot by time, code, factor
        )
        where
            !isNull(open),
            !isNull(low),
            !isNull(high),
            !isNull(close),
            !isNull(pre_close),
            !isNull(adj_factor),
            !isNull(vol),
            close > 0,
            vol >= 0
        order by time, code

        strategyMessage = backtest::build_backtest_message(
            select *
            from strategyMarketData
            where
                date(time) >= strategyStartDate,
                date(time) <= strategyEndDate
        )

        strategyDataProfile = dict(STRING, INT)
        strategyDataProfile["strategyMarketData"] =
            strategyMarketData.rows()
        strategyDataProfile["strategyMessage"] =
            strategyMessage.rows()
        strategyDataProfile
        """
    )
    session.run(STRATEGY_FUNCTIONS)
    return {
        "strategyMarketData": int(profile["strategyMarketData"]),
        "strategyMessage": int(profile["strategyMessage"]),
    }


def run_strategy(
        session: Any,
        code_names: Sequence[str],
        start_date: DateLike,
        end_date: DateLike,
        initial_cash: float,
        momentum_window: int,
        select_count: int,
        risk_window: int,
        max_history_rows: int,
        target_volatility: float,
        max_invested_ratio: float,
) -> pd.Series:
    """按代码和日期筛选已缓存数据，运行策略并返回每日净值曲线。"""
    output_start, output_end = normalize_date_range(start_date, end_date)
    engine_name = f"etf-research-{uuid4().hex}"
    session.upload(
        {
            "strategyCodeNames": np.asarray(code_names, dtype=str),
            "strategyRunStartDate": output_start.to_datetime64().astype(
                "datetime64[D]"
            ),
            "strategyRunEndDate": output_end.to_datetime64().astype(
                "datetime64[D]"
            ),
            "strategyInitialCash": float(initial_cash),
            "strategyMomentumWindow": int(momentum_window),
            "strategySelectCount": int(select_count),
            "strategyRiskWindow": int(risk_window),
            "strategyMaxHistoryRows": int(max_history_rows),
            "strategyTargetVolatility": float(target_volatility),
            "strategyMaxInvestedRatio": float(max_invested_ratio),
            "strategyEngineName": engine_name,
            "strategySignalAnnualizationDays": 252,
            "strategyOptimizerMaxIterations": 1_000,
            "strategyOptimizerTolerance": 1e-9,
            "strategySlippageRate": 0.00246,
            "strategyPricePrecision": 3,
            "strategyLotSize": 100,
        }
    )
    engine_created = False
    try:
        session.run(
            """
            strategyCodes = symbol(strategyCodeNames)
            strategySymbols = symbol(
                strReplace(
                    strReplace(string(strategyCodes), ".SZ", ".XSHE"),
                    ".SH",
                    ".XSHG"
                )
            )
            strategyRunMarketData = select *
            from strategyMarketData
            where
                code in strategyCodes,
                date(time) <= strategyRunEndDate
            strategyRunMessage = select *
            from strategyMessage
            where
                symbol in strategySymbols,
                date(tradeTime) >= strategyRunStartDate,
                date(tradeTime) <= strategyRunEndDate

            strategyConfig = dict(STRING, ANY)
            strategyConfig["startDate"] = strategyRunStartDate
            strategyConfig["endDate"] = strategyRunEndDate
            strategyConfig["strategyGroup"] = "stock"
            strategyConfig["cash"] = double(strategyInitialCash)
            strategyConfig["commission"] = double(0.00005)
            strategyConfig["enableMinimumPerTransactionFee"] = true
            strategyConfig["tax"] = double(0)
            strategyConfig["dataType"] = int(4)
            strategyConfig["msgAsTable"] = true
            strategyConfig["matchingMode"] = int(3)

            strategyParameters = dict(STRING, ANY)
            strategyParameters["codes"] = strategyCodes
            strategyParameters["symbols"] = strategySymbols
            strategyParameters["momentumWindow"] =
                strategyMomentumWindow
            strategyParameters["selectCount"] =
                strategySelectCount
            strategyParameters["riskWindow"] =
                strategyRiskWindow
            strategyParameters["maxHistoryRows"] =
                strategyMaxHistoryRows
            strategyParameters["targetVolatility"] =
                strategyTargetVolatility
            strategyParameters["maxInvestedRatio"] =
                strategyMaxInvestedRatio
            strategyParameters["slippageRate"] =
                strategySlippageRate
            strategyParameters["pricePrecision"] =
                strategyPricePrecision
            strategyParameters["lotSize"] = strategyLotSize
            strategyParameters["signalAnnualizationDays"] =
                strategySignalAnnualizationDays
            strategyParameters["optimizerMaxIterations"] =
                strategyOptimizerMaxIterations
            strategyParameters["optimizerTolerance"] =
                strategyOptimizerTolerance

            strategyEngine = backtest::run_backtest(
                strategyEngineName,
                strategyConfig,
                strategyRunMessage,
                strategyRunMarketData,
                strategyRunMarketData,
                etfInitialize,
                NULL,
                etfOnBar{strategyParameters},
                NULL,
                NULL,
                NULL,
                NULL,
                NULL
            )
            """
        )
        engine_created = True
        daily_net_value = session.run(
            """
            select
                tradeDate,
                netValue
            from Backtest::getDailyTotalPortfolios(strategyEngine)
            order by tradeDate
            """
        )
    finally:
        if engine_created:
            session.run(
                "Backtest::dropBacktestEngine(strategyEngine)"
            )

    if not isinstance(daily_net_value, pd.DataFrame):
        raise TypeError("每日净值结果必须是 DataFrame")
    return daily_net_value.set_index("tradeDate")["netValue"]


__all__ = ["get_data", "run_strategy"]
