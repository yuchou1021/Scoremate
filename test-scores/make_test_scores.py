#!/usr/bin/env python3
"""生成谱伴 ScoreMate 的测试用 MusicXML 谱子。

用法：python make_test_scores.py   （输出到本目录 *.musicxml）
这些谱子同时也是 PRD §12 基准集的第一批成员。
"""

from pathlib import Path
from xml.etree import ElementTree as ET

OUT = Path(__file__).resolve().parent


def make_note(spec, divisions=4):
    """spec: dict(step, octave, dur, type, alter=0, chord=False, rest=False)"""
    n = ET.Element("note")
    if spec.get("chord"):
        ET.SubElement(n, "chord")
    if spec.get("rest"):
        ET.SubElement(n, "rest")
    else:
        p = ET.SubElement(n, "pitch")
        ET.SubElement(p, "step").text = spec["step"]
        if spec.get("alter"):
            ET.SubElement(p, "alter").text = str(spec["alter"])
        ET.SubElement(p, "octave").text = str(spec["octave"])
    ET.SubElement(n, "duration").text = str(spec["dur"])
    ET.SubElement(n, "voice").text = "1"
    ET.SubElement(n, "type").text = spec["type"]
    return n


def build(measures, fifths=0, title="Test"):
    """measures: list of list of note-spec dicts；4/4 拍，单声部。"""
    root = ET.Element("score-partwise", {"version": "4.0"})
    pl = ET.SubElement(root, "part-list")
    sp = ET.SubElement(pl, "score-part", {"id": "P1"})
    ET.SubElement(sp, "part-name").text = title
    part = ET.SubElement(root, "part", {"id": "P1"})

    for i, m in enumerate(measures, 1):
        me = ET.SubElement(part, "measure", {"number": str(i)})
        attrs = ET.SubElement(me, "attributes")
        ET.SubElement(attrs, "divisions").text = "4"
        key = ET.SubElement(attrs, "key")
        ET.SubElement(key, "fifths").text = str(fifths)
        ET.SubElement(key, "mode").text = "major"
        time = ET.SubElement(attrs, "time")
        ET.SubElement(time, "beats").text = "4"
        ET.SubElement(time, "beat-type").text = "4"
        clef = ET.SubElement(attrs, "clef")
        ET.SubElement(clef, "sign").text = "G"
        ET.SubElement(clef, "line").text = "2"
        for spec in m:
            me.append(make_note(spec))
    return ET.tostring(root, encoding="unicode")


def q(step, octave, alter=0):      # 四分音符
    return {"step": step, "octave": octave, "alter": alter, "dur": 4, "type": "quarter"}


def s16(step, octave):             # 十六分音符
    return {"step": step, "octave": octave, "dur": 1, "type": "16th"}


def whole(step, octave, chord=False):   # 全音符
    return {"step": step, "octave": octave, "dur": 16, "type": "whole", "chord": chord}


def half(step, octave, chord=False):    # 二分音符
    return {"step": step, "octave": octave, "dur": 8, "type": "half", "chord": chord}


def write(name, xml):
    p = OUT / name
    p.write_text(xml, encoding="utf-8")
    print("written:", p.name)


def main():
    # 1) 宽音域：C2 → C7（测试压缩音域 + 音域分析）
    write("01_wide_range.musicxml", build([
        [q("C", 2), q("G", 2), q("C", 3), q("G", 3)],
        [q("C", 4), q("G", 4), q("C", 5), q("G", 5)],
        [q("C", 6), q("G", 6), q("C", 7), q("G", 7)],
        [q("C", 7), q("G", 6), q("C", 6), q("G", 5)],
    ], title="Wide Range"))

    # 2) 重复八度和弦（测试去重复八度）
    write("02_octave_chords.musicxml", build([
        [whole("C", 3), whole("E", 3, chord=True), whole("G", 3, chord=True),
         whole("C", 4, chord=True), whole("E", 4, chord=True)],
        [whole("G", 2), whole("B", 2, chord=True), whole("D", 3, chord=True),
         whole("G", 3, chord=True)],
        [whole("F", 3), whole("A", 3, chord=True), whole("C", 4, chord=True),
         whole("F", 4, chord=True), whole("A", 4, chord=True)],
        [whole("E", 3), whole("G", 3, chord=True), whole("B", 3, chord=True),
         whole("E", 4, chord=True)],
    ], title="Octave Chords"))

    # 3) 密集十六分音符跑动（测试密度分析 → 降低织体密度）
    run = [s16("C", 4), s16("D", 4), s16("E", 4), s16("F", 4),
           s16("G", 4), s16("A", 4), s16("B", 4), s16("C", 5),
           s16("D", 5), s16("C", 5), s16("B", 4), s16("A", 4),
           s16("G", 4), s16("F", 4), s16("E", 4), s16("D", 4)]
    write("03_dense_passage.musicxml", build([run, run, run, run], title="Dense Passage"))

    # 4) 简单旋律（C 大调，测试"无需简化"与转调）
    m = [q("C", 4), q("D", 4), q("E", 4), q("F", 4)]
    m2 = [q("G", 4), q("A", 4), q("B", 4), q("C", 5)]
    m3 = [q("C", 5), q("B", 4), q("A", 4), q("G", 4)]
    m4 = [q("F", 4), q("E", 4), q("D", 4), q("C", 4)]
    write("04_simple_melody.musicxml", build([m, m2, m3, m4, m, m2, m3, m4], title="Simple Melody"))

    # 5) G 大调旋律（含升 F，测试调性检测）
    write("05_key_g_major.musicxml", build([
        [q("G", 3), q("A", 3), q("B", 3), q("C", 4)],
        [q("D", 4), q("E", 4), q("F", 4, alter=1), q("G", 4)],
        [q("A", 4), q("B", 4), q("C", 5), q("D", 5)],
        [q("E", 5), q("F", 5, alter=1), q("D", 5), q("B", 4)],
        [q("G", 4), q("F", 4, alter=1), q("E", 4), q("D", 4)],
        [q("C", 4), q("B", 3), q("A", 3), q("G", 3)],
    ], fifths=1, title="G Major Melody"))

    # 6) 大跨度和弦（测试和弦跨度分析 → 拆分和弦）
    write("06_wide_stretch_chords.musicxml", build([
        [half("C", 2), half("G", 4, chord=True), half("C", 2), half("E", 4, chord=True)],
        [half("G", 2), half("D", 5, chord=True), half("G", 2), half("B", 4, chord=True)],
        [half("F", 2), half("A", 4, chord=True), half("F", 2), half("C", 5, chord=True)],
        [half("C", 2), half("G", 4, chord=True), half("C", 2), half("E", 4, chord=True)],
    ], title="Wide Stretch Chords"))


if __name__ == "__main__":
    main()
