"""确定性分析层（PRD §6.2 / §8）：调性检测、音域、难度评分。

v0.1 为纯 Python 实现，不依赖 music21：
- 调性检测：Krumhansl-Schmuckler 轮廓相关法
- 音域：min/max MIDI 与跨度
- 难度：PRD §8 加权公式
"""

from .schemas import AnalyzeResponse, DifficultyFeatures

# Krumhansl & Krumhansl (1982) 大/小调调性轮廓（12 个音级）
MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

# 常用记名（黑键取更常见的降号/升号形式）
PITCH_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def _pearson(a: list[float], b: list[float]) -> float:
    """皮尔逊相关系数。"""
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va == 0 or vb == 0:
        return 0.0
    return cov / (va**0.5 * vb**0.5)


def detect_key(notes: list[int]) -> tuple[str | None, float]:
    """Krumhansl-Schmuckler 调性检测。

    返回 (调名, 置信度 0-1)。音符太少或为空时返回 (None, 0.0)。
    """
    if not notes:
        return None, 0.0
    hist = [0.0] * 12
    for n in notes:
        hist[n % 12] += 1.0
    total = sum(hist)
    if total == 0:
        return None, 0.0
    hist = [h / total for h in hist]

    best_name, best_score = None, float("-inf")
    for tonic in range(12):
        for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            shifted = [profile[(i - tonic) % 12] for i in range(12)]
            score = _pearson(hist, shifted)
            if score > best_score:
                best_score = score
                best_name = f"{PITCH_NAMES[tonic]} {mode}"
    return best_name, max(0.0, min(1.0, (best_score + 1) / 2))


def compute_range(notes: list[int]) -> dict:
    """音域：low/high MIDI 与跨度（半音）。"""
    if not notes:
        return {"low_midi": None, "high_midi": None, "span": 0}
    low, high = min(notes), max(notes)
    return {"low_midi": low, "high_midi": high, "span": high - low}


def difficulty_score(
    notes: list[int],
    measures: int,
    features: DifficultyFeatures | None = None,
    ornament_count: int = 0,
    rhythm_complexity: float = 0.0,
) -> tuple[float, DifficultyFeatures]:
    """难度评分 0-1（PRD §8 加权公式）。

    无特征数据时从 notes 推导：密度按每小节 64 音为满密度归一。
    装饰音/节奏复杂度无法从扁平音高列表推导，由调用方传入（插件端实测值）。
    """
    if features is None:
        span = compute_range(notes)["span"]
        density = len(notes) / max(measures, 1) / 64.0
        features = DifficultyFeatures(
            note_density=min(1.0, density),
            range_span=span,
            ornament_count=max(0, int(ornament_count)),
            rhythm_complexity=max(0.0, min(1.0, float(rhythm_complexity))),
        )

    weights = {
        "note_density": 0.30,
        "range_span": 0.20,
        "max_chord_span": 0.20,
        "ornament_count": 0.15,
        "rhythm_complexity": 0.15,
    }

    def _norm(key: str) -> float:
        v = getattr(features, key)
        caps = {
            "note_density": 1.0,
            "range_span": 96,  # 8 个八度为满
            "max_chord_span": 24,
            "ornament_count": 32,
            "rhythm_complexity": 1.0,
        }
        return min(1.0, max(0.0, v) / caps[key])

    score = sum(weights[k] * _norm(k) for k in weights)
    return round(score, 3), features


def analyze(
    notes: list[int],
    measures: int = 1,
    ornament_count: int = 0,
    rhythm_complexity: float = 0.0,
) -> AnalyzeResponse:
    """综合分析入口：调性 + 音域 + 难度。

    ornament_count / rhythm_complexity 由插件端从乐谱实测传入
    （扁平音高列表推导不出），缺省为 0。
    """
    key, conf = detect_key(notes)
    rng = compute_range(notes)
    diff, features = difficulty_score(
        notes, measures,
        ornament_count=ornament_count,
        rhythm_complexity=rhythm_complexity,
    )
    return AnalyzeResponse(
        key_estimate=key,
        key_confidence=conf,
        range=rng,
        difficulty=diff,
        features=features,
    )
