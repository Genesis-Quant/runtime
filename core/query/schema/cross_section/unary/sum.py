"""unary.sum 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import CrossSectionOperator
from core.query.schema.fields import UnaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnarySumParams(StrictModel):
    """unary.sum 不接收参数。"""


class CrossSectionUnarySumOperator(CrossSectionOperator):
    """按交易日广播 sum 统计量。"""

    op: Literal['unary.sum'] = Field(..., description='按交易日广播 sum 统计量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnarySumParams = Field(
        default_factory=CrossSectionUnarySumParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
