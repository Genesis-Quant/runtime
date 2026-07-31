"""使用因子 DSL 数据在 DolphinDB 中完成多因子分析。"""

from typing import Any, Literal

import numpy as np

from core.database import create_session
from core.database.session import redirect_session_output
from core.utils import get_stock_metadata, logger

from ..query import api as query_api
from . import result, schema

SOURCE_REF = "coreFactorSourceData"
COMPUTED_REF = "coreFactorCOMPUTEDData"
FILTERED_REF = "coreFactorFilteredData"

INPUT_REF = "coreFactorInputData"
PROCESSED_REF = "coreFactorProcessedData"


# TODO remove
def _industry_metadata(
        level: Literal["industry", "sector"],
) -> tuple[np.ndarray, np.ndarray]:
    """读取并校验用于服务端连接的股票行业向量。"""
    _, stock_industries, _ = get_stock_metadata()
    values = stock_industries.loc[:, ["code", level]].copy()
    valid = (
            values["code"].notna()
            & values[level].notna()
            & values["code"].astype("string").str.strip().ne("")
            & values[level].astype("string").str.strip().ne("")
    )
    values = values.loc[valid].drop_duplicates("code", keep="first")
    if values.empty:
        raise RuntimeError(f"股票元数据没有可用的 {level} 行业映射")
    return (
        values["code"].astype(str).to_numpy(),
        values[level].astype(str).to_numpy(),
    )


def analyze_factors(
        dataset_query: dict[str, Any],
        factor_columns: list[str],
        return_columns: list[str],
        *,
        session: Any | None = None,
        n_groups: int = 5,
        preprocess: bool = True,
        market_value_column: str = "circ_mv",
        industry_level: Literal["industry", "sector"] = "industry",
) -> result.FactorAnalysisResult:
    """按需预处理一个或多个因子，并生成 IC 和市值加权分组收益。"""
    parameters = schema.FactorAnalysisParameters.model_validate({
        "dataset_query": dataset_query,
        "factor_columns": factor_columns,
        "return_columns": return_columns,
        "n_groups": n_groups,
        "preprocess": preprocess,
        "market_value_column": market_value_column,
        "industry_level": industry_level,
    })
    owns_session = session is None
    current_session = create_session() if owns_session else session
    redirect_session_output(current_session)

    try:
        query = parameters.dataset_query
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
            "coreFactorGroupCount": parameters.n_groups,
            "coreFactorMarketValueColumn": parameters.market_value_column,
        }

        if parameters.preprocess:
            industry_codes, industry_values = _industry_metadata(parameters.industry_level)
            upload_values.update({
                "coreFactorIndustryCodes": industry_codes,
                "coreFactorIndustryValues": industry_values,
            })

        current_session.upload(upload_values)

        logger.info("session.run: 加载 factor 模块")
        current_session.run("use factor")

        if parameters.preprocess:
            logger.info("session.run: 执行 MAD 去极值、标准化、中性化和分组")
            current_session.run(f"""
                coreFactorIndustryData = table(
                    symbol(coreFactorIndustryCodes) as code,
                    symbol(coreFactorIndustryValues) as {parameters.industry_level}
                )
                {INPUT_REF} = lj({INPUT_REF}, coreFactorIndustryData, `code)
                coreFactorMissingIndustryCodes =
                    exec distinct code
                    from {INPUT_REF}
                    where isNull({parameters.industry_level})
                if (size(coreFactorMissingIndustryCodes) > 0) {{
                    throw "industry metadata is missing for codes: " + string(coreFactorMissingIndustryCodes)
                }}
                {PROCESSED_REF} = factor::factorPreprocess(
                    {INPUT_REF},
                    coreFactorColumns,
                    coreFactorGroupCount,
                    "time",
                    "code",
                    coreFactorMarketValueColumn,
                    "{parameters.industry_level}"
                )
            """)
        else:
            logger.info("session.run: 跳过内置预处理，直接使用 DSL 输出")
            current_session.run(f"{PROCESSED_REF} = {INPUT_REF}")

        information_coefficient_refs: dict[str, str] = {}
        group_return_refs: dict[str, str] = {}
        for index, factor in enumerate(parameters.factor_columns):
            ic_ref = f"coreFactorInformationCoefficient{index}"
            group_ref = f"coreFactorGroupReturns{index}"
            current_session.upload({"coreFactorCurrentColumn": factor})

            logger.info(f"session.run: 计算因子 {factor} 的 IC 和分组收益")
            current_session.run(f"""
                {ic_ref} = factor::factorInformationCoefficient(
                        {PROCESSED_REF},
                        coreFactorReturnColumns,
                        coreFactorCurrentColumn,
                        "time"
                )
                {group_ref} = factor::factorGroupReturns(
                        {PROCESSED_REF},
                        coreFactorReturnColumns,
                        coreFactorCurrentColumn,
                        coreFactorGroupCount,
                        "time",
                        "code",
                        coreFactorMarketValueColumn
                )
            """)
            information_coefficient_refs[factor] = ic_ref
            group_return_refs[factor] = group_ref

        logger.success("因子分析已在 DolphinDB 会话中生成")

        return result.FactorAnalysisResult(
            session=current_session,
            factor_columns=parameters.factor_columns,
            return_columns=parameters.return_columns,
            processed_ref=PROCESSED_REF,
            information_coefficient_refs=information_coefficient_refs,
            group_return_refs=group_return_refs,
        )
    except Exception:
        logger.exception(f"因子分析失败")

        if owns_session:
            current_session.close()
        raise


__all__ = ["analyze_factors"]
