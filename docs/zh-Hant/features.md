<!-- 譯自 docs/features.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/features.md -->

# 功能目錄

> 本文件譯自 [`features.md`](../features.md)，內容以英文版為準。

OpenSquilla 結合了個人 Agent runtime，以及模型路由、工具、記憶、頻道、排程，
與可重複使用的 skill。

## 產品介面

| 介面 | 用途 |
| --- | --- |
| Web UI | 本地端控制台、設定、聊天工作階段、核准、日誌、頻道與使用量介面。 |
| CLI 聊天 | 互動式終端機 Agent 工作。 |
| CLI Agent | 單回合自動化、類似 CI 的執行，以及基準測試風格的呼叫。 |
| Gateway RPC | 給 Web UI、CLI 客戶端、頻道與外部客戶端使用的本地端伺服器介面。 |
| 頻道 | Telegram、Slack、Feishu／Lark、Discord、DingTalk、WeCom、Matrix、QQ、終端機，以及 websocket 風格的整合。 |

## 特色功能

### SquillaRouter

用於選擇模型層級的本地端路由。其設計目標是讓簡單的回合維持低成本，並把
昂貴的模型保留給真正需要的工作。

延伸閱讀：[`features/squilla-router.md`](../features/squilla-router.md)

### TUI 前端

終端機聊天使用串流平面處理 token 差異內容，並使用結構化 UI 平面處理外掛
快照，例如 Router HUD。

面向使用者的終端機聊天用法，請見 [`tui.md`](../tui.md)；後端細節請見
[`features/tui-frontend.md`](../features/tui-frontend.md)。

### 工具壓縮

大型工具輸出，會被投射成精簡、provider 可見的預覽，同時 runtime 可以將更
完整的原始結果保留在頻道之外。

延伸閱讀：[`features/tool-compression.md`](../features/tool-compression.md)

### Meta-Skills

可重複的多步驟工作流程可以表示為 skill，並加以檢視、提議、重播與重複
使用。預設情況下，使用者會在支援的聊天介面中，手動以 `/meta` 與
`/meta <name>` 啟動它們。

延伸閱讀：[`features/meta-skills.md`](../features/meta-skills.md) 與
[`features/meta-skill-user-guide.md`](../features/meta-skill-user-guide.md)

### 記憶

持久化記憶讓 OpenSquilla 能夠回想有用的使用者偏好、專案筆記與先前的任務
軌跡，而不必把每一份舊的逐字稿都塞進目前使用中的提示詞。

延伸閱讀：[`features/memory.md`](../features/memory.md)

### Skills

Skill 把針對特定任務的指引與腳本打包起來，讓 Agent 只在任務需要時，才
載入正確的操作指示。

延伸閱讀：[`features/skills.md`](../features/skills.md)

### 壓縮與快取延續性

長時間的工作階段可以壓縮舊有的 context、保留近期的任務狀態，並回報壓縮
生命週期事件。

延伸閱讀：[`features/compaction-and-cache.md`](../features/compaction-and-cache.md)

### 工作階段與持久化 Agent

工作階段會保留對話的延續性、匯出功能，以及執行中任務的控制。持久化
Agent 則為週期性的工作流程，提供具名身分與預設值。

延伸閱讀：[`sessions.md`](./sessions.md) 與 [`agents.md`](./agents.md)

### 使用量、診斷與權限

使用量報告會說明近期的模型花費。診斷與重播功能，有助於在回合執行後進行
檢視。權限與核准控制項，則能讓工具存取權限與任務相符。

延伸閱讀：[`usage-and-cost.md`](./usage-and-cost.md)、
[`diagnostics-and-replay.md`](../diagnostics-and-replay.md)，與
[`approvals-and-permissions.md`](./approvals-and-permissions.md)

## 核心 Runtime 能力

- 橫跨 Web UI、CLI 與頻道的統一 `TurnRunner` 路徑。
- 針對相容 OpenAI 的 API、Anthropic、Ollama，以及其他已設定後端的
  provider 抽象層。
- 串流回應、工具呼叫、重試、核准、artifact，以及最終使用量結算。
- 具備逐字稿、摘要、context 狀態與重播支援的持久化工作階段儲存。
- 每個 Agent 專屬的工作區，以及持久化的 Agent 項目。
- 支援子 Agent，用於有限範圍的委派。

## 工具

OpenSquilla 內建以下用途的工具：

- 檔案系統的讀取／寫入／編輯／列出／glob／grep。
- Shell 指令、背景行程，以及程式碼執行。
- Git 的 status、diff、log 與 commit。
- 網路搜尋與網頁擷取。
- 記憶的搜尋／儲存／取得／刪除。
- 工作階段搜尋，以及工作階段的衍生／傳送／歷史／狀態。
- Artifact 發佈。
- 影像生成、PDF、TTS，以及媒體工作流程。
- 透過內建的 skill，撰寫試算表、PPTX、DOCX、CSV 與 PDF。
- Feishu／Lark 的文件、聊天、雲端硬碟、wiki、權限，以及媒體上傳。
- Cron 與 gateway 管理。
- Skill 的列出、檢視、建立、編輯、安裝依賴套件，以及 meta-skill 呼叫。

延伸閱讀：[`tools-and-sandbox.md`](./tools-and-sandbox.md)

## Skills

內建、面向使用者的 skill 包括：

- `deep-research`
- `summarize`
- `memory`
- `cron`
- `github`
- `docx`
- `pptx`
- `xlsx`
- `pdf-toolkit`
- `html-to-pdf`
- `multi-search-engine`
- `weather`
- `tmux`
- `sub-agent`
- `skill-creator`

保留的內建 MetaSkill 包括 `meta-kid-project-planner`、
`meta-paper-write`、`meta-short-drama`，與 `meta-skill-creator`。開發
分支中可能存在實驗性的 MetaSkill，但它們不會被視為穩定的內建產品能力。

延伸閱讀：[`features/skills.md`](../features/skills.md)

## 排程

`cron` 指令群組用於管理 OpenSquilla 的排程執行：

```sh
opensquilla cron list
opensquilla cron add \
  --every 1h \
  --text "Summarize important project updates" \
  --name hourly-project-check
opensquilla cron status <job-id>
opensquilla cron run <job-id>
opensquilla cron runs <job-id>
```

排程工作可以依照設定，透過頻道或 webhook 等已設定的介面傳送工作內容。

延伸閱讀：[`scheduling.md`](../scheduling.md)

## 遷移

OpenSquilla 可以從 OpenClaw 與 Hermes Agent 匯入相容的狀態，也可以把完整
支援的 CLI／桌面版 profile，或歷史的 Windows Portable 資料，複製進另一個
獨立擁有的 OpenSquilla profile：

```sh
opensquilla migrate openclaw --json
opensquilla migrate openclaw --apply
opensquilla migrate hermes --json
opensquilla migrate hermes --apply
opensquilla migrate opensquilla --source PATH --json
opensquilla migrate opensquilla --source PATH --apply
```

同產品之間的匯入，一律需要明確指定來源。已有內容的目標，絕不會被合併：
只能選擇保留，或完整備份後整個取代。

延伸閱讀：[`../../MIGRATION.md`](../../MIGRATION.md)。

---

[說明索引](./README.md) · [產品指南](../../README.product.zh-Hant.md) ·
[改善這個頁面](../contributing-docs.md) ·
[回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
