"""与发送渠道无关的结构化消息读写和投递。"""

from __future__ import annotations

from pathlib import Path

from runtime.messaging.channels import create_message_channel
from runtime.messaging.models import MessageDeliveryResult, StructuredMessage
from runtime.utils.files import atomic_write_text


def read_message(path: Path | str) -> StructuredMessage:
    """读取并校验一个结构化消息 JSON 文件。"""
    source = Path(path).expanduser().resolve()
    try:
        return StructuredMessage.model_validate_json(
            source.read_text(encoding="utf-8-sig")
        )
    except (OSError, ValueError) as error:
        raise ValueError(f"无法读取结构化消息：{error}") from error


def write_message(path: Path | str, message: StructuredMessage) -> Path:
    """原子写入一个结构化消息 JSON 文件。"""
    return atomic_write_text(path, message.model_dump_json(indent=2))


def send_message(
    message: StructuredMessage,
    channel: str,
) -> MessageDeliveryResult:
    """通过已注册的 Channel 投递结构化消息。"""
    return create_message_channel(channel).send(message)


__all__ = ["read_message", "send_message", "write_message"]
