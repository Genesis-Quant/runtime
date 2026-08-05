"""只写标准输出、不产生外部副作用的 Console 渠道。"""

from runtime.messaging.channels.base import MessageChannel
from runtime.messaging.models import StructuredMessage


class ConsoleMessageChannel(MessageChannel):
    name = "console"
    delivery_status = "PRINTED"

    def deliver(self, message: StructuredMessage) -> None:
        print(message.model_dump_json(indent=2))


__all__ = ["ConsoleMessageChannel"]
