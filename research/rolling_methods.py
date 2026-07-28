"""全部滚动 ETF 选池方法的注册表。"""

from dataclasses import dataclass
from pathlib import Path

from research.rolling_ant_colony.strategy import (
    select_pool as ant_colony,
)
from research.rolling_beam_search.strategy import (
    select_pool as beam_search,
)
from research.rolling_common import Selector
from research.rolling_cross_entropy.strategy import (
    select_pool as cross_entropy,
)
from research.rolling_differential_evolution.strategy import (
    select_pool as differential_evolution,
)
from research.rolling_elite_frequency.strategy import (
    select_pool as elite_frequency,
)
from research.rolling_evolution_strategy.strategy import (
    select_pool as evolution_strategy,
)
from research.rolling_genetic.strategy import select_pool as genetic
from research.rolling_hill_climb.strategy import (
    select_pool as hill_climb,
)
from research.rolling_mean_inclusion.strategy import (
    select_pool as mean_inclusion,
)
from research.rolling_multi_start_hill.strategy import (
    select_pool as multi_start_hill,
)
from research.rolling_particle_swarm.strategy import (
    select_pool as particle_swarm,
)
from research.rolling_random_best.strategy import (
    select_pool as random_best,
)
from research.rolling_ridge_surrogate.strategy import (
    select_pool as ridge_surrogate,
)
from research.rolling_sequential_backward.strategy import (
    select_pool as sequential_backward,
)
from research.rolling_sequential_forward.strategy import (
    select_pool as sequential_forward,
)
from research.rolling_shapley.strategy import select_pool as shapley
from research.rolling_simulated_annealing.strategy import (
    select_pool as simulated_annealing,
)
from research.rolling_tabu_search.strategy import (
    select_pool as tabu_search,
)
from research.rolling_thompson_sampling.strategy import (
    select_pool as thompson_sampling,
)
from research.rolling_ucb_sampling.strategy import (
    select_pool as ucb_sampling,
)


@dataclass(frozen=True)
class Method:
    """一种可运行的选池方法。"""

    selector: Selector
    description: str

    @property
    def output_directory(self) -> Path:
        """返回该方法自己的默认输出目录。"""
        module_name = self.selector.__module__.split(".")[-2]
        return Path(__file__).parent / module_name / "output"


METHODS = {
    "rolling_random_best": Method(
        random_best,
        "随机组合中选择训练期 Sharpe 最高者",
    ),
    "rolling_shapley": Method(
        shapley,
        "按入选与未入选组合 Sharpe 均值差估计相对贡献",
    ),
    "rolling_mean_inclusion": Method(
        mean_inclusion,
        "按代码所在组合的平均 Sharpe 排名",
    ),
    "rolling_elite_frequency": Method(
        elite_frequency,
        "按高分组合中的超额出现频率排名",
    ),
    "rolling_ridge_surrogate": Method(
        ridge_surrogate,
        "用岭回归代理模型估计代码边际影响",
    ),
    "rolling_ucb_sampling": Method(
        ucb_sampling,
        "用 UCB 平衡代码探索与利用",
    ),
    "rolling_thompson_sampling": Method(
        thompson_sampling,
        "按代码表现后验进行 Thompson 抽样",
    ),
    "rolling_cross_entropy": Method(
        cross_entropy,
        "用精英样本逐批更新代码抽样概率",
    ),
    "rolling_hill_climb": Method(
        hill_climb,
        "单起点、只接受改进的单代码替换",
    ),
    "rolling_multi_start_hill": Method(
        multi_start_hill,
        "多起点局部爬山搜索",
    ),
    "rolling_tabu_search": Method(
        tabu_search,
        "使用短期禁忌表的邻域搜索",
    ),
    "rolling_simulated_annealing": Method(
        simulated_annealing,
        "按降温概率接受短期退步",
    ),
    "rolling_beam_search": Method(
        beam_search,
        "同时保留多个高分搜索分支",
    ),
    "rolling_sequential_forward": Method(
        sequential_forward,
        "逐步锁定高贡献代码",
    ),
    "rolling_sequential_backward": Method(
        sequential_backward,
        "逐步淘汰低贡献代码",
    ),
    "rolling_genetic": Method(
        genetic,
        "锦标赛选择、集合交叉和变异",
    ),
    "rolling_evolution_strategy": Method(
        evolution_strategy,
        "父代加子代精英保留的进化策略",
    ),
    "rolling_differential_evolution": Method(
        differential_evolution,
        "定长二进制差分进化",
    ),
    "rolling_particle_swarm": Method(
        particle_swarm,
        "定长二进制粒子群搜索",
    ),
    "rolling_ant_colony": Method(
        ant_colony,
        "按高分组合强化代码信息素",
    ),
}

if len(METHODS) < 20:
    raise RuntimeError("滚动选池方法不能少于 20 种")


__all__ = ["METHODS", "Method"]
