"""实现有限参数空间上的调优算法。"""

from collections.abc import Callable

import numpy as np

from .schema import OptimizationAlgorithm, OptimizationSelection


def normalize_parameter_candidates(
        candidates: list[dict[str, int | float]],
        names: tuple[str, ...],
) -> np.ndarray:
    """按每个参数的数值顺序把有限候选组合编码至 [0, 1]。"""
    points = np.zeros((len(candidates), len(names)), dtype=float)
    for column, name in enumerate(names):
        values = sorted({float(candidate[name]) for candidate in candidates})
        positions = {
            value: index / max(1, len(values) - 1)
            for index, value in enumerate(values)
        }
        points[:, column] = [
            positions[float(candidate[name])]
            for candidate in candidates
        ]
    return points


def select_parameter(
        algorithm: OptimizationAlgorithm,
        points: np.ndarray,
        evaluate: Callable[[int], float],
        *,
        seed: int,
        budget: int,
) -> OptimizationSelection:
    """从随机初始组合开始，在评价预算内选择训练 Sharpe 最高的组合。"""
    rng = np.random.default_rng(seed)
    initial = int(rng.integers(len(points)))
    visited = [initial]
    scores = {initial: evaluate(initial)}
    current = initial
    recent = [initial]
    velocity = np.zeros(points.shape[1], dtype=float)
    water_level = scores[initial] - 0.25

    while len(visited) < budget:
        step = len(visited)
        best = max(visited, key=scores.__getitem__)
        target = propose_parameter(
            algorithm,
            points,
            scores,
            visited,
            best,
            current,
            recent,
            velocity,
            step,
            budget,
            rng,
        )
        proposal = nearest_unvisited(points, target, visited)
        proposal_score = evaluate(proposal)
        scores[proposal] = proposal_score

        if algorithm == OptimizationAlgorithm.SIMULATED_ANNEALING:
            temperature = max(0.02, 0.35 * (1 - step / budget))
            delta = proposal_score - scores[current]
            if delta >= 0 or rng.random() < np.exp(max(-700.0, delta / temperature)):
                current = proposal
        elif algorithm == OptimizationAlgorithm.THRESHOLD_ACCEPTING:
            threshold = 0.25 * (1 - step / budget)
            if proposal_score >= scores[current] - threshold:
                current = proposal
        elif algorithm == OptimizationAlgorithm.GREAT_DELUGE:
            water_level += 0.5 / budget
            if proposal_score >= water_level:
                current = proposal
        else:
            current = proposal

        if algorithm == OptimizationAlgorithm.PARTICLE_SWARM:
            velocity = (
                0.45 * velocity
                + 1.35 * rng.random(points.shape[1]) * (points[best] - points[current])
            )
        visited.append(proposal)
        recent = (recent + [proposal])[-4:]

    selected = max(visited, key=scores.__getitem__)
    return OptimizationSelection(
        initial_index=initial,
        selected_index=selected,
        evaluated_indices=tuple(visited),
        selected_score=scores[selected],
    )


