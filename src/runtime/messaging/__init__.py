"""结构化消息、结果汇总和发送渠道。"""

from runtime.messaging.channels import (
    CHANNEL_TYPES,
    DEFAULT_MESSAGE_CHANNEL,
    MessageChannel,
    create_message_channel,
    normalize_channel_name,
)
from runtime.messaging.models import (
    ImageMessageBlock,
    MessageDeliveryResult,
    SpecialMessageBlock,
    StructuredMessage,
    TextMessageBlock,
)
from runtime.messaging.service import read_message, send_message, write_message

__all__ = [
    "CHANNEL_TYPES",
    "DEFAULT_MESSAGE_CHANNEL",
    "ImageMessageBlock",
    "MessageChannel",
    "MessageDeliveryResult",
    "SpecialMessageBlock",
    "StructuredMessage",
    "TextMessageBlock",
    "create_message_channel",
    "normalize_channel_name",
    "read_message",
    "send_message",
    "write_message",
]
