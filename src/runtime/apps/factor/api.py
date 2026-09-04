"""使用因子 DSL 数据在 DolphinDB 中完成多因子分析。"""

from typing import Any

import numpy as np

from runtime.database import create_session
from runtime.database.session import redirect_session_output
from runtime.utils import get_stock_metadata, logger

from ..query import api as query_api
from .result import FactorAnalysisResult
from .schema import FactorAnalysisParameters, FactorIndustryColumn

SOURCE_REF = "coreFactorSourceData"
COMPUTED_REF = "coreFactorCOMPUTEDData"
FILTERED_REF = "coreFactorFilteredData"
CODES_SOURCE_REF = "coreFactorCodesSourceData"
CODES_COMPUTED_REF = "coreFactorCodesComputedData"
CODES_FILTERED_REF = "coreFactorCodesFilteredData"
CODES_DATA_REF = "coreFactorCodesData"

INPUT_REF = "coreFactorInputData"
PROCESSED_REF = "coreFactorProcessedData"


def analyze_factors(
        dataset_query: dict[str, Any],
        factor_columns: list[str],
        return_columns: list[str],
        *,
        return_specs: dict[str, Any],
        session: Any | None = None,
        codes_query: dict[str, Any] | None = None,
        n_groups: int = 5,
        n_select: int = 10,
        preprocess: bool = True,
        market_value_column: str = "circ_mv",
        industry_column: FactorIndustryColumn = "industry",
) -> FactorAnalysisResult:
    """生成预处理因子表，并把后续分析交给惰性结果对象。"""
    parameters = FactorAnalysisParameters.model_validate({
        "dataset_query": dataset_query,
        "codes_query": codes_query,
        "factor_columns": factor_columns,
        "return_columns": return_columns,
        "return_specs": return_specs,
        "n_groups": n_groups,
        "n_select": n_select,
        "preprocess": preprocess,
        "market_value_column": market_value_column,
        "industry_column": industry_column,
    })
    owns_session = session is None
    current_session = create_session() if owns_session else session
    redirect_session_output(current_session)

    try:
        query = parameters.dataset_query
        if parameters.codes_query is not None:
            codes = query_api.execute_codes_query(
                parameters.codes_query,
                session=current_session,
                source_ref=CODES_SOURCE_REF,
                computed_ref=CODES_COMPUTED_REF,
                filtered_ref=CODES_FILTERED_REF,
                data_ref=CODES_DATA_REF,
            )
            query = query.model_copy(update={"codes": codes})
            parameters.dataset_query = query
        query_api.build_query_table(
            query,
            session=current_session,
            source_ref=SOURCE_REF,
            computed_ref=COMPUTED_REF,
            filtered_ref=FILTERED_REF,
            data_ref=INPUT_REF
        )

        upload_values = {
            "coreFactorColumns": np.asarray(parameters.factor_columns, dtype=str),
            "coreFactorReturnColumns": np.asarray(parameters.return_columns, dtype=str),
            "coreFactorTurnoverPeriods": np.asarray(
                sorted({spec.periods for spec in parameters.return_specs.values()}),
                dtype=np.int32,
            ),
            "coreFactorGroupCount": parameters.n_groups,
            "coreFactorSelectionCount": parameters.n_select,
            "coreFactorMarketValueColumn": parameters.market_value_column,
            "coreFactorIndustryColumn": parameters.industry_column,
        }

        if parameters.preprocess and parameters.industry_column == "industry":
            upload_values["coreFactorCodeToIndustry"] = get_stock_metadata()[2]

        current_session.upload(upload_values)

        logger.info("session.run: 加载 factor 模块")
        current_session.run("use factor")

        if parameters.preprocess:
            legacy_industry = parameters.industry_column == "industry"
            industry_assignment = (
                f'{INPUT_REF}["industry"] = '
                f'coreFactorCodeToIndustry[{INPUT_REF}["code"]]'
                if legacy_industry
                else ""
            )
            logger.info(
                "session.run: 执行 MAD 去极值、标准化、中性化和分组，"
                f"行业列={parameters.industry_column}"
            )
            current_session.run(f"""
                {industry_assignment}
                {PROCESSED_REF} = factor::factorPreprocess(
                    {INPUT_REF},
                    coreFactorColumns,
                    coreFactorGroupCount,
                    "time",
                    "code",
                    coreFactorMarketValueColumn,
                    coreFactorIndustryColumn
                )
            """)
        else:
            logger.info("session.run: 跳过内置预处理，直接使用 DSL 输出")
            current_session.run(f"{PROCESSED_REF} = {INPUT_REF}")

        logger.success("因子预处理已在 DolphinDB 会话中生成")

        return FactorAnalysisResult(
            session=current_session,
            parameters=parameters,
            source_ref=SOURCE_REF,
            computed_ref=COMPUTED_REF,
            filtered_ref=FILTERED_REF,
            processed_ref=PROCESSED_REF,
        )
    except Exception:
        logger.exception(f"因子分析失败")

        if owns_session:
            current_session.close()
        raise
