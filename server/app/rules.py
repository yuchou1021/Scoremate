"""规则引擎（PRD §8）：转调与简化规则。

确定性、可组合、可校验。v0.1 规则为主；LLM 负责"哪里改/改多少"的决策在
v0.2 接入（见 llm.py），本模块保持纯函数、无外部依赖。
"""

from .schemas import EditInstruction, ScoreSummary

# 调名 → 相对 C 的半音数
KEY_SEMITONES = {
    "C major": 0, "Db major": 1, "D major": 2, "Eb major": 3, "E major": 4,
    "F major": 5, "F# major": 6, "G major": 7, "Ab major": 8, "A major": 9,
    "Bb major": 10, "B major": 11,
    "A minor": 0, "Bb minor": 1, "B minor": 2, "C minor": 3, "C# minor": 4,
    "D minor": 5, "D# minor": 6, "E minor": 7, "F minor": 8, "F# minor": 9,
    "G minor": 10, "G# minor": 11,
}


def _scope(summary: ScoreSummary) -> dict:
    return {
        "start_measure": summary.selected.get("start_measure", 1),
        "end_measure": summary.selected.get("end_measure", 0) or summary.measures,
        "voices": list(range(max(summary.voices, 1))),
    }


def transpose_plan(
    summary: ScoreSummary,
    target_key: str | None = None,
    semitones: int | None = None,
    target_low: int | None = None,
    target_high: int | None = None,
) -> tuple[list[EditInstruction], list[str]]:
    """转调：目标调 或 半音数 二选一；可选目标音域约束（v0.1 仅记录约束，应用在插件端）。"""
    warnings: list[str] = []

    if semitones is None:
        src = KEY_SEMITONES.get((summary.key_estimate or "").strip())
        dst = KEY_SEMITONES.get((target_key or "").strip()) if target_key else None
        if src is None or dst is None:
            return [], ["无法确定起始/目标调：请先对选区做 /api/analyze，或在插件设置里手动指定调性"]
        semitones = (dst - src) % 12

    semitones = int(semitones) % 12
    if semitones == 0:
        return [], ["目标调与当前调相同（半音数为 0），无操作"]

    scope = _scope(summary)
    desc = f"将选区移调 {semitones} 个半音"
    why = f"原调 {summary.key_estimate or '未知'}"
    if target_key:
        desc += f"，目标调 {target_key}"
        why += f" → {target_key}"
    why += "，适配人声/乐器音域"
    if target_low is not None or target_high is not None:
        desc += f"，并约束音域 [{target_low or '不限'}, {target_high or '不限'}]"

    return [
        EditInstruction(
            id="t1",
            type="transpose",
            scope=scope,
            params={
                "semitones": semitones,
                "target_key": target_key,
                "target_low": target_low,
                "target_high": target_high,
            },
            description=desc,
            rationale=why,
        )
    ], warnings


def simplify_plan(summary: ScoreSummary, level: str = "simple") -> tuple[list[EditInstruction], list[str]]:
    """难度简化：按 PRD §8 规则表触发（v0.1 规则为主，LLM 决策见 v0.2）。"""
    f = summary.difficulty_features
    scope = _scope(summary)
    instructions: list[EditInstruction] = []
    warnings: list[str] = []

    def add(rtype: str, params: dict, desc: str, why: str) -> None:
        instructions.append(
            EditInstruction(
                id=f"s{len(instructions) + 1}",
                type="simplify",
                scope=scope,
                params={"rules": [rtype], "level": level, **params},
                description=desc,
                rationale=why,
            )
        )

    if f.ornament_count > 0:
        add("drop_ornaments", {}, "删除装饰音（倚音/波音/颤音）",
            f"检测到 {f.ornament_count} 个装饰音，超出目标水平的读谱负荷")
    if f.max_chord_span > 10:
        add("split_chords", {}, "拆分跨度超过 10 度的和弦",
            f"最大和弦跨度 {f.max_chord_span} 半音，目标水平够不着")
    if f.note_density > 0.6:
        add("reduce_density", {}, "降低织体密度（重复八度去重、重复音型减半）",
            f"音符密度 {f.note_density:.2f} 偏高，简化后更易读谱")
    if f.range_span > 48:
        add("compress_range", {}, "压缩音域至 C2–C6（钢琴默认范围）",
            f"音域跨度 {f.range_span} 半音，超过 4 个八度")
    if f.rhythm_complexity > 0.5:
        add("simplify_rhythm", {}, "简化节奏（32分→16分、三连音→八分）",
            f"节奏复杂度 {f.rhythm_complexity:.2f}，需放慢音符时值")

    if not instructions:
        return [], ["该选区特征已处于目标难度，无需简化；或缺少特征数据（需插件端提取后补齐）"]
    return instructions, warnings


def validate(instructions: list[EditInstruction], measures: int) -> list[str]:
    """校验层（PRD §8）：范围、半音数等基础检查。

    音乐性校验（声部交叉、平行五八度等）在 v0.2 随重配/加花功能扩展。
    """
    warnings: list[str] = []
    for it in instructions:
        s = it.scope.get("start_measure", 1)
        e = it.scope.get("end_measure", 0)
        if e and e < s:
            warnings.append(f"{it.id}: 范围错误（end_measure < start_measure）")
        if measures and e > measures:
            warnings.append(f"{it.id}: 范围超出总小节数（{measures}）")
        if it.type == "transpose":
            st = it.params.get("semitones")
            if st is not None and not (0 < st < 12):
                warnings.append(f"{it.id}: 半音数异常（{st}，应为 1-11）")
    return warnings
