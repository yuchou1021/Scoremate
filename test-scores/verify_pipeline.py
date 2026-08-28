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


def parse_score(path: Path) -> tuple[list[int], int, int]:
    """返回 (pitch 列表, 小节数, 最大和弦跨度)。"""
    root = ET.parse(path).getroot()
    notes: list[int] = []
    max_span = 0
    measures = root.findall(".//measure")
    for measure in measures:
        tick = 0
        chord_members: dict[int, list[int]] = {}
        for note in measure.findall("note"):
            if note.find("rest") is not None:
                continue
            is_chord = note.find("chord") is not None
            pitch = note.find("pitch")
            step = pitch.findtext("step")
            alter = int(pitch.findtext("alter") or 0)
            octave = int(pitch.findtext("octave"))
            dur = int(note.findtext("duration") or 1)
            midi = midi_of(step, alter, octave)
            chord_members.setdefault(tick, []).append(midi)
            notes.append(midi)
            if not is_chord:
                # 只有和弦的第一个音推进节拍位置（MusicXML 约定）
                tick += dur
        for members in chord_members.values():
            if len(members) > 1:
                max_span = max(max_span, max(members) - min(members))
    return notes, len(measures), max_span


CASES = [
    # (文件, 预期: key, 应包含的指令规则, 应无的指令规则, 说明)
    ("01_wide_range.musicxml", "C major", {"compress_range"}, set(), "宽音域 → 压缩音域"),
    ("02_octave_chords.musicxml", "C major", {"split_chords"}, {"compress_range"}, "重复八度和弦 → 拆和弦"),
    ("03_dense_passage.musicxml", "C major", {"reduce_density"}, set(), "密集跑动 → 降密度"),
    ("04_simple_melody.musicxml", "C major", set(), {"reduce_density", "compress_range"}, "简单旋律 → 无指令"),
    ("05_key_g_major.musicxml", "G major", set(), set(), "G 大调 → 调性检测"),
    ("06_wide_stretch_chords.musicxml", "C major", {"split_chords"}, set(), "大跨度和弦 → 拆和弦"),
]


def main() -> int:
    client = TestClient(app)
    failed = []

    for name, exp_key, exp_has, exp_not, desc in CASES:
        notes, measures, span = parse_score(SCORES_DIR / name)

        # 1) analyze（与插件一致：measures=1）
        r = client.post("/api/analyze", json={"notes": notes, "measures": 1})
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
        print(f"       key={key} (期望 {exp_key})  指令规则={rules or '无'}")

    print("-" * 50)
    if failed:
        print(f"FAILED: {failed}")
        return 1
    print("ALL PASS —— 云端分析链对 6 份测试谱全部符合预期")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
