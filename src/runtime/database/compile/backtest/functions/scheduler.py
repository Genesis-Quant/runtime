"""定义基于交易日和当前回放阶段的策略调度函数。"""

from runtime.database.compile import DolphinDBFunction

from .calendar import GET_TRADING_DAYS


REGISTER_SCHEDULE = DolphinDBFunction(
    module="backtest",
    definition="""
    def register_schedule(mutable context, callback, frequency, tradingDay, phase) {
        if (!("arenaScheduler" in context.keys())) {
            throw "run_daily/run_weekly/run_monthly 只能在 initialize 中注册"
        }
        scheduler = context["arenaScheduler"]
        if (!bool(scheduler["registrationOpen"])) {
            throw "run_daily/run_weekly/run_monthly 只能在 initialize 中注册"
        }
        normalizedFrequency = lower(string(frequency))
        normalizedPhase = lower(string(phase))
        if (!(normalizedFrequency in ["daily", "weekly", "monthly"])) {
            throw "frequency 只能是 daily、weekly 或 monthly"
        }
        if (!(
            normalizedPhase in [
                "before_trading",
                "open",
                "after_trading"
            ]
        )) {
            throw "phase 只能是 before_trading、open 或 after_trading"
        }
        normalizedTradingDay = int(tradingDay)
        if (
            isNull(tradingDay) ||
            double(normalizedTradingDay) != double(tradingDay)
        ) {
            throw "tradingDay 必须是整数"
        }
        if (
            normalizedFrequency != "daily" &&
            normalizedTradingDay == 0
        ) {
            throw "周/月调度的 tradingDay 不能为 0"
        }
        callbacks = scheduler["callbacks"]
        frequencies = scheduler["frequencies"]
        tradingDays = scheduler["tradingDays"]
        phases = scheduler["phases"]
        callbacks.append!(callback)
        frequencies.append!(normalizedFrequency)
        tradingDays.append!(normalizedTradingDay)
        phases.append!(normalizedPhase)
        scheduler["callbacks"] = callbacks
        scheduler["frequencies"] = frequencies
        scheduler["tradingDays"] = tradingDays
        scheduler["phases"] = phases
        context["arenaScheduler"] = scheduler
        return size(callbacks) - 1
    }
    """,
)

RUN_DAILY = DolphinDBFunction(
    module="backtest",
    definition="""
    def run_daily(mutable context, callback, phase="open") {
        /* 在每个回放交易日的指定阶段运行 callback。 */
        return register_schedule(
            context,
            callback,
            "daily",
            0,
            phase
        )
    }
    """,
    dependencies=(REGISTER_SCHEDULE,),
)

RUN_WEEKLY = DolphinDBFunction(
    module="backtest",
    definition="""
    def run_weekly(mutable context, callback, tradingDay=1, phase="open") {
        /* 在每周第 tradingDay 个交易日运行 callback；负数表示倒数。 */
        return register_schedule(
            context,
            callback,
            "weekly",
            tradingDay,
            phase
        )
    }
    """,
    dependencies=(REGISTER_SCHEDULE,),
)

RUN_MONTHLY = DolphinDBFunction(
    module="backtest",
    definition="""
    def run_monthly(mutable context, callback, tradingDay=1, phase="open") {
        /* 在每月第 tradingDay 个交易日运行 callback；负数表示倒数。 */
        return register_schedule(
            context,
            callback,
            "monthly",
            tradingDay,
            phase
        )
    }
    """,
    dependencies=(REGISTER_SCHEDULE,),
)

SCHEDULE_MATCHES_DATE = DolphinDBFunction(
    module="backtest",
    definition="""
    def schedule_matches_date(currentDate, frequency, tradingDay) {
        if (frequency == "daily") return true
        if (frequency == "weekly") {
            periodStart = weekBegin(currentDate)
            periodEnd = weekEnd(currentDate)
        } else {
            periodStart = monthBegin(currentDate)
            periodEnd = monthEnd(currentDate)
        }
        periodTradingDays = get_trading_days(
            periodStart,
            periodEnd,
            "XSHG"
        )
        selectedIndex = iif(
            tradingDay > 0,
            tradingDay - 1,
            size(periodTradingDays) + tradingDay
        )
        return selectedIndex >= 0 &&
            selectedIndex < size(periodTradingDays) &&
            periodTradingDays[selectedIndex] == currentDate
    }
    """,
    dependencies=(GET_TRADING_DAYS,),
)

