"""unary.floor 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import DirectOperator
from core.query.schema.fields import UnaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class DirectUnaryFloorParams(StrictModel):
    """unary.floor 不接收参数。"""


class DirectUnaryFloorOperator(DirectOperator):
    """逐行执行 floor。"""

    op: Literal['unary.floor'] = Field(..., description='逐行执行 floor。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryFloorParams = Field(
        default_factory=DirectUnaryFloorParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
