"""unary.sqrt 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import DirectOperator
from core.query.schema.fields import UnaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class DirectUnarySqrtParams(StrictModel):
    """unary.sqrt 不接收参数。"""


class DirectUnarySqrtOperator(DirectOperator):
    """逐行执行 sqrt。"""

    op: Literal['unary.sqrt'] = Field(..., description='逐行执行 sqrt。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnarySqrtParams = Field(
        default_factory=DirectUnarySqrtParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
