"""核心逻辑冒烟测试（v0.1）。

直接运行：python tests/smoke_core.py
（不依赖 fastapi；pydantic 需要已安装）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.music_analysis import analyze
from app.rules import simplify_plan, transpose_plan
from app.schemas import ScoreSummary

FAILED = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not cond:
        FAILED.append(name)


def main() -> int:
    # 1) 调性检测：C 大调音阶 → C major
    r = analyze([60, 62, 64, 65, 67, 69, 71, 72], 2)
    check("analyze.key=C major", r.key_estimate == "C major", f"got={r.key_estimate} conf={r.key_confidence:.2f}")
    check("analyze.range", r.range == {"low_midi": 60, "high_midi": 72, "span": 12}, f"got={r.range}")
    check("analyze.difficulty.low", r.difficulty < 0.1, f"got={r.difficulty}")

    # 2) 转调：C major -> G major → +7 半音
    s = ScoreSummary(title="t", key_estimate="C major", measures=16)
    ins, ws = transpose_plan(s, target_key="G major")
    check("transpose.C->G.semitones=7",
          len(ins) == 1 and ins[0].params.get("semitones") == 7,
          f"got={[(i.id, i.params.get('semitones')) for i in ins]} warn={ws}")

    # 3) 转调：同调 → 无操作
    ins, ws = transpose_plan(s, target_key="C major")
    check("transpose.same_key.noop", len(ins) == 0 and ws, f"ins={len(ins)} warn={ws}")

    # 4) 简化：高难度特征 → 触发全部 5 条规则
    s2 = ScoreSummary(
        title="t", key_estimate="C major", measures=16,
        difficulty_features={
            "note_density": 0.75, "max_chord_span": 14, "ornament_count": 6,
            "range_span": 60, "rhythm_complexity": 0.6,
        },
    )
    ins2, ws2 = simplify_plan(s2)
    rules_hit = {i.params["rules"][0] for i in ins2}
    expected = {"drop_ornaments", "split_chords", "reduce_density", "compress_range", "simplify_rhythm"}
    check("simplify.all_rules", rules_hit == expected, f"got={rules_hit} warn={ws2}")

    # 5) 简化：简单特征 → 无操作提示
    s3 = ScoreSummary(title="t", measures=8, difficulty_features={"note_density": 0.2})
    ins3, ws3 = simplify_plan(s3)
    check("simplify.easy.noop", len(ins3) == 0 and ws3, f"ins={len(ins3)} warn={ws3}")

    print("-" * 40)
    if FAILED:
        print(f"FAILED: {FAILED}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
