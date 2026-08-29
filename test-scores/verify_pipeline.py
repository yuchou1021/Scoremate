"""端到端验证：用测试谱模拟插件请求，验证云端分析链（基准集回归脚本）。

模拟插件的完整行为：
  1. 解析 MusicXML → 提取音符（pitch 列表）+ 和弦跨度（同拍音符分组）
  2. POST /api/analyze（measures=1，与插件一致）→ 特征
  3. 组 summary（特征 + 插件实测 max_chord_span）→ POST /api/arrange
  4. 断言每份谱的预期结果

运行（venv）：.venv\\Scripts\\python test-scores\\verify_pipeline.py
"""

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

SCORES_DIR = Path(__file__).resolve().parent

STEP_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi_of(step: str, alter: int, octave: int) -> int:
    return (octave + 1) * 12 + STEP_SEMITONES[step] + alter


def parse_score(path: Path) -> tuple[list[int], int, int, int, float]:
    """返回 (pitch 列表, 小节数, 最大和弦跨度, 装饰音数, 节奏复杂度)。

    装饰音 = 带 <grace/> 标记的音符；节奏复杂度 = 32分/64分音符占比
    （与插件端 computeRhythmComplexity 口径一致）。
    """
    root = ET.parse(path).getroot()
    notes: list[int] = []
    max_span = 0
    ornament_count = 0
    short_notes = 0
    measures = root.findall(".//measure")
    for measure in measures:
        tick = 0
        chord_members: dict[int, list[int]] = {}
        for note in measure.findall("note"):
            if note.find("rest") is not None:
                continue
            if note.find("grace") is not None:
                ornament_count += 1
                continue  # 装饰音不占时值，不进音高列表
            is_chord = note.find("chord") is not None
            pitch = note.find("pitch")
            step = pitch.findtext("step")
            alter = int(pitch.findtext("alter") or 0)
            octave = int(pitch.findtext("octave"))
            dur = int(note.findtext("duration") or 1)
            ntype = note.findtext("type") or ""
            if "32" in ntype or "64" in ntype:
                short_notes += 1
            midi = midi_of(step, alter, octave)
            chord_members.setdefault(tick, []).append(midi)
            notes.append(midi)
            if not is_chord:
                # 只有和弦的第一个音推进节拍位置（MusicXML 约定）
                tick += dur
        for members in chord_members.values():
            if len(members) > 1:
                max_span = max(max_span, max(members) - min(members))
    rhythm = min(1.0, short_notes / len(notes)) if notes else 0.0
    return notes, len(measures), max_span, ornament_count, rhythm


CASES = [
    # (文件, 预期: key, 应包含的指令规则, 应无的指令规则, 说明)
    ("01_wide_range.musicxml", "C major", {"compress_range"}, set(), "宽音域 → 压缩音域"),
    ("02_octave_chords.musicxml", "C major", {"split_chords"}, {"compress_range"}, "重复八度和弦 → 拆和弦"),
    ("03_dense_passage.musicxml", "C major", {"reduce_density"}, set(), "密集跑动 → 降密度"),
    ("04_simple_melody.musicxml", "C major", set(), {"reduce_density", "compress_range"}, "简单旋律 → 无指令"),
    ("05_key_g_major.musicxml", "G major", set(), set(), "G 大调 → 调性检测"),
    ("06_wide_stretch_chords.musicxml", "C major", {"split_chords"}, set(), "大跨度和弦 → 拆和弦"),
    ("07_ornaments.musicxml", "C major", {"drop_ornaments"}, set(), "装饰音 → 删装饰音"),
    ("08_complex_rhythm.musicxml", "C major", {"simplify_rhythm"}, set(), "32分音符 → 简化节奏"),
]


def main() -> int:
    client = TestClient(app)
    failed = []

    for name, exp_key, exp_has, exp_not, desc in CASES:
        notes, measures, span, ornaments, rhythm = parse_score(SCORES_DIR / name)

        # 1) analyze（与插件一致：measures=1 + 插件端实测特征）
        r = client.post("/api/analyze", json={
            "notes": notes,
            "measures": 1,
            "ornament_count": ornaments,
            "rhythm_complexity": rhythm,
        })
        ana = r.json()
        key = ana["key_estimate"]

        # 2) arrange（组 summary 同插件）
        features = dict(ana["features"])
        features["max_chord_span"] = max(features.get("max_chord_span", 0), span)
        summary = {
            "title": name,
            "key_estimate": key,
            "measures": 0,
            "voices": 1,
            "range": {"low_midi": min(notes), "high_midi": max(notes)},
            "difficulty_features": features,
            "selected": {"start_measure": 1, "end_measure": 0},
            "excerpt": "",
        }
        r2 = client.post("/api/arrange", json={
            "summary": summary, "instruction": "简化", "level": "simple",
        })
        arr = r2.json()
        rules = {rule for ins in arr["instructions"] for rule in ins["params"].get("rules", [])}

        ok = key == exp_key and exp_has <= rules and not (rules & exp_not)
        if not ok:
            failed.append(name)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}  {desc}")
        print(f"       key={key} (期望 {exp_key})  特征=(装饰音 {ornaments}, 节奏 {rhythm:.2f})  指令规则={rules or '无'}")

    # 3) 端到端规则覆盖检查：5 条简化规则必须全部可被真实数据流触发
    all_rules = set()
    for name, _, _, _, _ in CASES:
        notes, measures, span, ornaments, rhythm = parse_score(SCORES_DIR / name)
        r = client.post("/api/analyze", json={
            "notes": notes, "measures": 1,
            "ornament_count": ornaments, "rhythm_complexity": rhythm,
        })
        features = dict(r.json()["features"])
        features["max_chord_span"] = max(features.get("max_chord_span", 0), span)
        summary = {
            "title": name, "key_estimate": r.json()["key_estimate"], "measures": 0,
            "voices": 1, "range": {}, "difficulty_features": features,
            "selected": {"start_measure": 1, "end_measure": 0}, "excerpt": "",
        }
        r2 = client.post("/api/arrange", json={
            "summary": summary, "instruction": "简化", "level": "simple",
        })
        for ins in r2.json()["instructions"]:
            all_rules.update(ins["params"].get("rules", []))
    expected_rules = {"drop_ornaments", "split_chords", "reduce_density", "compress_range", "simplify_rhythm"}
    if all_rules != expected_rules:
        failed.append(f"rules coverage: got {all_rules}, want {expected_rules}")
        print(f"[FAIL] 端到端规则覆盖：{all_rules}（期望全部 5 条）")
    else:
        print(f"[PASS] 端到端规则覆盖：{sorted(all_rules)} —— 5 条规则全部可触发")

    print("-" * 50)
    if failed:
        print(f"FAILED: {failed}")
        return 1
    print("ALL PASS —— 云端分析链对 8 份测试谱全部符合预期，5 条简化规则端到端可触发")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
