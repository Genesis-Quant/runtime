"""binary.expanding_beta 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import TimeSeriesOperator
from core.query.schema.fields import BinaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class TimeSeriesBinaryExpandingBetaParams(StrictModel):
    """binary.expanding_beta 参数。"""

    min_periods: int = Field(default=1, ge=1, description="产生结果所需的最少非空观测数。")


class TimeSeriesBinaryExpandingBetaOperator(TimeSeriesOperator):
    """按股票执行 expanding_beta。"""

    op: Literal['binary.expanding_beta'] = Field(..., description='按股票执行 expanding_beta。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesBinaryExpandingBetaParams = Field(
        default_factory=TimeSeriesBinaryExpandingBetaParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
