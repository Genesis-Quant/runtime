"""unary.top_n 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import CrossSectionOperator
from core.query.schema.fields import UnaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryTopNParams(StrictModel):
    """unary.top_n 参数。"""

    n: int = Field(..., ge=1, description="需要选择的股票数量。")


class CrossSectionUnaryTopNOperator(CrossSectionOperator):
    """按交易日执行 top_n 选择。"""

    op: Literal['unary.top_n'] = Field(..., description='按交易日执行 top_n 选择。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryTopNParams = Field(
        default_factory=CrossSectionUnaryTopNParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
