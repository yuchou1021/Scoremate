"""WebSocket 通道冒烟测试（v0.1 协议）。

不依赖真实运行中的服务端：使用 FastAPI TestClient（内存内）。
运行（需 venv）：
    .venv\\Scripts\\python tests\\smoke_ws.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

FAILED = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not cond:
        FAILED.append(name)


def main() -> int:
    client = TestClient(app)

    # 0) 根路径 "/"（插件 api.websocket.open 实际连接的路径）
    with client.websocket_connect("/") as ws:
        ws.send_json({"type": "analyze", "payload": {"notes": [60, 62, 64, 65, 67, 69, 71, 72], "measures": 2}})
        data = ws.receive_json()
        check("ws.root.analyze.key", data["type"] == "analyze" and data["result"]["key_estimate"] == "C major",
              f"got={data['result'].get('key_estimate')}")

    with client.websocket_connect("/ws") as ws:
        # 1) analyze 经 WS
        ws.send_json({"type": "analyze", "payload": {"notes": [60, 62, 64, 65, 67, 69, 71, 72], "measures": 2}})
        data = ws.receive_json()
        check("ws.analyze.key", data["type"] == "analyze" and data["result"]["key_estimate"] == "C major",
              f"got={data['result'].get('key_estimate')}")

        # 2) arrange 转调经 WS
        ws.send_json({"type": "arrange", "payload": {
            "summary": {"title": "t", "key_estimate": "C major", "measures": 16},
            "target_key": "G major",
        }})
        data = ws.receive_json()
        st = [i["params"]["semitones"] for i in data["result"]["instructions"]]
        check("ws.arrange.transpose.7", data["type"] == "arrange" and st == [7], f"got={st}")

        # 3) 未知类型 → error
        ws.send_json({"type": "bogus", "payload": {}})
        data = ws.receive_json()
        check("ws.error.unknown_type", data["type"] == "error", f"got={data}")

    # 3.1) 意图判定：含 "keyboard" 的英文指令不应误触发转调（词边界匹配）
    r = client.post("/api/arrange", json={
        "summary": {"title": "t", "key_estimate": "C major", "measures": 16,
                    "difficulty_features": {"note_density": 0.2}},
        "instruction": "keyboard accompaniment please",
    })
    j = r.json()
    types = [i["type"] for i in j["instructions"]]
    check("intent.keyboard_no_transpose", "transpose" not in types, f"got={types}")

    # 3.2) 意图判定：真正的 "transpose" 单词 + 目标调 → 触发转调
    r = client.post("/api/arrange", json={
        "summary": {"title": "t", "key_estimate": "C major", "measures": 16},
        "instruction": "transpose please",
        "target_key": "G major",
    })
    j = r.json()
    types = [i["type"] for i in j["instructions"]]
    check("intent.transpose_word", types == ["transpose"], f"got={types}")

    # 3.3) 意图判定：中文 "转G调" 触发转调
    r = client.post("/api/arrange", json={
        "summary": {"title": "t", "key_estimate": "C major", "measures": 16},
        "instruction": "转G调",
        "target_key": "G major",
    })
    j = r.json()
    types = [i["type"] for i in j["instructions"]]
    check("intent.zh_transpose", types == ["transpose"], f"got={types}")

    # 3.6) 意图判定：提到转调但未给目标调 → 不产出指令，仅提示（行为不变）
    r = client.post("/api/arrange", json={
        "summary": {"title": "t", "key_estimate": "C major", "measures": 16},
        "instruction": "transpose to G",
    })
    j = r.json()
    check("intent.transpose_no_target",
          j["instructions"] == [] and any("目标调" in w for w in j["warnings"]),
          f"got instructions={j['instructions']} warnings={j['warnings']}")

    # 3.4) 意图判定："简化" 触发简化规则
    r = client.post("/api/arrange", json={
        "summary": {"title": "t", "key_estimate": "C major", "measures": 16,
                    "difficulty_features": {"range_span": 60}},
        "instruction": "简化",
    })
    j = r.json()
    types = {i["type"] for i in j["instructions"]}
    check("intent.zh_simplify", "simplify" in types, f"got={types}")

    # 3.5) 意图判定："simplify" 英文单词触发简化（词边界）
    r = client.post("/api/arrange", json={
        "summary": {"title": "t", "key_estimate": "C major", "measures": 16,
                    "difficulty_features": {"range_span": 60}},
        "instruction": "simplify it",
    })
    j = r.json()
    types = {i["type"] for i in j["instructions"]}
    check("intent.en_simplify", "simplify" in types, f"got={types}")

    # 4) HTTP 通道仍正常（回归）
    r = client.get("/api/health")
    check("http.health", r.status_code == 200 and r.json()["status"] == "ok", f"got={r.status_code}")

    print("-" * 40)
    if FAILED:
        print(f"FAILED: {FAILED}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
