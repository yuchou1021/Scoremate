# plugin/ —— 谱伴 ScoreMate 插件（MuseScore 4.7 新扩展）

> **状态：v0.4.6 已发布** —— 功能在 MuseScore 4.7.4 实测通过；v0.4.6 为 UI 布局修复（内容自适应 + 可滚动），需在 MuseScore 中确认显示效果。

## 安装

把整个 `ScoreMate/` 文件夹复制到 MuseScore 扩展目录：

- **Windows**：`C:\Users\<你>\AppData\Local\MuseScore\MuseScore4\extensions\`
- **macOS / Linux**：在 MuseScore **偏好设置 → 文件夹** 里查看扩展目录

重启 MuseScore → 菜单 **插件 → 谱伴 ScoreMate**。

> 需要 **MuseScore 4.7+**（新扩展系统）。老插件系统在 4.7 中创建窗口被禁，故不使用。

## v0.4.6 UI 修复

- 窗口尺寸改为 `560×520`（原 740×700 偏大，小屏/高缩放下内容溢出）
- 按钮行由固定 `Row` 改为 `Flow`（宽度不足时自动换行，不再超出界面）
- 整个内容包进 `Flickable`（内容超高时可滚动，不再被裁切；MuseScore form 窗口本身不可拉伸，见 musescore/MuseScore#26194）

## 功能（全部实测通过）

| 按钮 | 功能 | 实现 |
|---|---|---|
| 分析选区并生成改编指令 | 调性/难度/简化建议 | 两段式：`/api/analyze` 提取特征 → `/api/arrange` 生成指令 |
| ±2/±5/±7 移调 | 整体移调 | `note.pitch ±= n` + `startCmd/endCmd` |
| 压缩音域 | 超出 C2-C6 的音八度平移 | `note.pitch` 循环 ±12 |
| 去重复八度 | 和弦内同音名只留最低音 | `note.parent.remove(note)` |

## 技术要点（踩坑实录，均为实测/源码证实）

| 能力 | 结论 | 依据 |
|---|---|---|
| 插件格式 | 4.7 新扩展 = `manifest.json` + QML form | 官方 tutorial-2/3 |
| 网络 | 同步 `XMLHttpRequest` → HTTP，**实测 200 OK**；`api.websocket` 异步回调在 4.7 不执行，不用 | 本机实测 |
| 乐谱访问 | `api.engraving.curScore`；选区 `selection.elements` | 官方新版 colornotes |
| 写回 | `note.pitch` 可读写；`startCmd/endCmd` 撤销事务 | 移调实测 |
| **删除音符** | **`note.parent.remove(note)`**（`removeElement`/`cmd("delete")` 在 form 中均不可用） | 开源插件 fretboard-plugin 参考，实测成功 |
| 和弦识别 | 选区内无 Chord 对象 → 用 `note.parent.notes` 取和弦成员 | 实测 |

## 目录

```
ScoreMate/
  manifest.json   # uri: musescore://extensions/scoremate-2, type: form, apiversion: 2
  Main.qml        # 窗口 UI + 全部逻辑（分析/移调/压缩/去重复八度）
```
