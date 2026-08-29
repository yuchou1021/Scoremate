/*
 * 谱伴 ScoreMate —— MuseScore 4.7 新扩展（form）v0.4.7
 *
 * 里程碑 2 功能：
 *   1. 分析升级：两段式（/api/analyze 提取特征 → /api/arrange 生成指令）
 *   2. 移调写回：预设按钮直接改选中音符（Ctrl+Z 可撤销）
 *
 * v0.4.6 UI 修复：内容自适应 + 可滚动（按钮行 Flow 换行、Flickable 滚动），
 *   解决窗口尺寸变化时按钮溢出/内容被裁切的问题。
 * v0.4.7 写回增强：
 *   - 「执行以上建议」：把分析生成的指令映射到写回操作（移调/压缩音域/
 *     去重复八度），未支持的规则明确提示 v0.2
 *   - 压缩音域改为「整句移动」：整段上移/下移保持旋律轮廓，不再逐音折叠
 *
 * 网络：同步 XMLHttpRequest → HTTP（4.7 实测可用；同步不依赖异步回调）
 * 乐谱：api.engraving.curScore（新 API），写操作包在 startCmd/endCmd 里
 *   （参照官方新版 colornotes 扩展的写法）。
 *
 * 安装：整个 ScoreMate 文件夹复制到
 *   C:\Users\<你>\AppData\Local\MuseScore\MuseScore4\extensions\
 *   重启 MuseScore → 插件菜单 → 谱伴 ScoreMate。
 * 运行前提：云端服务已启动（start-server.bat，端口 8000）。
 */

import QtQuick
import MuseApi.Controls

