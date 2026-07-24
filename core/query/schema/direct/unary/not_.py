"""unary.not 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import DirectOperator
from core.query.schema.fields import UnaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class DirectUnaryNotParams(StrictModel):
    """unary.not 不接收参数。"""


class DirectUnaryNotOperator(DirectOperator):
    """逐行逻辑非。"""

    op: Literal['unary.not'] = Field(..., description='逐行逻辑非。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryNotParams = Field(
        default_factory=DirectUnaryNotParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
