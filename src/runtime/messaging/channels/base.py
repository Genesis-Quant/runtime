"""消息发送渠道抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Literal

from runtime.messaging.models import (
    MessageDeliveryResult,
    SpecialMessageBlock,
    StructuredMessage,
)


class MessageChannel(ABC):
    """过滤渠道专用内容并发送其余消息块。"""

    name: ClassVar[str]
    delivery_status: ClassVar[Literal["SENT", "PRINTED"]] = "SENT"
    special_formats: ClassVar[frozenset[str]] = frozenset()

    def send(self, message: StructuredMessage) -> MessageDeliveryResult:
        deliverable = []
        ignored = 0
        for block in message.blocks:
            if isinstance(block, SpecialMessageBlock) and (
                block.channel != self.name
                or block.format not in self.special_formats
            ):
                ignored += 1
                continue
            deliverable.append(block)

        if not deliverable:
            return MessageDeliveryResult(
                channel=self.name,
                status="IGNORED",
                delivered_blocks=0,
                ignored_blocks=ignored,
            )

        self.deliver(message.model_copy(update={"blocks": deliverable}))
        return MessageDeliveryResult(
            channel=self.name,
            status=self.delivery_status,
            delivered_blocks=len(deliverable),
            ignored_blocks=ignored,
        )

    @abstractmethod
    def deliver(self, message: StructuredMessage) -> None:
        """把已过滤的消息交给具体渠道。"""


__all__ = ["MessageChannel"]
