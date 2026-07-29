"""定义 Backtest 生命周期回调的默认实现。"""

from core.database.compile import DolphinDBFunction


CALLBACK_OR_DEFAULT = DolphinDBFunction(
    module="backtest",
    definition="""
    def callback_or_default(callback, fallback) {
        if (isNull(callback)) {
            return fallback
        }
        return callback
    }
    """,
)

NOOP_CONTEXT_CALLBACK = DolphinDBFunction(
    module="backtest",
    definition="""
    def noop_context_callback(mutable context) {
        return NULL
    }
    """,
)

NOOP_EVENT_CALLBACK = DolphinDBFunction(
    module="backtest",
    definition="""
    def noop_event_callback(mutable context, event) {
        return NULL
    }
    """,
)

NOOP_MESSAGE_CALLBACK = DolphinDBFunction(
    module="backtest",
    definition="""
    def noop_message_callback(mutable context, message, indicator) {
        return NULL
    }
    """,
)
