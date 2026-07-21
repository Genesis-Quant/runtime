"""定义四个财报接口各自独立的数据更新 Worker。"""

from typing import ClassVar

import numpy as np
import pandas as pd

from core.utils import pro

from .base import StockWorker


FLOW_SUFFIXES = ("ttm", "1", "2", "3", "4")
BALANCE_SHEET_FACTORS = tuple(
    """
    total_share cap_rese undistr_porfit surplus_rese special_rese money_cap
    trad_asset notes_receiv accounts_receiv oth_receiv prepayment div_receiv
    int_receiv inventories amor_exp nca_within_1y sett_rsrv loanto_oth_bank_fi
    premium_receiv reinsur_receiv reinsur_res_receiv pur_resale_fa oth_cur_assets
    total_cur_assets fa_avail_for_sale htm_invest lt_eqt_invest invest_real_estate
    time_deposits oth_assets lt_rec fix_assets cip const_materials fixed_assets_disp
    produc_bio_assets oil_and_gas_assets intan_assets r_and_d goodwill lt_amor_exp
    defer_tax_assets decr_in_disbur oth_nca total_nca cash_reser_cb depos_in_oth_bfi
    prec_metals deriv_assets rr_reins_une_prem rr_reins_outstd_cla rr_reins_lins_liab
    rr_reins_lthins_liab refund_depos ph_pledge_loans refund_cap_depos
    indep_acct_assets client_depos client_prov transac_seat_fee invest_as_receiv
    total_assets lt_borr st_borr cb_borr depos_ib_deposits loan_oth_bank trading_fl
    notes_payable acct_payable adv_receipts sold_for_repur_fa comm_payable
    payroll_payable taxes_payable int_payable div_payable oth_payable acc_exp
    deferred_inc st_bonds_payable payable_to_reinsurer rsrv_insur_cont
    acting_trading_sec acting_uw_sec non_cur_liab_due_1y oth_cur_liab total_cur_liab
    bond_payable lt_payable specific_payables estimated_liab defer_tax_liab
    defer_inc_non_cur_liab oth_ncl total_ncl depos_oth_bfi deriv_liab depos
    agency_bus_liab oth_liab prem_receiv_adva depos_received ph_invest
    reser_une_prem reser_outstd_claims reser_lins_liab reser_lthins_liab
    indept_acc_liab pledge_borr indem_payable policy_div_payable total_liab
    treasury_share ordin_risk_reser forex_differ invest_loss_unconf minority_int
    total_hldr_eqy_exc_min_int total_hldr_eqy_inc_min_int total_liab_hldr_eqy
    lt_payroll_payable oth_comp_income oth_eqt_tools oth_eqt_tools_p_shr
    lending_funds acc_receivable st_fin_payable payables hfs_assets hfs_sales
    cost_fin_assets fair_value_fin_assets contract_assets contract_liab
    accounts_receiv_bill accounts_pay oth_rcv_total fix_assets_total cip_total
    oth_pay_total long_pay_total debt_invest oth_debt_invest
    """.split()
)
INCOME_RAW_FACTORS = tuple(
    """
    total_revenue revenue int_income prem_earned comm_income n_commis_income
    n_oth_income n_oth_b_income prem_income out_prem une_prem_reser reins_income
    n_sec_tb_income n_sec_uw_income n_asset_mg_income oth_b_income
    fv_value_chg_gain invest_income ass_invest_income forex_gain total_cogs oper_cost
    int_exp comm_exp biz_tax_surchg sell_exp admin_exp fin_exp assets_impair_loss
    prem_refund compens_payout reser_insur_liab div_payt reins_exp oper_exp
    compens_payout_refu insur_reser_refu reins_cost_refund other_bus_cost
    operate_profit non_oper_income non_oper_exp nca_disploss total_profit income_tax
    n_income n_income_attr_p minority_gain oth_compr_income t_compr_income
    compr_inc_attr_p compr_inc_attr_m_s ebit ebitda insurance_exp undist_profit
    distable_profit rd_exp fin_exp_int_exp fin_exp_int_inc transfer_surplus_rese
    transfer_housing_imprest transfer_oth adj_lossgain withdra_legal_surplus
    withdra_legal_pubfund withdra_biz_devfund withdra_rese_fund withdra_oth_ersu
    workers_welfare distr_profit_shrhder prfshare_payable_dvd comshare_payable_dvd
    capit_comstock_div continued_net_profit
    """.split()
)
CASHFLOW_RAW_FACTORS = tuple(
    """
    net_profit finan_exp c_fr_sale_sg recp_tax_rends n_depos_incr_fi
    n_incr_loans_cb n_inc_borr_oth_fi prem_fr_orig_contr n_incr_insured_dep
    n_reinsur_prem n_incr_disp_tfa ifc_cash_incr n_incr_disp_faas
    n_incr_loans_oth_bank n_cap_incr_repur c_fr_oth_operate_a c_inf_fr_operate_a
    c_paid_goods_s c_paid_to_for_empl c_paid_for_taxes n_incr_clt_loan_adv
    n_incr_dep_cbob c_pay_claims_orig_inco pay_handling_chrg pay_comm_insur_plcy
    oth_cash_pay_oper_act st_cash_out_act n_cashflow_act oth_recp_ral_inv_act
    c_disp_withdrwl_invest c_recp_return_invest n_recp_disp_fiolta n_recp_disp_sobu
    stot_inflows_inv_act c_pay_acq_const_fiolta c_paid_invest n_disp_subs_oth_biz
    oth_pay_ral_inv_act n_incr_pledge_loan stot_out_inv_act n_cashflow_inv_act
    c_recp_borrow proc_issue_bonds oth_cash_recp_ral_fnc_act stot_cash_in_fnc_act
    free_cashflow c_prepay_amt_borr c_pay_dist_dpcp_int_exp incl_dvd_profit_paid_sc_ms
    oth_cashpay_ral_fnc_act stot_cashout_fnc_act n_cash_flows_fnc_act
    eff_fx_flu_cash n_incr_cash_cash_equ c_cash_equ_beg_period c_cash_equ_end_period
    c_recp_cap_contrib incl_cash_rec_saims uncon_invest_loss prov_depr_assets
    depr_fa_coga_dpba amort_intang_assets lt_amort_deferred_exp decr_deferred_exp
    incr_acc_exp loss_disp_fiolta loss_scr_fa loss_fv_chg invest_loss
    decr_def_inc_tax_assets incr_def_inc_tax_liab decr_inventories decr_oper_payable
    incr_oper_payable others im_net_cashflow_oper_act conv_debt_into_cap
    conv_copbonds_due_within_1y fa_fnc_leases im_n_incr_cash_equ
    net_dism_capital_add net_cash_rece_sec credit_impa_loss use_right_asset_dep
    oth_loss_asset end_bal_cash beg_bal_cash end_bal_cash_equ beg_bal_cash_equ
    """.split()
)
FINA_INDICATOR_FACTORS = tuple(
    """
    eps dt_eps total_revenue_ps revenue_ps capital_rese_ps surplus_rese_ps
    undist_profit_ps extra_item profit_dedt gross_margin current_ratio quick_ratio
    cash_ratio ar_turn ca_turn fa_turn assets_turn op_income ebit ebitda fcff fcfe
    current_exint noncurrent_exint interestdebt netdebt tangible_asset working_capital
    networking_capital invest_capital retained_earnings diluted2_eps bps ocfps
    retainedps cfps ebit_ps fcff_ps fcfe_ps netprofit_margin grossprofit_margin
    cogs_of_sales expense_of_sales profit_to_gr saleexp_to_gr adminexp_of_gr
    finaexp_of_gr impai_ttm gc_of_gr op_of_gr ebit_of_gr roe roe_waa roe_dt roa npta
    roic roe_yearly roa2_yearly debt_to_assets assets_to_eqt dp_assets_to_eqt
    ca_to_assets nca_to_assets tbassets_to_totalassets int_to_talcap
    eqt_to_talcapital currentdebt_to_debt longdeb_to_debt ocf_to_shortdebt
    debt_to_eqt eqt_to_debt eqt_to_interestdebt tangibleasset_to_debt
    tangasset_to_intdebt tangibleasset_to_netdebt ocf_to_debt turn_days roa_yearly
    roa_dp fixed_assets profit_to_op q_saleexp_to_gr q_gc_to_gr q_roe q_dt_roe
    q_npta q_ocf_to_sales basic_eps_yoy dt_eps_yoy cfps_yoy op_yoy ebt_yoy
    netprofit_yoy dt_netprofit_yoy ocf_yoy roe_yoy bps_yoy assets_yoy eqt_yoy tr_yoy
    or_yoy q_sales_yoy q_op_qoq equity_yoy
    """.split()
)
INCOME_FACTORS = tuple(
    f"{factor}_{suffix}"
    for factor in INCOME_RAW_FACTORS
    for suffix in FLOW_SUFFIXES
)
CASHFLOW_FACTORS = tuple(
    f"{factor}_{suffix}"
    for factor in CASHFLOW_RAW_FACTORS
    for suffix in FLOW_SUFFIXES
)


