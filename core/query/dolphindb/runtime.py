"""定义 DSL 执行层使用的 DolphinDB 公共函数。"""

from core.query.dolphindb.common.form import (
    IS_DICTIONARY_FORM,
    IS_SCALAR_FORM,
    IS_TABLE_FORM,
    IS_VECTOR_FORM,
)
from core.query.dolphindb.function import DolphinDBFunction

NORMALIZE_ON = DolphinDBFunction(
    """
    def normalize_on(on, n) {
        // 校验 on 为 BOOL，将标量广播为 n 行向量，并把 NULL 统一视为 false。
        if (type(on) != BOOL) {
            throw "DSL 的 on 必须是 BOOL，实际类型为 " + typestr(on)
        }
        result = on
        if (is_scalar_form(result)) result = take(result, n)
        if (!is_vector_form(result) || size(result) != n) {
            throw "DSL 的 on 必须是长度为 " + string(n) + " 的 BOOL 向量，实际为 " + typestr(result)
        }
        return nullFill(result, false)
    }
    """,
    dependencies=(IS_SCALAR_FORM, IS_VECTOR_FORM),
)

RESTORE_MASKED_ROWS = DolphinDBFunction(
    """
    def restore_masked_rows(selected_result, mask, n) {
        // 把筛选后的结果按 mask 回填到原始 n 行位置，未选中的行保持 NULL。
        result = array(type(selected_result), n, n, NULL)
        if (n == 0) return result
        if (sum(mask) == 0) return result
        indices = (0..(n - 1))[mask]
        result[indices] = selected_result
        return result
    }
    """
)

SAMPLE_OPERANDS = DolphinDBFunction(
    """
    def sample_operands(operands) {
        // 从每个操作数取一个样本，供空筛选分支推断算符返回类型。
        result = array(ANY, 0)
        for (operand in operands) {
            if (size(operand) == 0) result.append!(array(type(operand), 1, 1, NULL))
            else result.append!(take(operand, 1))
        }
        return result
    }
    """
)

SELECT_OPERANDS = DolphinDBFunction(
    """
    def select_operands(operands, mask) {
        // 使用同一个行掩码筛选全部操作数，并保持操作数顺序不变。
        result = array(ANY, 0)
        for (operand in operands) result.append!(operand[mask])
        return result
    }
    """
)

APPLY_TIME_SERIES = DolphinDBFunction(
    """
    def apply_time_series(func, operands, on, code, time, empty_result) {
        // 仅对 on=true 的行按 code 分组、time 排序执行时序函数，再恢复原始行位置。
        n = size(operands[0])
        mask = normalize_on(on, n)
        if (n == 0) return empty_result
        if (sum(mask) == 0) {
            sample = unifiedCall(func, sample_operands(operands))
            return restore_masked_rows(sample, mask, n)
        }
        selected = contextby(func, select_operands(operands, mask), code[mask], time[mask])
        return restore_masked_rows(selected, mask, n)
    }
    """,
    dependencies=(
        NORMALIZE_ON,
        RESTORE_MASKED_ROWS,
        SAMPLE_OPERANDS,
        SELECT_OPERANDS,
    ),
)

APPLY_CROSS_SECTION = DolphinDBFunction(
    """
    def apply_cross_section(func, operands, on, time, empty_result) {
        // 仅对 on=true 的行按 time 分组执行截面函数，再恢复原始行位置。
        n = size(operands[0])
        mask = normalize_on(on, n)
        if (n == 0) return empty_result
        if (sum(mask) == 0) {
            sample = unifiedCall(func, sample_operands(operands))
            return restore_masked_rows(sample, mask, n)
        }
        selected = contextby(func, select_operands(operands, mask), time[mask])
        return restore_masked_rows(selected, mask, n)
    }
    """,
    dependencies=(
        NORMALIZE_ON,
        RESTORE_MASKED_ROWS,
        SAMPLE_OPERANDS,
        SELECT_OPERANDS,
    ),
)

