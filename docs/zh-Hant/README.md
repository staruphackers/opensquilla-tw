<!-- 譯自 docs/README.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/README.md -->

# OpenSquilla 文件

> 本文件譯自 [`README.md`](../README.md)，內容以英文版為準。

本目錄是面向使用者的產品文件集，作為根目錄發佈版 README 的補充，提供以任務為
導向的指南。

## 先讀這些

1. [`quickstart.md`](./quickstart.md) — 安裝、設定、執行，並開啟 Web UI。
2. [`use-cases.md`](../use-cases.md) — 針對常見目標的任務導向操作範例。（英文）
3. [`gateway.md`](./gateway.md) — gateway 生命週期、host／port、安全性與狀態。
4. [`configuration.md`](./configuration.md) — provider、router、搜尋、頻道、
   記憶與權限設定。
5. [`cli.md`](./cli.md) — 指令群組與常見 CLI 工作流程。
6. [`tui.md`](../tui.md) — 終端機聊天用法、斜線指令、檔案、工作階段，以及
   OpenTUI 預覽版。（英文）
7. [`web-ui.md`](./web-ui.md) — 本地端控制台與聊天 UI。
8. [`sessions.md`](./sessions.md) — 工作階段的延續性、匯出、繼續、中止與
   清理。
9. [`glossary.md`](./glossary.md) — 面向使用者的術語說明。

## 功能指南

- [`features.md`](./features.md) — 能力目錄。
- [`features/squilla-router.md`](../features/squilla-router.md) —
  模型路由。（英文）
- [`features/tui-frontend.md`](../features/tui-frontend.md) — 終端機後端
  架構、外掛插槽、Router HUD，以及 OpenTUI 評估。（英文）
- [`features/tool-compression.md`](../features/tool-compression.md) —
  精簡的工具結果與 handle。（英文）
- [`features/meta-skills.md`](../features/meta-skills.md) — 可重複使用的
  工作流程 skill。（英文）
- [`features/meta-skill-user-guide.md`](../features/meta-skill-user-guide.md) -
  面向使用者的 MetaSkill 指南。（英文）
- [`authoring/meta-skills.md`](../authoring/meta-skills.md) — MetaSkill
  撰寫指南。（英文）
- [`features/memory.md`](../features/memory.md) — 持久化記憶與回想。
  （英文）
- [`features/skills.md`](../features/skills.md) — skill 探索、安裝與
  撰寫。（英文）
- [`features/compaction-and-cache.md`](../features/compaction-and-cache.md) -
  長工作階段的壓縮與提示詞快取延續性。（英文）

## 介面與維運

- [`releases/0.5.0rc3.md`](../releases/0.5.0rc3.md) — OpenSquilla 0.5.0
  Preview 3 發行說明。（英文）
- [`releases/0.5.0rc2.md`](../releases/0.5.0rc2.md) — OpenSquilla 0.5.0
  Preview 2 發行說明。（英文）
- [`releases/0.5.0rc1.md`](../releases/0.5.0rc1.md) — OpenSquilla 0.5.0
  Preview 1 發行說明。（英文）
- [`releases/0.4.1.md`](../releases/0.4.1.md) — OpenSquilla 0.4.1
  發行說明。（英文）
- [`releases/0.4.0.md`](../releases/0.4.0.md) — OpenSquilla 0.4.0
  發行說明。（英文）
- [`releases/0.3.0.md`](../releases/0.3.0.md) — OpenSquilla 0.3.0
  發行說明。（英文）
- [`channels.md`](./channels.md) — 支援的訊息頻道與設定流程。
- [`providers-and-models.md`](./providers-and-models.md) — LLM provider
  目錄、模型選擇，以及以 runtime 為基礎的模型檢視。
- [`search.md`](../search.md) — 網路搜尋 provider 與查詢工作流程。
  （英文）
- [`artifacts-and-media.md`](../artifacts-and-media.md) — artifact、
  生成的檔案、圖片、PDF 與 TTS。（英文）
- [`tools-and-sandbox.md`](./tools-and-sandbox.md) — 內建工具、核准、
  sandbox 狀態，以及寫入政策。
- [`approvals-and-permissions.md`](./approvals-and-permissions.md) —
  權限 profile、核准指令、工作區侷限範圍，以及 sandbox 狀態。
- [`agents.md`](./agents.md) — 持久化的具名 Agent 與工作區預設值。
- [`scheduling.md`](../scheduling.md) — 週期性與一次性的排程工作。
  （英文）
- [`mcp-server.md`](./mcp-server.md) — 給支援 MCP 的客戶端使用的
  MCP server 橋接。
- [`usage-and-cost.md`](./usage-and-cost.md) — token 使用量、預估成本，
  以及成本調查工作流程。
- [`diagnostics-and-replay.md`](../diagnostics-and-replay.md) — 診斷、
  原始擷取指引、唯讀回合重播，以及開發者重播基準測試。（英文）
- [`tui-real-terminal-harness.md`](../tui-real-terminal-harness.md) —
  維護者用的真實終端機 TUI 整合測試工具與證據擷取。（英文）
- [`experiments.md`](../experiments.md) — 選擇加入的 runtime 開關慣例，
  以及 `scripts/experiments/` 中的交付驗證工具。（英文）
- [`docker.md`](../docker.md) — 在家用伺服器與 NAS 上部署
  Docker／Compose：預先建置好的 GHCR 映像檔、透過 token 驗證對外開放
  LAN，以及升級方式。（英文）
- [`operations.md`](../operations.md) — 工作階段、cron、使用量、診斷、
  遷移、MCP server，以及安裝清點指令。（英文）
- [`troubleshooting.md`](./troubleshooting.md) — 常見的安裝／runtime
  問題。
- [`glossary.md`](./glossary.md) — 產品術語的簡短定義。

## 改善這些文件

歡迎協助改善文件。請先參考 [`contributing-docs.md`](../contributing-docs.md)
瞭解文件相關的具體指引，接著針對 `main` 分支開一個小型 pull request。

快速路徑：

- 使用[文件問題範本](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
  回報過時的指令、失效連結，或難以理解的頁面。
- 在 GitHub 上編輯受影響的 Markdown 頁面，並針對 `main` 分支開一個聚焦明確的
  pull request。
- 針對新功能的文件，請將各自獨立的功能放在 `docs/features/` 底下各自獨立的
  頁面中。

## 設計原則

OpenSquilla 的文件應該先幫助使用者把產品跑起來，接著再理解它的特殊優勢。著重
機制細節的 runtime 內容，應該放在開發者設計筆記或原始碼註解中，而不是放在
初次執行的路徑裡。

---

[產品指南](../../README.product.md) · [中文](../../README.zh-Hans.md) ·
[繁體中文](../../README.zh-Hant.md) · [日本語](../../README.ja.md) ·
[Français](../../README.fr.md) · [Deutsch](../../README.de.md) ·
[Español](../../README.es.md) · [改善這些文件](../contributing-docs.md) ·
[回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml) ·
[貢獻指南](../../CONTRIBUTING.md)
