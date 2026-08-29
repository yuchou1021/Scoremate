# 谱伴 ScoreMate —— 项目交接总结（v0.1 完成）

> 本文档给"新对话的开发者/AI"用：读完即可无缝继续开发。
> 状态：**v0.1 MVP 已完成并开源**，下一步是 v0.2。

---

## 0. 项目一句话

**MuseScore 4.7 插件 + 本地云端服务**：在 MuseScore 里选中一段谱子 → 分析（调性/难度/简化建议）→ 写回乐谱（移调/压缩音域/去重复八度，可撤销）。

- 目标用户：音乐自学者/爱好者、老师/学生
- 核心价值：**"改简单点"这类需求 MuseScore 内置没有**；规则引擎先行（零成本、稳定），LLM 创意层（v0.2）后用用户自带 Key
- License：MIT

## 1. 仓库与运行

- GitHub：`https://github.com/yuchou1021/Scoremate`（main 分支）
- 本地路径：`D:\DeepSeek Harness\musescore-ai-arranger`
- 结构：
  - `server/` —— FastAPI 云端（分析 + 改编指令生成），`start-server.bat` 一键启动（端口 8000）
  - `plugin/ScoreMate/` —— MuseScore 4.7 插件（manifest.json + Main.qml）
  - `test-scores/` —— 8 份测试谱 + 生成器 + 端到端验证脚本
  - `docs/` —— PRD、装机指引、本交接文档

### 运行方式

```powershell
# 云端（Windows 双击 server/start-server.bat 即可）
cd server
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# 插件：复制 plugin/ScoreMate 到
#   C:\Users\<你>\AppData\Local\MuseScore\MuseScore4\extensions\
# 重启 MuseScore → 插件菜单 → 谱伴 ScoreMate
```

### 测试（发布前必跑，3/3 全过）

```powershell
python server/tests/smoke_core.py                                  # 核心逻辑（系统 python）
server/.venv/Scripts/python server/tests/smoke_ws.py               # API+WS（venv）
server/.venv/Scripts/python test-scores/verify_pipeline.py         # 端到端 8 谱（venv）
```

GitHub Actions CI 已配置（push 自动跑以上测试）。

## 2. 已完成（全部实测通过）

| 模块 | 内容 |
|---|---|
| 服务端 | `/api/health` `/api/analyze`（调性 KS 算法/音域/难度；支持插件端传入装饰音数/节奏复杂度实测值）`/api/arrange`（转调+简化规则）`/api/config` + `/ws` WebSocket |
| 插件分析 | 两段式：analyze 提取特征 → arrange 生成指令（调性/难度/简化建议） |
| 插件写回 | 移调 ±2/5/7、压缩音域（C2-C6 八度平移）、去重复八度（chord.remove），均 Ctrl+Z 可撤销 |
| 测试 | 核心 13 项 + API 5 项 + WS 11 项 + 端到端 8 谱（含 5 条简化规则全覆盖断言），全过 |
| 开源 | MIT、CI、README、发布 zip（release/） |

## 3. 架构

```
MuseScore 4.7 插件（新扩展 form）
   │  同步 XMLHttpRequest → HTTP（实测可行；异步回调在 4.7 不执行，勿用）
   ▼
FastAPI 云端（本地 8000，无状态无数据库，不存谱）
   ├─ 确定性层：KS 调性检测 / 音域 / 难度加权公式
   ├─ 规则引擎：IF 阈值 → 简化指令 + 校验层
   └─ LLM 创意层：v0.2 接入（OpenAI 兼容，用户自带 Key）
```

插件只做三件事：**读选区 → 发请求 → 回写**。云端回传"编辑指令"而非整谱。

## 4. 关键踩坑记录（新对话必读，全是实测/源码证实的结论）