def propose_parameter(
        algorithm: OptimizationAlgorithm,
        points: np.ndarray,
        scores: dict[int, float],
        visited: list[int],
        best: int,
        current: int,
        recent: list[int],
        velocity: np.ndarray,
        step: int,
        budget: int,
        rng: np.random.Generator,
) -> np.ndarray:
    """根据算法和已观察得分提出下一个归一化候选位置。"""
    unvisited = np.asarray([
        index
        for index in range(len(points))
        if index not in visited
    ])
    if algorithm == OptimizationAlgorithm.RANDOM_SEARCH:
        return points[int(rng.choice(unvisited))]
    if algorithm == OptimizationAlgorithm.LATIN_HYPERCUBE:
        return (
            np.arange(points.shape[1]) * 0.61803398875
            + (step + rng.random()) / budget
        ) % 1.0
    if algorithm == OptimizationAlgorithm.HALTON:
        return np.asarray([
            van_der_corput(step + 1 + int(rng.integers(97)), prime)
            for prime in first_primes(points.shape[1])
        ])
    if algorithm == OptimizationAlgorithm.MAXIMIN:
        distance = np.min(point_distances(points[unvisited], points[visited]), axis=1)
        return points[unvisited[int(np.argmax(distance))]]
    if algorithm == OptimizationAlgorithm.HILL_CLIMB:
        scale = max(0.04, 0.30 * (1 - step / budget))
        return points[best] + rng.normal(0, scale, points.shape[1])
    if algorithm == OptimizationAlgorithm.COORDINATE_DESCENT:
        target = points[best].copy()
        column = step % points.shape[1]
        target[column] = points[int(rng.choice(unvisited)), column]
        return target
    if algorithm == OptimizationAlgorithm.PATTERN_SEARCH:
        target = points[best].copy()
        column = step % points.shape[1]
        direction = -1 if (step // points.shape[1]) % 2 else 1
        target[column] += direction * max(0.08, 0.35 * (1 - step / budget))
        return target
    if algorithm == OptimizationAlgorithm.TABU_SEARCH:
        candidates = np.asarray([index for index in unvisited if index not in recent])
        candidates = candidates if len(candidates) else unvisited
        distance = np.linalg.norm(points[candidates] - points[best], axis=1)
        return points[candidates[int(np.argmin(distance))]]
    if algorithm in {
        OptimizationAlgorithm.SIMULATED_ANNEALING,
        OptimizationAlgorithm.THRESHOLD_ACCEPTING,
        OptimizationAlgorithm.GREAT_DELUGE,
    }:
        scale = max(0.05, 0.40 * (1 - step / budget))
        return points[current] + rng.normal(0, scale, points.shape[1])
    if algorithm == OptimizationAlgorithm.DIFFERENTIAL_EVOLUTION:
        if len(points) < 3:
            return points[int(rng.choice(unvisited))]
        population = rng.choice(len(points), size=3, replace=False)
        return (
            points[population[0]]
            + 0.7 * (points[population[1]] - points[population[2]])
        )
    if algorithm == OptimizationAlgorithm.PARTICLE_SWARM:
        return (
            points[current]
            + velocity
            + 0.35 * rng.random(points.shape[1]) * (points[best] - points[current])
        )
    if algorithm == OptimizationAlgorithm.GENETIC_ALGORITHM:
        ranked = sorted(visited, key=scores.__getitem__)[-min(4, len(visited)):]
        first, second = rng.choice(ranked, size=2, replace=True)
        child = np.where(
            rng.random(points.shape[1]) < 0.5,
            points[first],
            points[second],
        )
        child[int(rng.integers(points.shape[1]))] = rng.random()
        return child
    if algorithm == OptimizationAlgorithm.EVOLUTION_STRATEGY:
        elite = sorted(visited, key=scores.__getitem__)[
            -max(1, len(visited) // 3):
        ]
        center = points[elite].mean(axis=0)
        scale = max(0.05, 0.30 * (1 - step / budget))
        return center + rng.normal(0, scale, points.shape[1])
    if algorithm == OptimizationAlgorithm.CROSS_ENTROPY:
        elite = sorted(visited, key=scores.__getitem__)[
            -max(1, len(visited) // 3):
        ]
        center = points[elite].mean(axis=0)
        spread = np.maximum(
            0.05,
            points[elite].std(axis=0) if len(elite) > 1 else 0.25,
        )
        return rng.normal(center, spread)
    if algorithm == OptimizationAlgorithm.TPE:
        if len(visited) < 4:
            return points[int(rng.choice(unvisited))]
        ranked = sorted(visited, key=scores.__getitem__)
        split = max(1, len(ranked) // 4)
        good = points[ranked[-split:]]
        bad = points[ranked[:-split]]
        good_distance = np.min(point_distances(points[unvisited], good), axis=1)
        bad_distance = np.min(point_distances(points[unvisited], bad), axis=1)
        return points[unvisited[int(np.argmax(bad_distance / (good_distance + 0.02)))]]
    if algorithm in {
        OptimizationAlgorithm.RBF_SURROGATE,
        OptimizationAlgorithm.KNN_UCB,
    }:
        distances = point_distances(points[unvisited], points[visited])
        weights = 1.0 / (distances + 0.03)
        observed = np.asarray([scores[index] for index in visited])
        prediction = (weights @ observed) / weights.sum(axis=1)
        uncertainty = np.min(distances, axis=1)
        coefficient = (
            0.35
            if algorithm == OptimizationAlgorithm.RBF_SURROGATE
            else 0.60
        )
        return points[unvisited[int(np.argmax(prediction + coefficient * uncertainty))]]
    if algorithm == OptimizationAlgorithm.ADAPTIVE_RANDOM:
        if rng.random() < max(0.15, 1 - step / budget):
            return points[int(rng.choice(unvisited))]
        return points[best] + rng.normal(0, 0.12, points.shape[1])
    raise ValueError(f"不支持的调优算法：{algorithm}")


def nearest_unvisited(
        points: np.ndarray,
        target: np.ndarray,
        visited: list[int],
) -> int:
    """把连续候选位置吸附到最近的未评价离散组合。"""
    target = np.clip(np.asarray(target, dtype=float), 0.0, 1.0)
    candidates = np.asarray([
        index
        for index in range(len(points))
        if index not in visited
    ])
    distances = np.linalg.norm(points[candidates] - target, axis=1)
    return int(candidates[int(np.argmin(distances))])


def point_distances(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """计算两组归一化参数点的欧氏距离矩阵。"""
    return np.linalg.norm(left[:, None, :] - right[None, :, :], axis=2)


def first_primes(count: int) -> list[int]:
    """返回 Halton 序列各维所需的前 count 个质数。"""
    primes: list[int] = []
    candidate = 2
    while len(primes) < count:
        if all(candidate % prime for prime in primes if prime * prime <= candidate):
            primes.append(candidate)
        candidate += 1
    return primes


def van_der_corput(index: int, base: int) -> float:
    """生成一维 Van der Corput 低差异序列值。"""
    value = 0.0
    denominator = 1.0
    while index:
        index, remainder = divmod(index, base)
        denominator *= base
        value += remainder / denominator
    return value


__all__ = ["normalize_parameter_candidates", "select_parameter"]