DISPATCH_SCHEDULES = DolphinDBFunction(
    module="backtest",
    definition="""
    def dispatch_schedules(mutable context, currentDate, phase, message, indicator) {
        scheduler = context["arenaScheduler"]
        callbacks = scheduler["callbacks"]
        frequencies = scheduler["frequencies"]
        tradingDays = scheduler["tradingDays"]
        phases = scheduler["phases"]
        if (size(callbacks) == 0) return NULL
        for (index in 0..(size(callbacks) - 1)) {
            if (phases[index] != phase) continue
            if (!schedule_matches_date(
                currentDate,
                frequencies[index],
                tradingDays[index]
            )) continue
            call(
                callbacks[index],
                context,
                message,
                indicator
            )
        }
        return NULL
    }
    """,
    dependencies=(SCHEDULE_MATCHES_DATE,),
)

INITIALIZE_SCHEDULER_CONTEXT = DolphinDBFunction(
    module="backtest",
    definition="""
    def initialize_scheduler_context(mutable context, replayDates) {
        scheduler = dict(STRING, ANY)
        scheduler["callbacks"] = array(ANY, 0)
        scheduler["frequencies"] = array(STRING, 0)
        scheduler["tradingDays"] = array(INT, 0)
        scheduler["phases"] = array(STRING, 0)
        scheduler["replayDates"] = date(replayDates)
        scheduler["dateIndex"] = -1
        scheduler["registrationOpen"] = true
        context["arenaScheduler"] = scheduler
        return NULL
    }
    """,
)

INITIALIZE_WITH_SCHEDULER = DolphinDBFunction(
    module="backtest",
    definition="""
    def initialize_with_scheduler(mutable context, callback, replayDates) {
        initialize_scheduler_context(context, replayDates)
        result = call(callback, context)
        scheduler = context["arenaScheduler"]
        scheduler["registrationOpen"] = false
        context["arenaScheduler"] = scheduler
        return result
    }
    """,
    dependencies=(INITIALIZE_SCHEDULER_CONTEXT,),
)

BEFORE_TRADING_WITH_SCHEDULER = DolphinDBFunction(
    module="backtest",
    definition="""
    def before_trading_with_scheduler(mutable context, callback) {
        scheduler = context["arenaScheduler"]
        currentIndex = int(scheduler["dateIndex"]) + 1
        replayDates = scheduler["replayDates"]
        if (currentIndex >= size(replayDates)) {
            throw "调度日期与 Backtest beforeTrading 回调数量不一致"
        }
        scheduler["dateIndex"] = currentIndex
        context["arenaScheduler"] = scheduler
        result = call(callback, context)
        dispatch_schedules(
            context,
            replayDates[currentIndex],
            "before_trading",
            NULL,
            NULL
        )
        return result
    }
    """,
    dependencies=(DISPATCH_SCHEDULES,),
)

ON_SNAPSHOT_WITH_SCHEDULER = DolphinDBFunction(
    module="backtest",
    definition="""
    def on_snapshot_with_scheduler(mutable context, message, indicator, callback) {
        currentTime = time(message.timestamp[0])
        if (currentTime == 09:30:00) {
            dispatch_schedules(
                context,
                date(message.timestamp[0]),
                "open",
                message,
                indicator
            )
        }
        return call(callback, context, message, indicator)
    }
    """,
    dependencies=(DISPATCH_SCHEDULES,),
)

AFTER_TRADING_WITH_SCHEDULER = DolphinDBFunction(
    module="backtest",
    definition="""
    def after_trading_with_scheduler(mutable context, callback) {
        result = call(callback, context)
        scheduler = context["arenaScheduler"]
        currentIndex = int(scheduler["dateIndex"])
        replayDates = scheduler["replayDates"]
        if (currentIndex >= 0 && currentIndex < size(replayDates)) {
            dispatch_schedules(
                context,
                replayDates[currentIndex],
                "after_trading",
                NULL,
                NULL
            )
        }
        return result
    }
    """,
    dependencies=(DISPATCH_SCHEDULES,),
)

CLEANUP_SCHEDULER_CONTEXT = DolphinDBFunction(
    module="backtest",
    definition="""
    def cleanup_scheduler_context(mutable context) {
        erase!(context, "arenaScheduler")
        return NULL
    }
    """,
)

FINALIZE_WITH_SCHEDULER = DolphinDBFunction(
    module="backtest",
    definition="""
    def finalize_with_scheduler(mutable context, callback) {
        cleanup_scheduler_context(context)
        return call(callback, context)
    }
    """,
    dependencies=(CLEANUP_SCHEDULER_CONTEXT,),
)
