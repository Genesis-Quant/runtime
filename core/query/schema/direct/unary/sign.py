"""unary.sign 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import DirectOperator
from core.query.schema.fields import UnaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class DirectUnarySignParams(StrictModel):
    """unary.sign 不接收参数。"""


class DirectUnarySignOperator(DirectOperator):
    """逐行执行 sign。"""

    op: Literal['unary.sign'] = Field(..., description='逐行执行 sign。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnarySignParams = Field(
        default_factory=DirectUnarySignParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