class FinancialData:
    """提供四个财报 Worker 共用的公告日和报告期转换。"""

    REPORT_TYPES: ClassVar[dict[str, int]] = {
        "0331": 1,
        "0630": 2,
        "0930": 3,
        "1231": 4,
    }

    @staticmethod
    def empty(factors: tuple[str, ...]) -> pd.DataFrame:
        """返回包含 time 和固定因子的空宽表。"""
        return pd.DataFrame(columns=["time", *factors])

    @staticmethod
    def lookback(start_date: pd.Timestamp, years: int) -> str:
        """把增量起点回退指定年数并对齐到当月首日。"""
        return pd.Timestamp(
            year=start_date.year - years,
            month=start_date.month,
            day=1,
        ).strftime("%Y%m%d")

    @staticmethod
    def first_announcement(
        data: pd.DataFrame,
        announcement_column: str,
    ) -> pd.DataFrame:
        """按公告时间保留新报告期首次出现，同日只保留最新报告期。"""
        result = data.copy()
        if len(result) == 0:
            return result
        periods = result["end_date"].to_numpy()
        keep = np.ones(len(result), dtype=bool)
        latest = periods[0]
        for index in range(1, len(periods)):
            if periods[index] > latest:
                latest = periods[index]
            else:
                keep[index] = False
        return (
            result[keep]
            .reset_index(drop=True)
            .groupby(announcement_column, as_index=False)
            .last()
        )

    @classmethod
    def prepare(
        cls,
        endpoint: str,
        data: pd.DataFrame | None,
        factors: tuple[str, ...],
        announcement_column: str,
    ) -> pd.DataFrame:
        """校验财报响应、识别标准报告期并应用首次公告筛选。"""
        columns = [announcement_column, "end_date", *factors, "end_type"]
        if data is None:
            return pd.DataFrame(columns=columns)
        if not isinstance(data, pd.DataFrame):
            raise TypeError(f"{endpoint} 返回值不是 DataFrame")
        if data.empty:
            return pd.DataFrame(columns=columns)
        required = {announcement_column, "end_date", *factors}
        if missing := required - set(data.columns):
            raise ValueError(f"{endpoint} 返回结果缺少列：{sorted(missing)}")
        result = data.iloc[::-1].sort_values(
            by=announcement_column,
            kind="mergesort",
        )
        result = result.loc[
            :, [announcement_column, "end_date", *factors]
        ].copy()
        result["end_type"] = (
            result["end_date"].astype("string").str.slice(4).map(cls.REPORT_TYPES)
        )
        result = result.dropna(subset=["end_type"])
        result["end_type"] = result["end_type"].astype(int)
        result[announcement_column] = pd.to_datetime(
            result[announcement_column]
        )
        result["end_date"] = pd.to_datetime(result["end_date"])
        return cls.first_announcement(result, announcement_column)

    @staticmethod
    def process_flow(
        data: pd.DataFrame,
        factors: tuple[str, ...],
    ) -> pd.DataFrame:
        """把累计利润或现金流展开为报告期列并计算滚动十二个月值。"""
        result = data.copy()
        result = result.sort_values(
            ["end_date", "f_ann_date"]
        ).reset_index(drop=True)
        if result.empty:
            return result
        years = result["end_date"].dt.year.to_numpy()
        report_types = result["end_type"].to_numpy()
        previous_years = years - 1
        masks = {value: report_types == value for value in (1, 2, 3, 4)}
        generated: dict[str, np.ndarray] = {}
        for factor in factors:
            values = pd.to_numeric(result[factor], errors="coerce").to_numpy(
                dtype=float
            )
            for report_type, mask in masks.items():
                column = np.full(len(result), np.nan)
                column[mask] = values[mask]
                generated[f"{factor}_{report_type}"] = column
            lookups = {
                report_type: (
                    pd.Series(values[mask], index=years[mask])
                    .groupby(level=0)
                    .first()
                    .to_dict()
                    if mask.any()
                    else {}
                )
                for report_type, mask in masks.items()
            }
            previous = {
                report_type: np.fromiter(
                    (
                        lookups[report_type].get(year, np.nan)
                        for year in previous_years
                    ),
                    dtype=float,
                    count=len(result),
                )
                for report_type in (1, 2, 3, 4)
            }
            generated[f"{factor}_ttm"] = np.select(
                [masks[4], masks[3], masks[2], masks[1]],
                [
                    values,
                    values + previous[4] - previous[3],
                    values + previous[4] - previous[2],
                    values + previous[4] - previous[1],
                ],
                default=np.nan,
            )
        return pd.concat(
            [result, pd.DataFrame(generated, index=result.index)],
            axis=1,
        )


