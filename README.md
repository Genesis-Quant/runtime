# Seminar Core

本项目定义派生因子 DSL 的 Pydantic 校验模型，并生成由 DolphinDB 执行的完整算符脚本。Python 不计算因子，只负责校验节点、登记算符以及组合 DolphinDB 函数。

## 职责边界

DSL 分为三类：

| `type` | 分组语义 | `on` |
|---|---|---|
| `DIRECT` | 不分组，直接计算 | 禁止 |
| `TS` | 按 `code` 分组、按 `time` 排序 | 必填 |
| `CS` | 按 `time` 分组 | 必填 |

每个具体 Operator 文件只定义三部分：

1. 本算符的 `Params`，直接继承 `StrictModel`。
2. 本算符的 Operator 模型，完整声明 `type/op/fields/params`。
3. 纯计算 `DolphinDBFunction`，参数只能是本算符的 `fields + params`。

`on`、`source`、`code`、`time`、分组、排序和结果回填均由 DSL 执行层负责，不属于具体算符函数。TS/CS 模型保留 `on` 字段只是为了校验完整 DSL 节点；执行层计算 `on` 后才调用 Operator 的纯函数。

执行一个 TS/CS 节点时，运行层依次：

1. 递归计算 `fields` 和 `on`。
2. 校验 `on` 是与输入等长的 BOOL 向量，并将 NULL 视为 `false`。
3. 只保留 `on=true` 的行。
4. 按 TS 或 CS 规则建立分组上下文。
5. 用筛选后的 `fields` 调用纯 Operator 函数。
6. 将结果回填到原行，其他位置保持 NULL。

因此，TS 的滚动窗口不会计入 `on=false` 的行，CS 的均值、排名和回归也不会使用这些行。

## DSL 结构

DIRECT 节点：

```json
{
  "type": "DIRECT",
  "op": "binary.add",
  "fields": {"left": "close", "right": "dividend"},
  "params": {}
}
```

TS 节点：

```json
{
  "type": "TS",
  "op": "unary.rolling_mean",
  "fields": {"col": "close"},
  "params": {"window": 20, "min_periods": 10},
  "on": {
    "type": "DIRECT",
    "op": "binary.gt",
    "fields": {"left": "volume", "right": 0},
    "params": {}
  }
}
```

CS 节点：

```json
{
  "type": "CS",
  "op": "controls.neutralize_by",
  "fields": {
    "target": "factor",
    "controls": [
      "industry",
      {
        "type": "DIRECT",
        "op": "unary.log",
        "fields": {"col": "market_value"},
        "params": {}
      }
    ]
  },
  "params": {"intercept": true},
  "on": "eligible"
}
```

字符串操作数表示原始列或命名因子。字符串、日期、SYMBOL 和 NULL 常量应使用 `nullary.literal`，避免与列名混淆。

## 字段模型

| 组 | `fields` |
|---|---|
| `nullary` | `{}` |
| `unary` | `{"col": Operand}` |
| `binary` | `{"left": Operand, "right": Operand}` |
| `ternary` | `{"condition": Operand, "if_true": Operand, "if_false": Operand}` |
| `multiary` | `{"cols": list[Operand]}` |
| `grouped` | `{"col": Operand, "by": Operand}` |
| `controls` | `{"target": Operand, "controls": list[Operand]}` |

参数名、类型、默认值、范围和互斥规则以每个算符文件内的 `Params` 模型为唯一来源。所有模型启用严格类型、禁止额外字段，并拒绝 NaN 和正负无穷。

## 算符目录

当前共 231 个算符：DIRECT 75 个、TS 116 个、CS 40 个。

### DIRECT

- `nullary`: `false`, `literal`, `true`
- `unary`: `abs`, `acos`, `asin`, `atan`, `between`, `cast`, `ceil`, `clip`, `cos`, `day`, `day_of_year`, `exp`, `expm1`, `floor`, `get`, `is_finite`, `is_month_end`, `is_null`, `is_quarter_end`, `is_weekend`, `is_year_end`, `isin`, `log`, `log10`, `log1p`, `log2`, `month`, `neg`, `not`, `not_null`, `quarter`, `replace`, `round`, `sign`, `sin`, `sqrt`, `tan`, `week`, `weekday`, `year`
- `binary`: `add`, `and`, `days_between`, `div`, `eq`, `floor_div`, `ge`, `gt`, `le`, `lt`, `maximum`, `minimum`, `mod`, `mul`, `ne`, `null_if`, `or`, `pow`, `sub`, `xor`
- `ternary`: `where`
- `multiary`: `add`, `and`, `coalesce`, `count`, `max`, `mean`, `min`, `mul`, `or`, `std`, `var`

### TS

