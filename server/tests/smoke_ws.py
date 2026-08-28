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
