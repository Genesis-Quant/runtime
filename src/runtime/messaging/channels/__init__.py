"""消息 Channel 注册和解析。"""

from runtime.messaging.channels.base import MessageChannel
from runtime.messaging.channels.console import ConsoleMessageChannel

CHANNEL_TYPES: dict[str, type[MessageChannel]] = {
    ConsoleMessageChannel.name: ConsoleMessageChannel,
}
DEFAULT_MESSAGE_CHANNEL = ConsoleMessageChannel.name


def normalize_channel_name(value: str | None) -> str:
    """校验并返回规范 Channel 名称。"""
    name = value.strip().lower() if value else DEFAULT_MESSAGE_CHANNEL
    name = name or DEFAULT_MESSAGE_CHANNEL
    if name not in CHANNEL_TYPES:
        available = "、".join(CHANNEL_TYPES)
        raise ValueError(f"未知消息 Channel：{value!r}；可用值：{available}")
    return name


def create_message_channel(value: str) -> MessageChannel:
    """创建已注册的消息 Channel。"""
    name = normalize_channel_name(value)
    return CHANNEL_TYPES[name]()


__all__ = [
    "CHANNEL_TYPES",
    "ConsoleMessageChannel",
    "DEFAULT_MESSAGE_CHANNEL",
    "MessageChannel",
    "create_message_channel",
    "normalize_channel_name",
]
