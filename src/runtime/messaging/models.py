"""跨发送渠道复用的结构化消息模型。"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class TextMessageBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["text"] = "text"
    text: str = Field(min_length=1)


class ImageMessageBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["image"] = "image"
    source: str = Field(min_length=1)
    alt: str | None = None


class SpecialMessageBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["special"] = "special"
    channel: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    format: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    payload: dict[str, Any]


MessageBlock = Annotated[
    TextMessageBlock | ImageMessageBlock | SpecialMessageBlock,
    Field(discriminator="type"),
]


class StructuredMessage(BaseModel):
    """可由不同 Channel 发送的消息信封。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    message_id: str = Field(
        default_factory=lambda: uuid4().hex,
        pattern=r"^[a-zA-Z0-9-]+$",
    )
    title: str = Field(min_length=1)
    blocks: list[MessageBlock] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageDeliveryResult(BaseModel):
    """一次 Channel 调用的稳定返回结果。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    channel: str
    status: Literal["SENT", "PRINTED", "IGNORED"]
    delivered_blocks: int = Field(ge=0)
    ignored_blocks: int = Field(ge=0)


__all__ = [
    "ImageMessageBlock",
    "MessageBlock",
    "MessageDeliveryResult",
    "SpecialMessageBlock",
    "StructuredMessage",
    "TextMessageBlock",
]