class StockBalanceSheetWorker(StockWorker):
    """通过 balancesheet 接口更新资产负债表。"""

    factors = BALANCE_SHEET_FACTORS

    @property
    def last_date_factors(self) -> tuple[str, ...]:
        """排除由 daily_basic 同时写入的 total_share。"""
        return tuple(factor for factor in self.factors if factor != "total_share")

    def fetch_one(
        self,
        code: str,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """获取一只股票的资产负债表。"""
        response = pro.balancesheet(
            ts_code=code,
            start_date=FinancialData.lookback(start_date, 1),
            end_date=end_date.strftime("%Y%m%d"),
        )
        result = FinancialData.prepare(
            "balancesheet",
            response,
            self.factors,
            "f_ann_date",
        )
        if result.empty:
            data = FinancialData.empty(self.factors)
        else:
            data = result.rename(columns={"f_ann_date": "time"}).loc[
                :, ["time", *self.factors]
            ]
        return self.to_long(
            code,
            data,
            start_date=start_date,
            end_date=end_date,
        )


class StockIncomeWorker(StockWorker):
    """通过 income 接口更新利润表报告期值和 TTM 值。"""

    factors = INCOME_FACTORS

    def fetch_one(
        self,
        code: str,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """获取一只股票的利润表并计算报告期和 TTM 因子。"""
        response = pro.income(
            ts_code=code,
            start_date=FinancialData.lookback(start_date, 2),
            end_date=end_date.strftime("%Y%m%d"),
        )
        result = FinancialData.prepare(
            "income",
            response,
            INCOME_RAW_FACTORS,
            "f_ann_date",
        )
        if result.empty:
            data = FinancialData.empty(self.factors)
        else:
            result = FinancialData.process_flow(result, INCOME_RAW_FACTORS)
            data = result.rename(columns={"f_ann_date": "time"}).loc[
                :, ["time", *self.factors]
            ]
        return self.to_long(
            code,
            data,
            start_date=start_date,
            end_date=end_date,
        )


class StockCashflowWorker(StockWorker):
    """通过 cashflow 接口更新现金流报告期值和 TTM 值。"""

    factors = CASHFLOW_FACTORS

    def fetch_one(
        self,
        code: str,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """获取一只股票的现金流量表并计算报告期和 TTM 因子。"""
        response = pro.cashflow(
            ts_code=code,
            start_date=FinancialData.lookback(start_date, 2),
            end_date=end_date.strftime("%Y%m%d"),
        )
        result = FinancialData.prepare(
            "cashflow",
            response,
            CASHFLOW_RAW_FACTORS,
            "f_ann_date",
        )
        if result.empty:
            data = FinancialData.empty(self.factors)
        else:
            result = FinancialData.process_flow(result, CASHFLOW_RAW_FACTORS)
            data = result.rename(columns={"f_ann_date": "time"}).loc[
                :, ["time", *self.factors]
            ]
        return self.to_long(
            code,
            data,
            start_date=start_date,
            end_date=end_date,
        )


class StockFinaIndicatorWorker(StockWorker):
    """通过 fina_indicator 接口更新财务指标。"""

    factors = FINA_INDICATOR_FACTORS

    def fetch_one(
        self,
        code: str,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """获取一只股票的财务指标。"""
        response = pro.fina_indicator(
            ts_code=code,
            start_date=FinancialData.lookback(start_date, 1),
            end_date=end_date.strftime("%Y%m%d"),
        )
        result = FinancialData.prepare(
            "fina_indicator",
            response,
            self.factors,
            "ann_date",
        )
        if result.empty:
            data = FinancialData.empty(self.factors)
        else:
            data = result.rename(columns={"ann_date": "time"}).loc[
                :, ["time", *self.factors]
            ]
        return self.to_long(
            code,
            data,
            start_date=start_date,
            end_date=end_date,
        )


stock_balance_sheet_worker = StockBalanceSheetWorker(threads=8, throttle=8)
stock_income_worker = StockIncomeWorker(threads=8, throttle=8)
stock_cashflow_worker = StockCashflowWorker(threads=8, throttle=8)
stock_fina_indicator_worker = StockFinaIndicatorWorker(threads=8, throttle=8)
