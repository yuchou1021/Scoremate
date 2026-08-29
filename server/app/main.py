"""谱伴 ScoreMate 云端服务入口（PRD §6.2）。

启动：uvicorn app.main:app --reload --port 8000

通道：
- HTTP  /api/*   —— 插件端主通道（4.7 form 扩展中同步 XMLHttpRequest
                     实测可用；插件 Main.qml 即走此通道）
- WS    /ws、/   —— 备用/测试通道（MuseScore 插件 api.websocket 的
                     异步回调在 4.7 不执行，插件端未使用）
"""

import json
import re

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import llm, rules
from .__init__ import __version__
from .music_analysis import analyze
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ArrangeRequest,
    ArrangeResponse,
)

app = FastAPI(
    title="谱伴 ScoreMate",
    version=__version__,
    description="MuseScore AI 改编助手云端服务：分析 + 改编指令生成",
)

# 插件以 file:// 方式发请求，开发期放开跨域；自托管上线时建议收紧来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def handle_arrange(req: ArrangeRequest) -> ArrangeResponse:
    """改编主逻辑（HTTP 与 WS 共用，PRD §7.3）。

    意图判定：
    - 显式给了 target_key/semitones，或指令提到 转调/移调/transpose → 转调
    - 指令提到 简化/简单/simplicity，或指令为空 → 简化
    - 两者都提到 → 都做
    """
    explicit = req.instruction.strip()
    # 英文用词边界匹配，避免 "keyboard"/"monkey" 等误触发转调
    mentions_transpose = bool(
        any(k in explicit for k in ("转调", "移调"))
        or re.search(r"\b(transpose|key)\b", explicit, re.IGNORECASE)
    )
    mentions_simplify = bool(
        any(k in explicit for k in ("简化", "简单", "难度"))
        or re.search(r"\bsimplif(y|ication|ied)?\b", explicit, re.IGNORECASE)
    )

    do_transpose = bool(req.target_key or req.semitones is not None or mentions_transpose)
    do_simplify = bool(mentions_simplify or (not explicit and not do_transpose))

    warnings: list[str] = []
    instructions = []
    source = "rules"

    # v0.1：LLM 层未接入（llm.decide 返回 None）；v0.2 起若可用则优先
    llm_result = llm.decide(req)
    if llm_result:
        instructions, warnings = llm_result
        source = "llm"
    else:
        if do_transpose:
            ins, ws = rules.transpose_plan(
                req.summary,
                target_key=req.target_key,
                semitones=req.semitones,
                target_low=req.target_low,
                target_high=req.target_high,
            )
            instructions += ins
            warnings += ws
        if do_simplify:
            ins, ws = rules.simplify_plan(req.summary, req.level)
            instructions += ins
            warnings += ws

    if not instructions:
        warnings.append("未生成任何指令：请提供更明确的要求（如“转到 G 调”“简化”），或先补齐谱面特征数据")
    else:
        warnings += rules.validate(instructions, req.summary.measures)

    return ArrangeResponse(instructions=instructions, warnings=warnings, source=source)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "scoremate", "version": __version__}


@app.get("/api/config")
def config() -> dict:
    return {
        "capabilities": ["analyze", "transpose", "simplify"],
        "analysis": ["key", "range", "difficulty"],
        "levels": ["simple", "medium"],
        "transport": ["http", "websocket"],  # HTTP 为插件端实际通道；WS 为测试/备用
        "llm_configured": llm.is_configured(),
        "notes": "v0.1 为纯规则引擎；LLM 创意层（局部重配/加花）在 v0.2 接入",
    }


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze_endpoint(req: AnalyzeRequest) -> AnalyzeResponse:
    """分析：调性检测 + 音域 + 难度评分。

    输入 midi 音高列表即可；装饰音/节奏复杂度由插件端实测后传入。
    """
    return analyze(
        req.notes,
        req.measures,
        ornament_count=req.ornament_count,
        rhythm_complexity=req.rhythm_complexity,
    )


@app.post("/api/arrange", response_model=ArrangeResponse)
def arrange_endpoint(req: ArrangeRequest) -> ArrangeResponse:
    return handle_arrange(req)


async def _ws_handler(ws: WebSocket) -> None:
    """WebSocket 通道（测试与备用，协议同 HTTP /api/*）。

    插件端实际走同步 XMLHttpRequest → HTTP；WS 保留给测试与其他客户端。
    MuseScore 插件 api.websocket.open(port) 连接的是 ws://127.0.0.1:port/
    （根路径），故在 "/" 暴露；"/ws" 为别名，供测试与其他客户端使用。

    请求（JSON 文本）：
      {"type": "arrange", "payload": {ArrangeRequest 字段}}
      {"type": "analyze", "payload": {"notes": [...], "measures": n}}
    响应（JSON 文本）：
      {"type": "arrange", "result": {ArrangeResponse}}
      {"type": "analyze", "result": {AnalyzeResponse}}
      {"type": "error", "message": "..."}
    """
    await ws.accept()
    try:
        while True:
            text = await ws.receive_text()
            try:
                msg = json.loads(text)
                mtype = msg.get("type", "")
                payload = msg.get("payload", {})
                print(f"[ScoreMate] WS 收到请求: type={mtype}", flush=True)
                if mtype == "arrange":
                    req = ArrangeRequest.model_validate(payload)
                    result = handle_arrange(req).model_dump()
                    await ws.send_text(json.dumps({"type": "arrange", "result": result}))
                elif mtype == "analyze":
                    req = AnalyzeRequest.model_validate(payload)
                    result = analyze(
                        req.notes,
                        req.measures,
                        ornament_count=req.ornament_count,
                        rhythm_complexity=req.rhythm_complexity,
                    ).model_dump()
                    await ws.send_text(json.dumps({"type": "analyze", "result": result}))
                else:
                    await ws.send_text(json.dumps({"type": "error", "message": f"未知消息类型: {mtype}"}))
            except Exception as exc:  # 单条消息失败不影响连接
                await ws.send_text(json.dumps({"type": "error", "message": str(exc)}))
    except WebSocketDisconnect:
        pass


@app.websocket("/")
async def ws_root(ws: WebSocket) -> None:
    """根路径别名（MuseScore api.websocket.open(port) 连接的路径）。"""
    await _ws_handler(ws)


@app.websocket("/ws")
async def ws_api(ws: WebSocket) -> None:
    """通道别名：测试与其他客户端使用。"""
    await _ws_handler(ws)