- `unary` 状态和累计：`bars_since`, `bfill`, `changed`, `consecutive_count`, `cum_count`, `cum_max`, `cum_mean`, `cum_min`, `cum_prod`, `cum_sum`, `diff`, `ffill`, `log_return`, `pct_change`, `shift`
- `unary` 滚动和扩展：`decay_linear`, `expanding_median`, `expanding_quantile`, `expanding_rank`, `expanding_rank_pct`, `expanding_sem`, `expanding_std`, `expanding_var`, `rolling_all`, `rolling_any`, `rolling_argmax`, `rolling_argmin`, `rolling_count`, `rolling_first`, `rolling_kurt`, `rolling_last`, `rolling_mad`, `rolling_max`, `rolling_mean`, `rolling_median`, `rolling_min`, `rolling_prod`, `rolling_quantile`, `rolling_rank`, `rolling_rank_pct`, `rolling_sem`, `rolling_skew`, `rolling_std`, `rolling_sum`, `rolling_true_count`, `rolling_var`, `rolling_zscore`
- `unary` 指数加权：`ewm_mean`, `ewm_std`, `ewm_var`
- `binary`: `cross_above`, `cross_below`, `ewm_corr`, `ewm_cov`, `expanding_beta`, `expanding_corr`, `expanding_cov`, `rolling_alpha`, `rolling_beta`, `rolling_corr`, `rolling_cov`, `rolling_residual`
- `talib`: `ad`, `adx`, `adxr`, `apo`, `aroon`, `aroonOsc`, `atr`, `avgPrice`, `bBands`, `beta`, `bop`, `cci`, `correl`, `dema`, `dx`, `ema`, `kama`, `linearreg`, `linearreg_angle`, `linearreg_intercept`, `linearreg_slope`, `ma`, `macd`, `medPrice`, `mfi`, `midPoint`, `midPrice`, `minus_di`, `minus_dm`, `mom`, `natr`, `obv`, `plus_di`, `plus_dm`, `ppo`, `roc`, `rocp`, `rocr`, `rocr100`, `rsi`, `sma`, `stddev`, `t3`, `tema`, `trange`, `trima`, `trix`, `tsf`, `typPrice`, `ultOsc`, `var`, `wclPrice`, `willr`, `wma`

### CS

- `unary`: `bottom_n`, `bottom_pct`, `count`, `demean`, `kurt`, `mad`, `max`, `mean`, `median`, `min`, `normalize_l1`, `normalize_l2`, `normalize_sum`, `qcut`, `quantile`, `rank`, `rank_dense`, `rank_normal`, `rank_pct`, `robust_zscore`, `skew`, `std`, `sum`, `top_n`, `top_pct`, `var`, `winsorize`, `winsorize_mad`, `zscore`
- `binary`: `alpha`, `beta`, `corr`, `cov`, `rank_corr`, `residual`
- `grouped`: `demean`, `mean`, `rank_pct`, `zscore`
- `controls`: `neutralize_by`

## Python 校验

导入 `core.operators` 会通过各级 `__init__.py` 导入全部算符。具体 Operator 在继承初始化时自动登记，不扫描文件，也没有单独的 registry 模块。

```python
from core.operators import Derivative

node = Derivative.model_validate(
    {
        "type": "DIRECT",
        "op": "binary.add",
        "fields": {"left": "close", "right": 1.0},
        "params": {},
    }
)
```

构造阶段会检查算符是否存在、字段和参数是否完整、TS/CS 是否提供 BOOL `on`，以及每个 Operator 的 DolphinDB 函数签名是否恰好等于 `fields + params`。

## DolphinDB 执行

生成完整脚本：

```powershell
uv run python -m core.dolphindb.script
```

该命令从已登记的 Operator 收集函数及其直接依赖，生成 [operators.dos](output/operators.dos)。算符函数不在 DOS 中重复维护，DOS 是 Python 定义的生成结果；`output` 目录不存在时会自动创建。

每个 Operator 的 `DolphinDBFunction.definition` 都在函数体内直接维护 pandas DataFrame API 风格文档，按 `Parameters`、`Returns`、`Notes` 和 `Examples` 组织。`Notes` 必须明确说明该算符自己的 NULL 处理、数值或窗口边界及输出语义；每个函数至少提供两个带真实输出的调用示例，复杂算符还会分别示范主要参数模式和边界分支。脚本生成器只按章节原样汇总函数，不动态拼接算符文档。

工具函数和 derive 执行层函数同样在函数体开头说明职责、筛选规则或错误语义，生成测试会拒绝任何缺少函数体注释的 DOS 函数。

## 测试与覆盖度

```powershell
uv run pytest
```

完整测试只连接现有 DolphinDB 服务，不会自行启动或重启服务。测试会加载生成脚本，并直接执行工具函数、DIRECT/TS/CS 算符及 derive 执行层。算符清单测试要求已登记模型与独立参考实现完全对应；数值结果由 pandas、NumPy、TA-Lib 参考结果以及 Hypothesis 随机输入与 DolphinDB 实际结果逐项比较，同时覆盖 NULL、空输入、全 false `on`、标量广播、退化截面和多阶段依赖等边界。

测试结束后，由 `pytest-cov` 生成 [Python coverage](output/python-coverage/index.html) 和 [python-coverage.xml](output/python-coverage.xml)，并同时检查 Python 行覆盖率和分支覆盖率达到 100%。DolphinDB 脚本没有伪造的行覆盖率统计；其有效性由函数清单完整性、真实数据库执行和独立结果差分共同验证。

加载脚本后，可在 DolphinDB 中计算命名因子：

```dos
source = table(
    2024.01.01 2024.01.02 2024.01.01 2024.01.02 as time,
    `A`A`B`B as code,
    1.0 3.0 2.0 4.0 as x
)

definitions = fromStdJson(
    "{\"x2\":{\"type\":\"DIRECT\",\"op\":\"binary.mul\",\"fields\":{\"left\":\"x\",\"right\":2},\"params\":{}}}"
)

result = compute_factors(source, definitions)
```

`compute_factors` 解析命名因子依赖、检测循环、缓存已计算结果，并返回原表加全部结果列。
