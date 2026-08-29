# 谱伴 ScoreMate

**在 MuseScore 里选中一段谱子，让 AI 帮你分析并改编——简化、转调、加花，一键回写，可撤销。**

谱伴是一个 **MuseScore 4.7+ 插件 + 本地云端服务** 的开源项目：
插件负责交互（选区 → 请求 → 回写），云端负责分析（规则引擎，后续接入 LLM 创意层）。
云端回传的是**编辑指令**而非整谱，你可以逐条预览、接受、撤销。

> **v0.1 已发布**：分析（调性/难度/简化建议）+ 移调写回 + 压缩音域 + 去重复八度，全部实测通过。

---

## ✨ 功能

| 功能 | 说明 | 状态 |
|---|---|---|
| 🔍 谱面分析 | 调性检测（Krumhansl-Schmuckler）、音域、难度评分 | ✅ 已实测 |
| 📋 简化建议 | 装饰音多 → 删装饰音；和弦过宽 → 拆和弦；密度高 → 降密度；音域宽 → 压缩；节奏复杂 → 简化节奏 | ✅ 已实测（5 条规则端到端可触发） |
| 🔁 移调写回 | ±2/±5/±7 半音，直接改谱，Ctrl+Z 可撤销 | ✅ 已实测 |
| 📐 压缩音域 | 超出 C2-C6 的音按八度平移拉回 | ✅ 已实测 |
| ✂️ 去重复八度 | 和弦内同音名只保留最低音（`chord.remove`） | ✅ 已实测 |
| 🧠 LLM 创意层（v0.2） | 局部和弦重配/加花，使用用户自带的 API Key | 🔜 规划中 |

## 🚀 快速开始（约 10 分钟）

### 1. 装插件

把 [`plugin/ScoreMate/`](plugin/ScoreMate/) 整个文件夹复制到 MuseScore 扩展目录：

- Windows：`C:\Users\<你>\AppData\Local\MuseScore\MuseScore4\extensions\`
- macOS / Linux：`~/Library/Application Support/MuseScore/MuseScore4/extensions/`（如路径不同，在 MuseScore 的 偏好设置 → 文件夹 里查看）

重启 MuseScore → 菜单 **插件 → 谱伴 ScoreMate**。

> 需要 **MuseScore 4.7+**（新扩展系统）。

### 2. 启动云端服务

需要 Python 3.10+：

```bash
cd server
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

> Windows 用户也可以直接双击 `server/start-server.bat`。

验证：浏览器打开 <http://127.0.0.1:8000/api/health>，看到 `{"status":"ok",...}` 即成功。

### 3. 使用

1. 在 MuseScore 里打开一份谱子（可用 [`test-scores/`](test-scores/) 里的测试谱）
2. 选中一段音符（`Ctrl+A` 全选或框选）
3. 插件窗口里：点「分析」看改编建议，或直接点「移调 / 压缩音域 / 去重复八度」改谱
4. 所有改动都可 `Ctrl+Z` 撤销

## 🧱 架构

```
MuseScore 4.7 插件 (QML form)
   │  同步 XMLHttpRequest（实测可行，不依赖异步回调）
   ▼
FastAPI 云端服务（本地运行，端口 8000）
   ├─ 确定性层：调性检测 / 音域 / 难度评分（纯算法，无外部依赖）
   ├─ 规则引擎：简化规则（IF 阈值触发）+ 校验层
   └─ LLM 创意层（v0.2）：OpenAI 兼容接口，用户自带 API Key，云端不存谱
```

- 插件只做三件事：**读选区 → 发请求 → 回写**（`note.pitch` 读写 + `note.parent.remove()` + `startCmd/endCmd` 撤销事务）
- 云端无状态、无数据库，谱面数据请求结束即释放，**不存储、不训练**
- 详细设计见 [`docs/PRD.md`](docs/PRD.md)

## 🧪 测试

```bash
# 核心逻辑（不依赖 fastapi）
python server/tests/smoke_core.py

# API + WebSocket（需 venv）
server/.venv/Scripts/python server/tests/smoke_ws.py

# 端到端：8 份测试谱模拟插件请求（需 venv）
server/.venv/Scripts/python test-scores/verify_pipeline.py
```

测试谱在 [`test-scores/`](test-scores/)，可重新生成：`python test-scores/make_test_scores.py`。

## 📄 文档

- [`docs/PRD.md`](docs/PRD.md) —— 产品设计、协议、规则集、实测记录
- [`docs/user-setup.md`](docs/user-setup.md) —— 新手装机指引
- [`plugin/README.md`](plugin/README.md) —— 插件技术说明

## 🤝 贡献

欢迎 PR！建议先跑一遍测试确认不破坏现有功能。路线图：

- **v0.2**：LLM 创意层（局部重配/加花，用户自带 Key）+ 拆和弦/删装饰音写回 + 压缩音域改"整句移动"
- **v0.3**：设置页（LLM Key / 端口 / 语言）、i18n 中英双语、基准集打分

## 📜 License

MIT © 2025 ScoreMate contributors（详见 [LICENSE](LICENSE)）
