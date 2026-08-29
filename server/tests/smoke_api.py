"""API 冒烟测试：需服务端已启动。

启动服务端：
    cd server && .venv\\Scripts\\activate && uvicorn app.main:app --port 8000
运行本脚本：
    python tests/smoke_api.py
"""

import sys
from pathlib import Path

# httpx2 是新版 httpx 的继任者（starlette TestClient 官方同样以 httpx2 优先），
# 优先使用；老环境回退到 httpx。
try:
    import httpx2 as httpx
except ImportError:  # pragma: no cover - 老环境回退
    import httpx  # type: ignore[no-redef]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://127.0.0.1:8000"
FAILED = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not cond:
        FAILED.append(name)


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=15) as c:
        # 1) health
        r = c.get("/api/health")
        check("health.ok", r.status_code == 200 and r.json().get("status") == "ok", f"got={r.json()}")

        # 2) analyze：C 大调音阶
        r = c.post("/api/analyze", json={"notes": [60, 62, 64, 65, 67, 69, 71, 72], "measures": 2})
        j = r.json()
        check("analyze.key", r.status_code == 200 and j.get("key_estimate") == "C major", f"got={j.get('key_estimate')}")

        # 3) arrange：转调（结构化字段）
        r = c.post("/api/arrange", json={
            "summary": {"title": "t", "key_estimate": "C major", "measures": 16},
            "target_key": "G major",
        })
        j = r.json()
        st = [i["params"]["semitones"] for i in j["instructions"]]
        check("arrange.transpose.7", r.status_code == 200 and st == [7], f"got={st}")

        # 4) arrange：简化（高难度特征 → 5 条规则）
        r = c.post("/api/arrange", json={
            "summary": {
                "title": "t", "key_estimate": "C major", "measures": 16,
                "difficulty_features": {
                    "note_density": 0.75, "max_chord_span": 14, "ornament_count": 6,
                    "range_span": 60, "rhythm_complexity": 0.6,
                },
            },
            "instruction": "简化",
        })
        j = r.json()
        descs = [i["description"] for i in j["instructions"]]
        check("arrange.simplify.count=5", r.status_code == 200 and len(descs) == 5, f"got={len(descs)}")

        # 5) config
        r = c.get("/api/config")
        check("config.capabilities", r.status_code == 200 and "simplify" in r.json()["capabilities"], f"got={r.json()['capabilities']}")

    print("-" * 40)
    if FAILED:
        print(f"FAILED: {FAILED}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