APPLY_GROUPED_CROSS_SECTION = DolphinDBFunction(
    """
    def apply_grouped_cross_section(func, operands, on, time, by, empty_result) {
        // 排除 on=false 和 by=NULL 的行，按 time 与 by 联合分组执行截面函数。
        n = size(operands[0])
        mask = normalize_on(on, n) && !isNull(by)
        if (n == 0) return empty_result
        if (sum(mask) == 0) {
            sample = unifiedCall(func, sample_operands(operands))
            return restore_masked_rows(sample, mask, n)
        }
        selected = contextby(func, select_operands(operands, mask), (time[mask], by[mask]))
        return restore_masked_rows(selected, mask, n)
    }
    """,
    dependencies=(
        NORMALIZE_ON,
        RESTORE_MASKED_ROWS,
        SAMPLE_OPERANDS,
        SELECT_OPERANDS,
    ),
)

APPLY_CONTROLLED_CROSS_SECTION = DolphinDBFunction(
    """
    def apply_controlled_cross_section(func, target, controls, on, time) {
        // 按交易日向控制变量截面函数传入 target 和 controls，并把结果回填到原始行。
        n = size(target)
        mask = normalize_on(on, n)
        result = array(DOUBLE, n, n, NULL)
        if (n == 0) return result
        if (sum(mask) == 0) return result
    
        selected_indices = (0..(n - 1))[mask]
        selected_time = time[mask]
        for (current_date in distinct(selected_time)) {
            row_indices = selected_indices[selected_time == current_date]
            result[row_indices] = func(target[row_indices], controls[row_indices])
        }
        return result
    }
    """,
    dependencies=(NORMALIZE_ON,),
)

BUILD_CONTROL_TABLE = DolphinDBFunction(
    """
    def build_control_table(values) {
        // 将按顺序给出的控制变量向量组装成 control0、control1 等命名列的表。
        if (size(values) == 0) throw "控制变量至少包含一列"
        columns = dict(STRING, ANY)
        for (index in 0..(size(values) - 1)) {
            columns["control" + string(index)] = values[index]
        }
        return transpose(columns)
    }
    """
)

REQUIRE_KEY = DolphinDBFunction(
    """
    def require_key(object, key, location) {
        // 校验 object 为字典且包含必填 key，错误信息保留 DSL 所在位置。
        if (!is_dictionary_form(object)) {
            throw location + " 必须是字典，实际类型为 " + typestr(object)
        }
        if (!(key in object)) throw location + " 缺少必填键 " + key
        return object[key]
    }
    """,
    dependencies=(IS_DICTIONARY_FORM,),
)

REQUIRE_VECTOR = DolphinDBFunction(
    """
    def require_vector(value, n, location) {
        // 将标量或单元素向量广播为 n 行，并拒绝其他长度或数据形态不符合要求的结果。
        result = value
        if (is_scalar_form(result)) result = take(result, n)
        if (is_vector_form(result) && size(result) == 1 && n != 1) result = take(result, n)
        if (!is_vector_form(result) || size(result) != n) {
            throw location + " 必须返回长度为 " + string(n) + " 的向量，实际为 " + typestr(result)
        }
        return result
    }
    """,
    dependencies=(IS_SCALAR_FORM, IS_VECTOR_FORM),
)

REQUIRE_COLUMN = DolphinDBFunction(
    """
    def require_column(source, name, operation) {
        // 读取算符必需的输入列；缺列时报告具体算符和列名。
        if (!(name in columnNames(source))) {
            throw operation + " 要求输入表包含列 " + name
        }
        return source[name]
    }
    """
)