1. **MuseScore 4.7 换用新扩展系统**：老插件（`import MuseScore 3.0`）在 4.7 里**创建窗口被禁、onRun 后异步回调不执行**。新系统 = 文件夹内含 `manifest.json`（`uri: musescore://extensions/xxx`，`type: form`，`apiversion: 2`）+ QML form（`import MuseApi.Controls`，`ExtensionBlank`/`FlatButton`）。
2. **插件安装目录**（重要！不是 Documents）：`%LOCALAPPDATA%\MuseScore\MuseScore4\extensions\`。
3. **网络**：form 插件里同步 `XMLHttpRequest` 可用（实测 200 OK）；`api.websocket` 异步回调在 4.7 不执行；`cmd()`/`curScore` 全局在 form 里不存在。
4. **乐谱访问**：`api.engraving.curScore`；选区 `selection.elements` 里**没有 Chord 对象，只有 Note**；和弦成员用 `note.parent.notes` 取；`selection.select` 存在。
5. **删除音符**（找了很久）：`note.parent.remove(note)`（即 chord.remove(note)，参考开源插件 fretboard-plugin）；`removeElement`/`el.remove()`/`parent.removeNote`/`cmd("delete")` 在 form 中均不可用。
6. **写回撤销**：`score.startCmd()` / `score.endCmd()` 包裹；`note.pitch` 可读写。注意：只改 pitch 不处理 `tpc`（音名拼写可能不完美，v0.2 修）。
7. **git push 两台坑**：a) schannel TLS 报错 → 仓库级 `git config http.sslBackend openssl`；b) 系统级 credential.helper=manager 但机器没装 GCM，push 会挂起 → 推送时加 `-c credential.helper=`（令牌放 URL）。
8. **pip 镜像**：本机全局指向清华镜像（曾 403）→ 装依赖用 `-i https://pypi.org/simple`（venv 在 server/.venv）。
9. **PowerShell 调 python**：`python -c` 传含双引号的代码会被剥引号 → 用单引号 here-string 或写临时脚本文件。

## 5. 参考项目：mcp-score

`https://github.com/tskovlund/mcp-score`（MIT，20 star，工程质量高，作者 Thomas Skovlund Hansen）

- 定位：Claude 通过 MCP 驱动 MuseScore/Dorico/Sibelius（开发者工具），与我们（端用户产品）互补
- **v0.2 重点参考**：老式插件用 `pluginType: "dock"` 常驻 + QtWebSockets WebSocketServer（`import QtWebSockets 1.0`）；`cursor.addNote(pitch)` 加音符；`newElement(Element.X)` + `cursor.add()` 加元素；`note.tpc` 拼写；游标式读谱（rewind/next 逐小节）
- 它的"LLM 写 music21 脚本生成谱"思路，可作我们复杂改编的备选通道

## 6. 待办（v0.2+，按优先级）

1. **LLM 创意层**：局部和弦重配/加花（OpenAI 兼容接口 + 用户自带 Key；服务端 llm.py 已留接口与降级路径）；轻量改编走"结构化 JSON 决策+规则校验"，复杂改编可参考 mcp-score 的 music21 生成
2. **补齐简化写回**：拆和弦（split_chords，删除已通，需加音符能力）、删装饰音（grace note 删除）
3. **压缩音域改"整句移动"**：用户反馈逐音八度折叠会破坏旋律线（有的音跳八度有的不动）→ 按短语/声部整体平移
4. **移调补 tpc**：音名拼写正确性
5. **设置页**：LLM Key / 端口 / 语言（i18n 中英并行，PRD 已定）
6. **基准集人工打分**：20 首，验证"越改越差"门禁（test-scores 已有 6 首种子）
7. **插件库上架** musescore.org + GitHub Releases（release/ScoreMate-v0.4.5.zip 已打包）
8. **可选**：MCP 桥接，让 Claude 也能驱动 ScoreMate

## 7. 用户反馈记录

- 压缩音域"乱"：逐音折叠破坏旋律线（见待办 3）
- 用户倾向"不想自己操作测试"→ 云端侧可全自动验证（verify_pipeline.py），插件侧给最简步骤
- 用户已同意公开仓库；文档中不要出现"AI 协作开发"类描述（已清理，grep 过 0 匹配）

## 8. 安全提醒

- 发布用的 GitHub 令牌（ghp_ 开头）应已删除/过期；**再次 push 前需要新令牌**（classic，勾 repo+workflow），推送用 `-c credential.helper=` + URL 内令牌，用完即删
- 服务端无状态不存谱，隐私基线 OK（PRD §10）
