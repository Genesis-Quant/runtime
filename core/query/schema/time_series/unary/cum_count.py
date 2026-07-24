"""unary.cum_count 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import TimeSeriesOperator
from core.query.schema.fields import UnaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryCumCountParams(StrictModel):
    """unary.cum_count 参数。"""

    min_periods: int = Field(default=1, ge=1, description="产生结果所需的最少非空观测数。")


class TimeSeriesUnaryCumCountOperator(TimeSeriesOperator):
    """按股票执行 cum_count。"""

    op: Literal['unary.cum_count'] = Field(..., description='按股票执行 cum_count。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryCumCountParams = Field(
        default_factory=TimeSeriesUnaryCumCountParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