ExtensionBlank {
    id: root

    // 最近一次分析生成的改编指令（供"执行以上建议"按钮使用）
    property var lastInstructions: []
    property var lastCollected: null

    // 初始窗口尺寸（MuseScore form 窗口不可自由拉伸，故内容需自适应+可滚动，
    // 避免按钮行溢出、窗口过小时内容被裁切——见 musescore/MuseScore#26194）
    implicitHeight: 520
    implicitWidth: 560

    Flickable {
        id: scroll
        anchors.fill: parent
        contentWidth: column.width + 24
        contentHeight: column.height + 24
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: column
            x: 12
            y: 12
            width: Math.max(scroll.width - 24, 320)
            spacing: 10

            StyledTextLabel {
                text: "谱伴 ScoreMate（4.7 扩展版 v0.4）"
            }

            StyledTextLabel { text: "① 分析（生成改编建议）：" }
            Flow {
                width: parent.width
                spacing: 6
                FlatButton {
                    text: "分析选区并生成改编指令"
                    onClicked: root.runAnalysis()
                }
                FlatButton {
                    text: "执行以上建议"
                    onClicked: root.applySuggestions()
                }
            }

            StyledTextLabel { text: "② 移调写回（直接改谱，Ctrl+Z 可撤销）：" }
            Flow {
                width: parent.width
                spacing: 6
                FlatButton { text: "-7";  onClicked: root.applyTranspose(-7) }
                FlatButton { text: "-5";  onClicked: root.applyTranspose(-5) }
                FlatButton { text: "-2";  onClicked: root.applyTranspose(-2) }
                FlatButton { text: "+2";  onClicked: root.applyTranspose(2) }
                FlatButton { text: "+5";  onClicked: root.applyTranspose(5) }
                FlatButton { text: "+7";  onClicked: root.applyTranspose(7) }
            }

            StyledTextLabel { text: "③ 简化写回（直接改谱，Ctrl+Z 可撤销）：" }
            Flow {
                width: parent.width
                spacing: 6
                FlatButton { text: "压缩音域（拉回 C2-C6）"; onClicked: root.compressRange() }
                FlatButton { text: "去重复八度"; onClicked: root.reduceDensity() }
            }

            Text {
                id: report
                width: parent.width
                wrapMode: Text.WordWrap
                font.pixelSize: 12
                text: "使用说明：\n1. 在乐谱中选中一段音符\n2. 点「分析」看改编建议；或直接点「移调」按钮改谱"
            }
        }
    }

    // 当前乐谱对象（新 API 优先）
    function currentScore() {
        if (typeof api !== "undefined" && api.engraving && api.engraving.curScore) {
            return api.engraving.curScore
        }
        if (typeof curScore !== "undefined") {
            return curScore
        }
        return null
    }

    // 收集选区：音符元素引用、音高列表、和弦跨度、和弦元素、时值类型、装饰音数
    function collectElements() {
        var score = currentScore()
        if (!score) {
            return { elements: [], notes: [], chords: [], chordElements: [], durationTypes: [], ornaments: 0 }
        }
        var elements = []
        var notes = []
        var chords = []
        var chordElements = []
        var durationTypes = []
        var ornaments = 0
        var fullScore = !score.selection.elements.length
        if (fullScore) {
            try { cmd("select-all") } catch (e) {}
        }
        for (var i in score.selection.elements) {
            var el = score.selection.elements[i]
            if (el.pitch !== undefined) {
                notes.push(el.pitch)
                elements.push(el)
                // 时值类型（防御式读取，用于节奏复杂度）
                try {
                    if (el.type !== undefined && el.type !== null) {
                        durationTypes.push(String(el.type))
                    } else if (el.durationType !== undefined && el.durationType !== null) {
                        durationTypes.push(String(el.durationType))
                    }
                } catch (e) {}
                // 装饰音标记（倚音/波音/颤音，防御式读取）
                try {
                    if (el.grace === true || el.isGrace === true ||
                        (el.graceIndex !== undefined && el.graceIndex !== null)) {
                        ornaments++
                    } else if (el.type !== undefined && String(el.type).indexOf("grace") >= 0) {
                        ornaments++
                    }
                } catch (e) {}
            }
            if (el.notes !== undefined && el.notes.length > 0) {
                chordElements.push(el)
                var lo = 127
                var hi = 0
                for (var j in el.notes) {
                    var n = el.notes[j]
                    if (n.pitch < lo) { lo = n.pitch }
                    if (n.pitch > hi) { hi = n.pitch }
                }
                chords.push(hi - lo)
            }
        }
        if (fullScore) {
            try { cmd("escape") } catch (e) {}
        }
        return { elements: elements, notes: notes, chords: chords, chordElements: chordElements,
                 durationTypes: durationTypes, ornaments: ornaments }
    }

    // 节奏复杂度 0-1：短时值（32分/64分）音符占比越高越复杂
    function computeRhythmComplexity(durationTypes) {
        if (!durationTypes || durationTypes.length === 0) {
            return 0
        }
        var shortCount = 0
        for (var i in durationTypes) {
            var t = durationTypes[i].toLowerCase()
            if (t.indexOf("32") >= 0 || t.indexOf("64") >= 0 || t.indexOf("128") >= 0) {
                shortCount++
            }
        }
        return Math.min(1.0, shortCount / durationTypes.length)
    }

    function maxSpan(chords) {
        var m = 0
        for (var i in chords) {
            if (chords[i] > m) { m = chords[i] }
        }
        return m
    }

    // 摘要（analysis 来自 /api/analyze 的响应）
    function buildSummary(collected, analysis) {
        var hi = 0
        var lo = 127
        for (var i in collected.notes) {
            if (collected.notes[i] > hi) { hi = collected.notes[i] }
            if (collected.notes[i] < lo) { lo = collected.notes[i] }
        }
        var score = currentScore()
        var features = { "note_density": 0, "max_chord_span": 0,
                         "ornament_count": 0, "rhythm_complexity": 0, "range_span": hi - lo }
        if (analysis && analysis.features) {
            features = analysis.features
        }
        // 和弦跨度服务端从扁平音高列表算不出，用插件端实测值（取较大者）
        var span = root.maxSpan(collected.chords)
        if (span > (features.max_chord_span || 0)) {
            features.max_chord_span = span
        }
        return {
            "title": score && score.title !== undefined ? score.title : "",
            "time_signature": "4/4",
            "key_estimate": analysis && analysis.key_estimate ? analysis.key_estimate : null,
            "measures": 0,
            "voices": score && score.nstaves !== undefined ? score.nstaves : 1,
            "range": { "low_midi": lo <= 127 ? lo : null, "high_midi": hi },
            "difficulty_features": features,
            "selected": { "start_measure": 1, "end_measure": 0 },
            "excerpt": ""
        }
    }

    function formatResponse(text) {
        var lines = ["===== 谱伴 ScoreMate 分析结果 =====", ""]
        var obj = JSON.parse(text)
        if (obj.key_estimate !== undefined) {
            lines.push("调性估计：" + obj.key_estimate + "（置信度 " + obj.key_confidence + "）")
            lines.push("难度评分：" + obj.difficulty)
            lines.push("")
        }
        var ins = obj.instructions || []
        lines.push("生成 " + ins.length + " 条改编指令：")
        for (var i in ins) {
            lines.push("  [" + ins[i].id + "] " + ins[i].description)
        }
        var warns = obj.warnings || []
        for (var j in warns) {
            lines.push("  ⚠ " + warns[j])
        }
        lines.push("")
        lines.push("提示：点「执行以上建议」可应用已支持的指令（移调/压缩音域/去重复八度）；")
        lines.push("删装饰音/拆和弦/简化节奏的写回将在 v0.2 支持。")
        return lines.join("\n")
    }

    function runAnalysis() {
        try {
            var collected = collectElements()
            if (collected.notes.length === 0) {
                report.text = "没有找到音符。\n请先在乐谱中选中一段音符，再点按钮。"
                return
            }
            report.text = "已收集 " + collected.notes.length + " 个音符，正在分析..."

            var url = "http://127.0.0.1:8000"

            // 第一步：/api/analyze 提取特征（装饰音/节奏复杂度为插件端实测值）
            var analysis = null
            var rhythm = root.computeRhythmComplexity(collected.durationTypes)
            var x1 = new XMLHttpRequest()
            x1.open("POST", url + "/api/analyze", false)
            x1.setRequestHeader("Content-Type", "application/json")
            x1.send(JSON.stringify({
                "notes": collected.notes,
                "measures": 1,
                "ornament_count": collected.ornaments,
                "rhythm_complexity": rhythm
            }))
            if (x1.status === 200) {
                analysis = JSON.parse(x1.responseText)
            } else {
                report.text = "分析请求失败（状态码 " + x1.status + "）\n请确认云端服务已启动（start-server.bat）。"
                return
            }

            // 第二步：/api/arrange 生成改编指令
            var summary = buildSummary(collected, analysis)
            var x2 = new XMLHttpRequest()
            x2.open("POST", url + "/api/arrange", false)
            x2.setRequestHeader("Content-Type", "application/json")
            x2.send(JSON.stringify({
                "summary": summary,
                "instruction": "简化",
                "level": "simple"
            }))
            if (x2.status !== 200) {
                report.text = "改编请求失败（状态码 " + x2.status + "）\n" + x2.responseText
                return
            }
            var parsed = JSON.parse(x2.responseText)
            root.lastInstructions = parsed.instructions || []
            root.lastCollected = collected
            report.text = formatResponse(x2.responseText)
        } catch (e) {
            report.text = "出错：" + e
        }
    }

    // 执行最近一次分析生成的改编指令（写回乐谱，可撤销）。
    // 已支持：转调 / 压缩音域 / 去重复八度；其余规则（删装饰音/拆和弦/
    // 简化节奏）写回在 v0.2 接入，这里明确提示而不是静默跳过。
    function applySuggestions() {
        try {
            var ins = root.lastInstructions
            if (!ins || ins.length === 0) {
                report.text = "没有可执行的建议。\n请先点「分析选区并生成改编指令」。"
                return
            }
            var collected = collectElements()
            if (collected.elements.length === 0) {
                report.text = "没有找到音符。\n请先在乐谱中选中一段音符，再执行建议。"
                return
            }

            var lines = ["===== 执行改编建议 =====", ""]
            var executed = 0
            var skipped = []

            for (var i in ins) {
                var it = ins[i]
                var rules = (it.params && it.params.rules) || []
                if (it.type === "transpose" && it.params && it.params.semitones !== undefined) {
                    // 转调：直接改选中音符 pitch
                    root.applyTranspose(it.params.semitones)
                    lines.push("✓ [" + it.id + "] " + it.description)
                    executed++
                } else if (rules.indexOf("compress_range") >= 0) {
                    // 压缩音域（整句移动）
                    root.compressRange()
                    lines.push("✓ [" + it.id + "] " + it.description)
                    executed++
                } else if (rules.indexOf("reduce_density") >= 0) {
                    // 去重复八度（降密度）
                    root.reduceDensity()
                    lines.push("✓ [" + it.id + "] " + it.description)
                    executed++
                } else {
                    skipped.push("  ✗ [" + it.id + "] " + it.description + "（v0.2 支持写回）")
                }
            }

            lines.push("")
            if (executed > 0) {
                lines.push("已应用 " + executed + " 条指令，均可 Ctrl+Z 撤销。")
            }
            if (skipped.length > 0) {
                lines.push("以下指令暂不支持写回：")
                for (var k in skipped) {
                    lines.push(skipped[k])
                }
            }
            report.text = lines.join("\n")
        } catch (e) {
            report.text = "执行建议出错：" + e
        }
    }

    // 移调写回：直接改选中音符的 pitch（可撤销）
    function applyTranspose(n) {
        try {
            var collected = collectElements()
            if (collected.elements.length === 0) {
                report.text = "没有找到音符。\n请先选中一段音符。"
                return
            }
            var score = currentScore()
            var outOfRange = 0
            if (score && score.startCmd) {
                score.startCmd()
            }
            for (var i in collected.elements) {
                var p = collected.elements[i].pitch + n
                if (p < 0 || p > 127) {
                    outOfRange++
                    continue
                }
                collected.elements[i].pitch = p
            }
            if (score && score.endCmd) {
                score.endCmd()
            }
            var msg = "移调完成：" + (n > 0 ? "+" : "") + n + " 半音，共处理 " +
                      collected.elements.length + " 个音符"
            if (outOfRange > 0) {
                msg += "（跳过 " + outOfRange + " 个越界音符）"
            }
            msg += "\n可用 Ctrl+Z 撤销。"
            report.text = msg
        } catch (e) {
            report.text = "移调出错：" + e
        }
    }

    // 压缩音域 v2（整句移动）：统计整体越界方向，整段上移/下移一个八度，
    // 保持旋律轮廓不变；不再逐音折叠（逐音折叠会破坏旋律线——用户反馈）。
    // 跨度极大（同时超高低界且超 5 个八度）时提示缩小选区，不强行压缩。
    function compressRange() {
        try {
            var collected = collectElements()
            var score = currentScore()
            if (!score || collected.elements.length === 0) {
                report.text = "没有找到音符。\n请先选中一段音符。"
                return
            }
            var LOW = 36   // C2
            var HIGH = 84  // C6
            var maxP = 0
            var minP = 127
            for (var i in collected.notes) {
                var p = collected.notes[i]
                if (p > maxP) { maxP = p }
                if (p < minP) { minP = p }
            }
            var above = maxP > HIGH
            var below = minP < LOW
            if (!above && !below) {
                report.text = "没有超出 C2-C6 范围的音符，无需压缩。"
                return
            }
            // 跨度极大：整句移动无法同时解决高低两侧越界，提示用户而非硬压
            if (above && below && (maxP - minP) > 60) {
                report.text = "选区跨度超过 5 个八度（最低 " + minP + "，最高 " + maxP + "），\n" +
                              "整句移动无法同时解决高低越界。\n请缩小选区后再试，或手动处理极端音符。"
                return
            }

            var shift = 0
            if (above) {
                // 整体偏高：整句下移，直到最高音不越界（上限 2 个八度）
                while (maxP + shift > HIGH && shift > -24) { shift -= 12 }
            } else {
                // 整体偏低：整句上移，直到最低音不越界（上限 2 个八度）
                while (minP + shift < LOW && shift < 24) { shift += 12 }
            }

            var moved = 0
            if (shift !== 0) {
                if (score && score.startCmd) {
                    score.startCmd()
                }
                for (var j in collected.elements) {
                    var el = collected.elements[j]
                    if (el.pitch === undefined) { continue }
                    var np = el.pitch + shift
                    if (np < 0 || np > 127) { continue }
                    el.pitch = np
                    moved++
                }
                if (score && score.endCmd) {
                    score.endCmd()
                }
                var dirWord = shift < 0 ? "下移" : "上移"
                report.text = "压缩音域完成：整句" + dirWord + " " + Math.abs(shift) +
                              " 个半音，共移动 " + moved + " 个音符（旋律轮廓保持不变）\n可用 Ctrl+Z 撤销。"
            } else {
                report.text = "压缩音域：整句移动无法解决（越界方向冲突），请缩小选区后重试。"
            }
        } catch (e) {
            report.text = "压缩音域出错：" + e
        }
    }

    // 判断音符是否是和弦内同音名的更高八度重复（保留最低音）
    function isOctaveDuplicate(n, notes) {
        var pc = ((n.pitch % 12) + 12) % 12
        for (var j in notes) {
            var m = notes[j]
            if (m === n) { continue }
            if (((m.pitch % 12) + 12) % 12 === pc && m.pitch < n.pitch) {
                return true
            }
        }
        return false
    }

    // 防御式删除：依次尝试多种 API（真实插件源码证实的优先）
    function tryRemove(score, el) {
        var parent = el.parent
        // 1) chord.remove(note) —— 开源插件 fretboard-plugin 证实（chord = note.parent）
        if (parent && typeof parent.remove === "function") {
            try { parent.remove(el); return true } catch (e) {}
        }
        // 2) 全局 removeElement(el) —— 开源插件 violin-fingering / xmms-tools 证实
        if (typeof removeElement === "function") {
            try { removeElement(el); return true } catch (e) {}
        }
        // 3) score.removeElement
        if (typeof score.removeElement === "function") {
            try { score.removeElement(el); return true } catch (e) {}
        }
        // 4) 元素自身 remove()
        if (typeof el.remove === "function") {
            try { el.remove(); return true } catch (e) {}
        }
        // 5) 父和弦 removeNote()
        if (parent && typeof parent.removeNote === "function") {
            try { parent.removeNote(el); return true } catch (e) {}
        }
        // 6) 老全局 curScore.removeElement
        if (typeof curScore !== "undefined" && typeof curScore.removeElement === "function") {
            try { curScore.removeElement(el); return true } catch (e) {}
        }
        // 7) 选中音符 + cmd("delete")
        try {
            if (typeof cmd === "function" && score.selection &&
                typeof score.selection.select === "function") {
                score.selection.select(el)
                cmd("delete")
                return true
            }
        } catch (e) {}
        return false
    }

    // 属性诊断（找不到和弦结构时输出，帮助定位 4.7 API 形态）
    function dumpProps(el) {
        if (!el) { return "null" }
        var props = ["pitch", "track", "voice", "staff", "tick", "type", "className",
                     "objectName", "name", "parent", "segment", "notes", "pos", "x",
                     "y", "pagePos", "uniqueID", "id", "index"]
        var out = []
        for (var i in props) {
            try {
                var v = el[props[i]]
                out.push(props[i] + "=" + (v === null ? "null" : (typeof v === "object" ? "obj" : v)))
            } catch (e) {
                out.push(props[i] + "=ERR")
            }
        }
        return out.join(" | ")
    }

    // 去重复八度：每个和弦内同音名只保留最低音
    // 4.7 新 API：选区内没有 Chord 对象、parent 引用也不相等，
    // 故改为直接读 note.parent.notes（和弦成员列表）判断重复。
    function reduceDensity() {
        try {
            var collected = collectElements()
            var score = currentScore()
            if (!score || collected.elements.length === 0) {
                report.text = "没有找到音符。\n请先选中一段音符（Ctrl+A 全选）。"
                return
            }

            var removed = 0
            var failed = 0
            var chordsUsed = 0
            if (score && score.startCmd) {
                score.startCmd()
            }

            // 途径 A：元素本身是 Chord（含 .notes）
            if (collected.chordElements.length > 0) {
                for (var a in collected.chordElements) {
                    var notesA = collected.chordElements[a].notes
                    chordsUsed++
                    var toRemoveA = []
                    for (var b in notesA) {
                        if (root.isOctaveDuplicate(notesA[b], notesA)) {
                            toRemoveA.push(notesA[b])
                        }
                    }
                    for (var c in toRemoveA) {
                        if (root.tryRemove(score, toRemoveA[c])) { removed++ } else { failed++ }
                    }
                }
            } else {
                // 途径 B：音符的 parent.notes（和弦成员列表）
                for (var d in collected.elements) {
                    var n = collected.elements[d]
                    var p = n.parent
                    if (!p) { continue }
                    var chordNotes = p.notes
                    if (chordNotes === undefined || chordNotes.length < 2) { continue }
                    chordsUsed++
                    if (root.isOctaveDuplicate(n, chordNotes)) {
                        if (root.tryRemove(score, n)) { removed++ } else { failed++ }
                    }
                }
            }
            if (score && score.endCmd) {
                score.endCmd()
            }

            var msg
            if (chordsUsed === 0) {
                msg = "未找到和弦结构（音符的 parent 无 .notes）。\n" +
                      "选区内音符数：" + collected.elements.length + "\n" +
                      "第一个音符属性诊断：\n" + root.dumpProps(collected.elements[0]) +
                      "\n\n请把此报告发给开发者。"
            } else {
                msg = "识别到 " + chordsUsed + " 个和弦"
                if (removed === 0 && failed === 0) {
                    msg += "；未发现重复八度（每个和弦内同音名只保留最低音）。"
                } else {
                    msg += "；移除 " + removed + " 个音符"
                    if (failed > 0) {
                        msg += "（" + failed + " 个删除失败）"
                        msg += "\n诊断：cmd=" + (typeof cmd) + " curScore=" +
                               (typeof curScore) + " selection.select=" +
                               (score && score.selection ? typeof score.selection.select : "无")
                    }
                    msg += "\n可用 Ctrl+Z 撤销。"
                }
            }
            report.text = msg
        } catch (e) {
            report.text = "去重复八度出错：" + e
        }
    }
}
