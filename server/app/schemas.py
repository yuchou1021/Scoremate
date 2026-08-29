"""数据协议（与 PRD §7 对应）。

约定：谱面传输使用自定义 JSON（轻量、token 少、插件端解析简单），
MusicXML 仅作为与外部工具互通的导出格式，不作为主协议。
"""

from typing import Optional

from pydantic import BaseModel, Field


class DifficultyFeatures(BaseModel):
    """难度特征（PRD §8 难度评分公式的输入项）。"""

    note_density: float = 0.0  # 0-1 音符密度
    max_chord_span: int = 0  # 最大和弦跨度（半音）
    ornament_count: int = 0  # 装饰音数量
    rhythm_complexity: float = 0.0  # 0-1 节奏复杂度
    range_span: int = 0  # 音域跨度（半音）


class ScoreSummary(BaseModel):
    """插件端发给云端的谱面摘要（PRD §7.1）。"""

    title: str = "未命名"
    time_signature: str = "4/4"
    key_estimate: Optional[str] = None  # 如 "G major"，可由插件端分析或传音符让服务端算
    measures: int = 0
    voices: int = 1
    range: Optional[dict] = None  # {"low_midi": int, "high_midi": int}
    difficulty_features: DifficultyFeatures = Field(default_factory=DifficultyFeatures)
    selected: dict = Field(
        default_factory=lambda: {"start_measure": 1, "end_measure": 0}
    )  # end_measure=0 表示到曲末
    excerpt: str = ""  # 旋律片段简化表示（控制 token，v0.2 LLM 层使用）


class AnalyzeRequest(BaseModel):
    """分析请求：midi 音高列表 + 插件端实测特征。

    notes 足够 v0.1 的调性/音域/密度分析；装饰音与节奏复杂度无法从
    扁平音高列表推导，由插件端从乐谱对象实测后传入（缺省为 0）。
    """

    notes: list[int] = Field(default_factory=list)
    measures: int = 1
    ornament_count: int = 0  # 插件端实测：装饰音（倚音/波音/颤音）数量
    rhythm_complexity: float = 0.0  # 插件端实测：0-1 节奏复杂度（短时值/三连音占比）


class AnalyzeResponse(BaseModel):
    key_estimate: Optional[str]
    key_confidence: float
    range: dict
    difficulty: float
    features: DifficultyFeatures


class EditInstruction(BaseModel):
    """编辑指令（PRD §7.2）：云端回传的不是整谱，而是一组可预览/可撤销的指令。"""

    id: str
    type: str  # transpose | simplify | reharmonize | embellish | ...
    scope: dict  # {"start_measure": int, "end_measure": int, "voices": list[int]}
    params: dict
    description: str  # 用户可读的改动说明
    rationale: str  # 为什么这么改


class ArrangeRequest(BaseModel):
    """改编请求（PRD §7.3 /api/arrange）。"""

    summary: ScoreSummary
    instruction: str = ""  # 用户自然语言要求，如 "转G调" "简化"
    level: str = "simple"  # simple | medium
    target_key: Optional[str] = None  # 转调目标调，如 "F major"
    semitones: Optional[int] = None  # 或直接指定半音数
    target_low: Optional[int] = None  # 目标音域下界（MIDI）
    target_high: Optional[int] = None  # 目标音域上界（MIDI）


class ArrangeResponse(BaseModel):
    instructions: list[EditInstruction]
    warnings: list[str]
    source: str = "rules"  # rules | llm | fallback
