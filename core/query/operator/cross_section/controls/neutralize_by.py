"""controls.neutralize_by 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction
from core.query.dolphindb.common import (
    IS_FINITE_NUMBER,
)

from core.query.operator.base import CrossSectionOperator
from core.query.operator.fields import ControlsFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionControlsNeutralizeByParams(StrictModel):
    """controls.neutralize_by 参数。"""

    intercept: bool = Field(default=True, description="回归是否包含截距。")


class CrossSectionControlsNeutralizeByOperator(CrossSectionOperator):
    """按交易日执行分类和连续变量 OLS 中性化。"""

    op: Literal['controls.neutralize_by'] = Field(..., description='按交易日执行分类和连续变量 OLS 中性化。')
    fields: ControlsFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionControlsNeutralizeByParams = Field(
        default_factory=CrossSectionControlsNeutralizeByParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_controls_neutralize_by(target, controls, intercept) {
            /*
            对连续和分类控制变量执行截面 OLS 回归，返回目标变量的残差。

            只有 target 和所有控制变量均有效的行参加回归；无效行在输出中保持 NULL。数值控制变量直接进入设计矩阵，BOOL、SYMBOL 和 STRING
            控制变量先独热编码，并为每个分类变量删除第一个水平以避免完全共线。

            独热编码后会删除常量控制列。若没有剩余控制列、有效样本不超过 1，或样本数不大于控制列数加截距项数，则不调用 OLS，而是返回有效 target 的去均值结果。

            正常回归使用 target 作为因变量、controls 作为自变量。函数只返回残差，不自动取对数、去极值或标准化。

            Parameters
            ----------
            target : vector
                需要中性化的数值目标向量。
            controls : table
                控制变量表；每列是一个连续变量或分类变量。
            intercept : bool, default true
                true 时在设计矩阵中加入截距项；false 时强制回归通过原点。

            Returns
            -------
            result : vector[NUMBER]
                与 target 等长的 DOUBLE 残差向量；未参加回归的行保持 NULL。

            Notes
            -----
            NULL 处理：target 或任一控制变量为 NULL 的行不进入回归，并在结果同位置返回 NULL；数值列中的
            NaN 和正负无穷同样排除，分类控制的 NULL 不会自动创建为一个类别。若有效控制矩阵退化为无控制列，则对有效
            target 去均值。

            回归边界：分类列展开为去掉首类的哑变量，连续列直接作为数值控制；intercept 控制是否添加常数项。有效样本不足
            、秩亏或单样本截面通过最小二乘或去均值规则得到残差，函数不自动取对数、去极值或标准化。

            Examples
            --------
            >>> target = 2.0 4.0 3.0 7.0 5.0 9.0
            >>> industry = `bank`bank`tech`tech`retail`retail
            >>> size = 10.0 12.0 8.0 11.0 9.0 13.0
            >>> controls = table(industry, size)

            同时控制行业和连续市值变量：
            >>> cs_controls_neutralize_by(target, controls, true)
            [0.103448, -0.103448, -0.344828, 0.344828, 0.206897, -0.206897]

            >>> size = 8.0 9.0 10.0 11.0 12.0
            >>> target = 1.0 2.2 2.8 4.1 4.9
            >>> controls = table(size)

            只控制连续变量：
            >>> cs_controls_neutralize_by(target, controls, true)
            [-0.06, 0.17, -0.2, 0.13, -0.04]

            >>> target = 1.0 3.0 2.0 6.0 4.0 8.0
            >>> industry = `bank`bank`tech`tech`retail`retail
            >>> controls = table(industry)

            只控制分类变量：
            >>> cs_controls_neutralize_by(target, controls, true)
            [-1, 1, -2, 2, -2, 2]

            >>> target = 1.0 2.0 3.0 4.0 5.0
            >>> size = 8.0 9.0 10.0 11.0 12.0
            >>> target[1] = NULL
            >>> size[3] = NULL
            >>> controls = table(size)

            目标或控制变量缺失的行保持 NULL：
            >>> cs_controls_neutralize_by(target, controls, true)
            [0, NULL, 0, NULL, 0]

            >>> target = 1.0 2.0 4.0 8.0
            >>> constant = 1.0 1.0 1.0 1.0
            >>> controls = table(constant)

            控制变量为常量时退化为截面去均值：
            >>> cs_controls_neutralize_by(target, controls, true)
            [-2.75, -1.75, 0.25, 4.25]

            >>> target = 1.0 2.0
            >>> size = 8.0 9.0
            >>> controls = table(size)

            有效样本不足时退化为截面去均值：
            >>> cs_controls_neutralize_by(target, controls, true)
            [-0.5, 0.5]

            >>> target = 1.0 2.2 2.8 4.1 4.9
            >>> size = 8.0 9.0 10.0 11.0 12.0
            >>> controls = table(size)

            不包含截距项：
            >>> cs_controls_neutralize_by(target, controls, false)
            [-1.5051, -0.618235, -0.331373, 0.65549, 1.14235]
            */
            n = size(target)
            valid = is_finite_number(target)
            for (name in columnNames(controls)) {
                values = controls[name]
                if (type(values) in [BOOL, SYMBOL, STRING]) valid = valid && isValid(values)
                else valid = valid && is_finite_number(values)
            }
            result = array(DOUBLE, n, n, NULL)
            if (sum(valid) == 0) return result
            y = double(target[valid])
            x_table = controls[valid]
            category_names = array(STRING, 0)
            for (name in columnNames(x_table)) {
                if (type(x_table[name]) in [BOOL, SYMBOL, STRING]) category_names.append!(name)
            }
            encoded = x_table
            if (size(category_names) > 0) {
                encoded = oneHot(x_table, symbol(category_names))
                drop_names = array(STRING, 0)
                encoded_names = columnNames(encoded)
                for (name in category_names) {
                    candidates = encoded_names[startsWith(encoded_names, name + "_")]
                    baseline_name = name + "_" + string(min(x_table[name]))
                    if (baseline_name in candidates) drop_names.append!(baseline_name)
                }
                if (size(drop_names) == columns(encoded)) {
                    result[valid] = y - avg(y)
                    return result
                }
                if (size(drop_names) > 0) dropColumns!(encoded, symbol(drop_names))
            }
            constant_names = array(STRING, 0)
            for (name in columnNames(encoded)) {
                if (size(distinct(encoded[name])) <= 1) constant_names.append!(name)
            }
            if (size(constant_names) == columns(encoded)) {
                result[valid] = y - avg(y)
                return result
            }
            if (size(constant_names) > 0) dropColumns!(encoded, symbol(constant_names))
            column_count = columns(encoded)
            if (size(y) <= 1 || column_count == 0 || size(y) <= column_count + int(intercept)) {
                residual = y - avg(y)
            } else {
                residual = ols(y, matrix(encoded), intercept, 2).Residual
            }
            result[valid] = residual
            return result
        }
        """,
        dependencies=(IS_FINITE_NUMBER,)
    )
