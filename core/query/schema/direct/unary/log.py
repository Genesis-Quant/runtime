"""unary.log 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import DirectOperator
from core.query.schema.fields import UnaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class DirectUnaryLogParams(StrictModel):
    """unary.log 不接收参数。"""


class DirectUnaryLogOperator(DirectOperator):
    """逐行执行 log。"""

    op: Literal['unary.log'] = Field(..., description='逐行执行 log。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryLogParams = Field(
        default_factory=DirectUnaryLogParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