EVALUATE_DEFINITION = DolphinDBFunction(
    """
    def evaluate_definition(evaluator, source, definitions, mutable cache, mutable states, name) {
        // 按名称递归计算因子，使用 cache 复用结果，并通过 states 检测循环依赖。
        if (name in cache) return cache[name]
        if (name in states && states[name] == 1) {
            throw "命名因子存在循环依赖，重复进入 " + name
        }
        if (!(name in definitions)) throw "不存在命名因子 " + name
    
        states[name] = 1
        value = evaluator(source, definitions, cache, states, definitions[name])
        value = require_vector(value, source.rows(), "命名因子 " + name)
        cache[name] = value
        states[name] = 2
        return value
    }
    """
)

EVALUATE_OPERAND = DolphinDBFunction(
    """
    def evaluate_operand(evaluator, source, definitions, mutable cache, mutable states, operand) {
        // 将操作数解析为嵌套 DSL、命名因子、输入列或原样返回的标量。
        if (is_dictionary_form(operand)) {
            result = evaluator(source, definitions, cache, states, operand)
            if (is_vector_form(result) && size(result) == 1 && source.rows() != 1) {
                return take(result, source.rows())
            }
            return result
        }
        if (is_scalar_form(operand) && type(operand) == STRING) {
            if (operand in definitions) {
                return evaluate_definition(evaluator, source, definitions, cache, states, operand)
            }
            if (operand in columnNames(source)) return source[operand]
            throw "DSL 引用了不存在的列或命名因子 " + operand
        }
        if (is_scalar_form(operand)) return operand
        throw "DSL 操作数必须是列名、命名因子、嵌套节点或标量，实际为 " + typestr(operand)
    }
    """,
    dependencies=(IS_DICTIONARY_FORM, IS_SCALAR_FORM, IS_VECTOR_FORM),
)

EVALUATE_OPERANDS = DolphinDBFunction(
    """
    def evaluate_operands(evaluator, source, definitions, mutable cache, mutable states, operands) {
        // 依次解析操作数列表，并以 ANY 数组保留不同结果类型。
        result = array(ANY, 0)
        for (operand in operands) {
            result.append!(evaluate_operand(evaluator, source, definitions, cache, states, operand))
        }
        return result
    }
    """
)

EVALUATE_FIELDS = DolphinDBFunction(
    """
    def evaluate_fields(evaluator, source, definitions, mutable cache, mutable states, fields) {
        // 解析 DSL fields 字典；向量字段按操作数列表处理，其余字段按单个操作数处理。
        if (!is_dictionary_form(fields)) {
            throw "DSL fields 必须是字典，实际类型为 " + typestr(fields)
        }
        result = dict(STRING, ANY)
        for (name in string(fields.keys())) {
            operand = fields[name]
            if (is_vector_form(operand)) {
                result[name] = evaluate_operands(evaluator, source, definitions, cache, states, operand)
            } else {
                result[name] = evaluate_operand(evaluator, source, definitions, cache, states, operand)
            }
        }
        return result
    }
    """,
    dependencies=(IS_DICTIONARY_FORM, IS_VECTOR_FORM),
)

EVALUATE_NODE = DolphinDBFunction(
    """
    def evaluate_node(source, definitions, mutable cache, mutable states, node) {
        // 校验 DSL 节点公共结构，并按 DIRECT、TS 或 CS 分发到对应执行器。
        node_type = require_key(node, "type", "DSL 节点")
        require_key(node, "op", "DSL 节点")
        require_key(node, "fields", "DSL 节点")
        require_key(node, "params", "DSL 节点")
        if (node_type == "DIRECT") {
            if ("on" in node) throw "DIRECT 节点禁止包含 on"
            return evaluate_direct(evaluate_node, source, definitions, cache, states, node)
        }
        if (node_type == "TS") {
            require_key(node, "on", "TS 节点")
            return evaluate_time_series(evaluate_node, source, definitions, cache, states, node)
        }
        if (node_type == "CS") {
            require_key(node, "on", "CS 节点")
            return evaluate_cross_section(evaluate_node, source, definitions, cache, states, node)
        }
        throw "未知 DSL 类型 " + string(node_type)
    }
    """
)

