"""LLM 创意层（PRD §9）。

v0.1 仅定义接口与降级路径，真实调用在 v0.2 接入：
- 输入：ScoreSummary（不是整谱，控制 token）+ 用户指令 + 目标水平 + 可用规则清单
- 输出：JSON 决策列表（action/scope/params/rationale），经 rules.validate() 校验
- 降级：LLM 不可用或输出校验失败 → 返回 None，上层走纯规则保守方案

约定：
- 用户自带 Key，服务端不存储 Key（由请求头 Authorization 或服务端环境变量透传）
- 接口为 OpenAI 兼容（base_url + api_key + model），天然支持
  OpenAI / DeepSeek / 通义 / Ollama 等
"""

from __future__ import annotations

from .schemas import ArrangeRequest, EditInstruction


def is_configured() -> bool:
    """LLM 层是否已配置可用（v0.1 恒 False；v0.2 接入真实状态）。

    由 /api/config 的 llm_configured 字段引用，避免端点内硬编码。
    """
    return False


def decide(request: ArrangeRequest) -> tuple[list[EditInstruction], list[str]] | None:
    """根据请求生成改编决策。

    v0.1：恒返回 None（未接入），上层据此走纯规则路径。
    v0.2 实现要点：
      1. 构造 prompt（系统提示词含 JSON Schema 与示例 + 可用规则清单）
      2. 调 OpenAI 兼容 /chat/completions，解析 JSON
      3. 校验失败自动重试 1 次（修正提示），再失败返回 None
    """
    return None
