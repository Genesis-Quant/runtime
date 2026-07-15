"""unary.winsorize_mad 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryWinsorizeMadParams(StrictModel):
    """unary.winsorize_mad 参数。"""

    n: float = Field(default=3.0, gt=0, allow_inf_nan=False, description="MAD 倍数。")
    scale: float = Field(default=1.4826, gt=0, allow_inf_nan=False, description="MAD 尺度系数。")


class CrossSectionUnaryWinsorizeMadOperator(CrossSectionOperator):
    """按交易日使用 MAD 缩尾。"""

    op: Literal['unary.winsorize_mad'] = Field(..., description='按交易日使用 MAD 缩尾。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryWinsorizeMadParams = Field(
        default_factory=CrossSectionUnaryWinsorizeMadParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_winsorize_mad(col, n, scale) {
            /*
            使用中位数与 MAD 给出的上下界对当前截面缩尾。

            上下界为 median(col) ± n * scale * MAD(col)。超出边界的值被截断到边界，范围内的值保持不变。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。
            n : float, default 3.0
                MAD 边界倍数，必须大于 0。
            scale : float, default 1.4826
                MAD 尺度系数。默认 1.4826 使正态分布下的 MAD 与标准差尺度近似一致。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Examples
            --------
            >>> col = 1.0 2.0 3.0 4.0 100.0

            使用 1.0 倍 MAD 边界：
            >>> cs_unary_winsorize_mad(col, 1.0, 1.4826)
            [1.5174, 2, 3, 4, 4.4826]

            使用 2.0 倍 MAD 边界：
            >>> cs_unary_winsorize_mad(col, 2.0, 1.4826)
            [1, 2, 3, 4, 5.9652]

            使用 3.0 倍 MAD 边界：
            >>> cs_unary_winsorize_mad(col, 3.0, 1.4826)
            [1, 2, 3, 4, 7.4478]
            */
            center = med(col)
            distance = mad(col, true) * scale * n
            return iif(col < center - distance, center - distance, iif(col > center + distance, center + distance, col))
        }
        """
    )
