<!-- 譯自 ../glossary.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/glossary.md -->

# 詞彙表

> 本文件譯自 [`glossary.md`](../glossary.md)，內容以英文版為準。

本詞彙表以使用者可理解的語言，定義 OpenSquilla 的常用術語，並非執行期
設計文件。

## Agent

具名的 OpenSquilla 身分，具備模型、工作區、名稱與描述等預設值。內建的
`main` agent 一律可用。

詳見：[`agents.md`](./agents.md)

## Artifact

由一次執行所產生的檔案或媒體輸出，例如 HTML 頁面、報告、影像、試算表、
PDF 或投影片。

詳見：[`artifacts-and-media.md`](../artifacts-and-media.md)

## 核准

在敏感的工具動作繼續執行之前，所需要的人工決策。核准行為取決於介面、
權限設定檔，以及工具政策。

詳見：[`approvals-and-permissions.md`](./approvals-and-permissions.md)

## 頻道

訊息平台整合，例如 Telegram、Slack、Feishu／Lark、Discord、DingTalk、
WeCom、Matrix、終端機，或 websocket 類型的用戶端。

詳見：[`channels.md`](./channels.md)

## 壓縮

在長時間的工作階段中，縮減舊有 context 的處理過程，讓 agent 可以在模型
的 context 預算內繼續運作。

詳見：[`features/compaction-and-cache.md`](../features/compaction-and-cache.md)

## 診斷

用來瞭解路由、provider 行為、壓縮、工具壓縮、快取行為，以及傳送失敗
狀況的執行期日誌控制項。

詳見：[`diagnostics-and-replay.md`](../diagnostics-and-replay.md)

## Gateway

支援 Web UI、頻道、工作階段、核准、診斷、用量，以及 RPC 用戶端的本地端
伺服器。

詳見：[`gateway.md`](./gateway.md)

## 記憶

持久保存的使用者或專案 context，可供之後搜尋與回想，不需要把每一份舊有
逐字稿都塞進目前使用中的提示詞。

詳見：[`features/memory.md`](../features/memory.md)

## MetaSkill

可重複使用、可稽核的工作流程協定，能將多個 skill、工具、LLM 呼叫、檢查
或輸出步驟，組合成一項可重複執行的能力。

詳見：[`features/meta-skills.md`](../features/meta-skills.md) 與
[`features/meta-skill-user-guide.md`](../features/meta-skill-user-guide.md)

## 權限設定檔

為某次執行所選定的工具存取狀態，例如 `restricted`、`on`、`bypass` 或
`full`。

詳見：[`approvals-and-permissions.md`](./approvals-and-permissions.md)

## Provider

為 OpenSquilla 設定的 LLM 後端，例如 TokenRhythm、OpenRouter、OpenAI、
Anthropic、Gemini、DeepSeek、DashScope 或 Ollama。

詳見：[`providers-and-models.md`](./providers-and-models.md)

## 重播

從決策日誌中，以唯讀方式檢視某個已記錄回合的內容。重播不會重新執行
工具。

詳見：[`diagnostics-and-replay.md`](../diagnostics-and-replay.md)

## 排程器

`opensquilla cron` 功能，用於執行週期性與單次的 OpenSquilla 工作。

詳見：[`scheduling.md`](../scheduling.md)

## 工作階段

持久保存的對話或任務歷史紀錄。工作階段可以被列出、繼續、匯出、中止或
刪除。

詳見：[`sessions.md`](./sessions.md)

## Skill

可重複使用的套件，內含針對特定任務的指引、腳本或工作流程指示，
OpenSquilla 可在需要時載入。

詳見：[`features/skills.md`](../features/skills.md)

## SquillaRouter

OpenSquilla 的本地端路由層，用來為每一個回合選擇合適的模型層級。

詳見：[`features/squilla-router.md`](../features/squilla-router.md)

## 工具壓縮

一種節省 context 的功能，能在將較小的預覽內容送給模型的同時，仍保留
大型工具結果的可用性。

詳見：[`features/tool-compression.md`](../features/tool-compression.md)

## 工作區

允許或預期任務在其中工作的本地端目錄。工作區旗標有助於限制檔案與 shell
相關工作的範圍。

詳見：[`tools-and-sandbox.md`](./tools-and-sandbox.md)

---

[文件索引](./README.md) · [產品指南](../../README.product.zh-Hant.md) · [改善本頁](../contributing-docs.md) · [回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