PARSE_DEFINITIONS = DolphinDBFunction(
    """
    def parse_definitions(definitions) {
        // 接受标准 JSON 字符串或 ANY 字典，并规范化为命名因子定义集合。
        result = definitions
        if (is_scalar_form(result) && type(result) == STRING) result = fromStdJson(result)
        if (!is_dictionary_form(result)) {
            throw "派生因子集合必须是字典或标准 JSON 对象，实际为 " + typestr(result)
        }
        if (type(result) != ANY) {
            throw "派生因子字典的值类型必须为 ANY，实际为 " + typestr(result)
        }
        return result
    }
    """,
    dependencies=(IS_DICTIONARY_FORM, IS_SCALAR_FORM),
)

COMPUTE_FACTORS = DolphinDBFunction(
    """
    def compute_factors(source, definitions) {
        // 计算全部命名因子并追加到 source 副本，同时拒绝因子名与输入列冲突。
        if (!is_table_form(source)) {
            throw "compute_factors 的 source 必须是 table，实际为 " + typestr(source)
        }
        parsed = parse_definitions(definitions)
        names = string(parsed.keys())
        conflicts = names[names in columnNames(source)]
        if (size(conflicts) > 0) {
            throw "命名因子与输入列重名：" + concat(conflicts, ", ")
        }
    
        cache = dict(STRING, ANY)
        states = dict(STRING, INT)
        result = select * from source
        for (name in names) {
            result[name] = evaluate_definition(evaluate_node, source, parsed, cache, states, name)
        }
        return result
    }
    """,
    dependencies=(IS_TABLE_FORM,),
)

TOOL_FUNCTIONS = (
    NORMALIZE_ON,
    RESTORE_MASKED_ROWS,
    SAMPLE_OPERANDS,
    SELECT_OPERANDS,
    APPLY_TIME_SERIES,
    APPLY_CROSS_SECTION,
    APPLY_GROUPED_CROSS_SECTION,
    APPLY_CONTROLLED_CROSS_SECTION,
    BUILD_CONTROL_TABLE,
    REQUIRE_KEY,
    REQUIRE_VECTOR,
    REQUIRE_COLUMN,
)

DERIVE_HELPER_FUNCTIONS = (
    EVALUATE_DEFINITION,
    EVALUATE_OPERAND,
    EVALUATE_OPERANDS,
    EVALUATE_FIELDS,
)

DERIVE_ENTRY_FUNCTIONS = (
    EVALUATE_NODE,
    PARSE_DEFINITIONS,
    COMPUTE_FACTORS,
)

RUNTIME_FUNCTIONS = (
    *TOOL_FUNCTIONS,
    *DERIVE_HELPER_FUNCTIONS,
    *DERIVE_ENTRY_FUNCTIONS,
)

__all__ = [
    "APPLY_CONTROLLED_CROSS_SECTION",
    "APPLY_CROSS_SECTION",
    "APPLY_GROUPED_CROSS_SECTION",
    "APPLY_TIME_SERIES",
    "BUILD_CONTROL_TABLE",
    "COMPUTE_FACTORS",
    "DERIVE_ENTRY_FUNCTIONS",
    "DERIVE_HELPER_FUNCTIONS",
    "EVALUATE_DEFINITION",
    "EVALUATE_FIELDS",
    "EVALUATE_NODE",
    "EVALUATE_OPERAND",
    "EVALUATE_OPERANDS",
    "NORMALIZE_ON",
    "PARSE_DEFINITIONS",
    "REQUIRE_COLUMN",
    "REQUIRE_KEY",
    "REQUIRE_VECTOR",
    "RESTORE_MASKED_ROWS",
    "RUNTIME_FUNCTIONS",
    "SAMPLE_OPERANDS",
    "SELECT_OPERANDS",
    "TOOL_FUNCTIONS",
]
