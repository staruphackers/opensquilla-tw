<!-- 譯自 README.product.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- README.product.md -->

# OpenSquilla 產品指南

> 本文件譯自 [`README.product.md`](README.product.md)，內容以英文版為準。

OpenSquilla 是一個高效運用 token 的個人 Agent runtime，適用於終端機、本地端
Web UI，以及訊息頻道。它的設計目標，是讓使用者擁有單一 Agent 介面，就能
聊天、使用工具、記住有用的 context、執行排程工作、發佈 artifact，並在多個
LLM provider 之間路由工作，而不必為了每個 provider 重寫工作流程。

本指南是產品與使用面的入口。既有的 [`README.md`](README.zh-Hant.md) 依然是
套件／發布版 README。

## 從這裡開始

1. 安裝 OpenSquilla：

   ```sh
   uv tool install --python 3.12 "opensquilla[recommended] @ https://github.com/opensquilla/opensquilla/releases/download/v0.5.0rc3/opensquilla-0.5.0rc3-py3-none-any.whl"
   ```

2. 設定你的 provider：

   ```sh
   opensquilla onboard
   ```

3. 啟動 gateway：

   ```sh
   opensquilla gateway run
   ```

4. 開啟控制 UI：

   <http://127.0.0.1:18791/control/>

關於各平台專屬的安裝路徑與復原步驟，請見
[`docs/quickstart.md`](docs/zh-Hant/quickstart.md)。

## 為什麼選擇 OpenSquilla

OpenSquilla 著重的是每次成功任務的成本，以及長時間執行的實用性，而不只是
單一回合的聊天。

| 產品能力 | 使用者能獲得什麼 |
| --- | --- |
| SquillaRouter | 本地端、裝置端的路由功能，會針對每個回合選擇合適的模型層級，讓簡單的任務不必負擔高階模型的成本。 |
| 工具壓縮 | 大型工具輸出依然保持有用，卻不會塞爆模型的 context；原始結果可以被保留，同時把精簡的預覽送給模型。 |
| Meta-skills | 可重複的工作流程能夠打包成可組合的 skill，讓使用者能把週期性的多步驟工作，變成可重複使用的 Agent 例行程序。 |
| 統一介面 | CLI、Web UI、gateway RPC 與頻道，共用同一個 runtime 路徑、工具、記憶、核准，以及使用量結算。 |
| 持久化工作階段 | 對話、逐字稿、壓縮摘要、artifact、成本與重播資料，都會被保存下來供之後檢視。 |
| 個人記憶 | 使用者事實、筆記與任務軌跡，可以透過本地端關鍵字與語意搜尋來儲存與回想。 |
| 多 provider runtime | OpenRouter、OpenAI、Anthropic、Gemini、DeepSeek、DashScope、Ollama，以及其他相容 provider 的後端，都能透過同一份 schema 設定。 |
| 安全的工具使用 | 檔案、shell、網路、記憶、git、artifact、媒體、頻道與 Agent 工具，都在政策層與核准介面之後執行。 |

## 文件導覽地圖

| 需求 | 請讀 |
| --- | --- |
| 安裝並執行 OpenSquilla | [`docs/quickstart.md`](docs/zh-Hant/quickstart.md) |
| 針對目標選擇合適的工作流程 | [`docs/use-cases.md`](docs/use-cases.md)（英文） |
| 啟動、停止、對外開放，或排除 gateway 的疑難雜症 | [`docs/gateway.md`](docs/zh-Hant/gateway.md) |
| 設定 provider、router、搜尋、頻道、記憶與權限 | [`docs/configuration.md`](docs/zh-Hant/configuration.md) |
| 瞭解 CLI 指令群組 | [`docs/cli.md`](docs/zh-Hant/cli.md) |
| 使用本地端控制台 | [`docs/web-ui.md`](docs/zh-Hant/web-ui.md) |
| 繼續、匯出、中止或刪除工作階段 | [`docs/sessions.md`](docs/zh-Hant/sessions.md) |
| 選擇並檢視 LLM provider／模型 | [`docs/providers-and-models.md`](docs/zh-Hant/providers-and-models.md) |
| 設定網路搜尋 | [`docs/search.md`](docs/search.md)（英文） |
| 瞭解主要的產品能力 | [`docs/features.md`](docs/zh-Hant/features.md) |
| 使用 SquillaRouter | [`docs/features/squilla-router.md`](docs/features/squilla-router.md)（英文） |
| 瞭解工具壓縮與工具結果 handle | [`docs/features/tool-compression.md`](docs/features/tool-compression.md)（英文） |
| 使用 MetaSkill | [`docs/features/meta-skills.md`](docs/features/meta-skills.md)（英文） |
| 使用記憶功能 | [`docs/features/memory.md`](docs/features/memory.md)（英文） |
| 使用 skill | [`docs/features/skills.md`](docs/features/skills.md)（英文） |
| 瞭解壓縮、快取與長工作階段延續性 | [`docs/features/compaction-and-cache.md`](docs/features/compaction-and-cache.md)（英文） |
| 發佈 artifact 並使用媒體功能 | [`docs/artifacts-and-media.md`](docs/artifacts-and-media.md)（英文） |
| 連接聊天頻道 | [`docs/channels.md`](docs/zh-Hant/channels.md) |
| 建立持久化的具名 Agent | [`docs/agents.md`](docs/zh-Hant/agents.md) |
| 排程週期性或一次性的工作 | [`docs/scheduling.md`](docs/scheduling.md)（英文） |
| 瞭解工具、sandbox 與核准 | [`docs/tools-and-sandbox.md`](docs/zh-Hant/tools-and-sandbox.md) |
| 選擇權限與核准狀態 | [`docs/approvals-and-permissions.md`](docs/zh-Hant/approvals-and-permissions.md) |
| 檢視使用量與模型成本 | [`docs/usage-and-cost.md`](docs/zh-Hant/usage-and-cost.md) |
| 診斷並重播回合 | [`docs/diagnostics-and-replay.md`](docs/diagnostics-and-replay.md)（英文） |
| 連接支援 MCP 的客戶端 | [`docs/mcp-server.md`](docs/zh-Hant/mcp-server.md) |
| 執行工作階段、cron、診斷、遷移與 MCP 維運操作 | [`docs/operations.md`](docs/operations.md)（英文） |
| 修正常見的安裝／runtime 問題 | [`docs/troubleshooting.md`](docs/zh-Hant/troubleshooting.md) |
| 瞭解 OpenSquilla 術語 | [`docs/glossary.md`](docs/zh-Hant/glossary.md) |

## 最快上手的工作流程

gateway 執行之後，請依照工作內容選擇合適的介面：

```sh
opensquilla chat
```

這適合互動式的終端機工作。

```sh
opensquilla agent -m "Summarize this repo and tell me what to test"
```

這適合一次性的自動化工作。

```sh
opensquilla gateway start --json
```

這適合背景執行的 Web UI、頻道與 RPC 客戶端。

```sh
opensquilla sessions list
opensquilla cost
opensquilla doctor
```

這些指令可用於檢視歷史紀錄、成本與就緒狀態。

## 設定要點

OpenSquilla 會依照以下順序載入設定：

1. `OPENSQUILLA_GATEWAY_CONFIG_PATH`
2. `./opensquilla.toml`
3. `~/.opensquilla/config.toml`
4. 內建預設值

日常變更請使用 CLI：

```sh
opensquilla onboard --if-needed
opensquilla configure provider --provider openrouter --api-key-env OPENROUTER_API_KEY
opensquilla configure router --router recommended
opensquilla configure search --search-provider duckduckgo
opensquilla configure search --search-provider tavily --api-key-env TAVILY_API_KEY
opensquilla configure channels
opensquilla config get llm.provider
opensquilla config set gateway.port 18791
```

詳情請見 [`docs/configuration.md`](docs/zh-Hant/configuration.md)。

## 功能亮點

### SquillaRouter

SquillaRouter 是 OpenSquilla 的本地端路由層。它會把輕量的任務保留給比較
便宜的模型，並把更強的層級留給較困難的回合。路由決策留在本地端進行；
使用者的提示詞不會只為了決定模型，就被送往另一個外部分類器。

延伸閱讀：[`docs/features/squilla-router.md`](docs/features/squilla-router.md)
（英文）

### 工具壓縮

Agent 的工作經常會產生龐大的工具結果：日誌、網頁、搜尋結果、試算表、
diff 與 JSON。OpenSquilla 可以保留原始結果，同時投射出精簡、模型可見的
預覽，在不丟棄使用者工作狀態的前提下，降低 context 壓力。

延伸閱讀：[`docs/features/tool-compression.md`](docs/features/tool-compression.md)
（英文）

### Meta-Skills

Meta-skill 讓 OpenSquilla 能夠呈現更高層次的工作流程，使用者不必重複
描述同一套多步驟流程。它適合用在可重複的研究報告、從文件到決策的工作、
每日營運簡報、帳號監看、求職準備、兒童專案規劃、學術論文草擬，以及
MetaSkill 提案的建立。

預設情況下，會以 `/meta` 與 `/meta <name>` 有意識地啟動它們。

延伸閱讀：[`docs/features/meta-skills.md`](docs/features/meta-skills.md)、
[`docs/features/meta-skill-user-guide.md`](docs/features/meta-skill-user-guide.md)，
與 [`docs/authoring/meta-skills.md`](docs/authoring/meta-skills.md)（皆為英文）

## OpenSquilla 能做什麼

- 從 Web UI、CLI、gateway RPC、終端機頻道，以及支援的訊息平台執行聊天。
- 使用工具處理檔案、shell 指令、程式碼執行、git、網路搜尋／擷取、記憶、
  工作階段、artifact、媒體、Feishu、排程工作與子 Agent。
- 安裝、檢視、發佈與組合 skill。
- 使用 `opensquilla cron` 排程週期性執行。
- 儲存持久化記憶，並搜尋先前的工作階段。
- 使用 `opensquilla cost` 追蹤使用量與預估成本。
- 使用 `opensquilla doctor` 與 `/control/` 健康狀況檢視，診斷就緒狀態。
- 使用 `opensquilla dist` 匯出可重現的安裝狀態。
- 使用 `opensquilla uninstall` 乾淨地移除 OpenSquilla——除非你加上
  `--purge-state`／`--purge-config`／`--purge-all`，否則會保留你的資料。
- 在安裝了 `mcp` extra 的情況下，使用 `opensquilla mcp-server run` 把
  OpenSquilla 橋接進支援 MCP 的客戶端。
- 建立並傳送 artifact，例如 HTML 檔案、PDF 報告、投影片、試算表、生成的
  圖片，以及透過頻道傳送的檔案。

## 安全預設值

gateway 預設綁定在 `127.0.0.1`。綁定到公開介面需要主動選用：

```sh
opensquilla gateway run --listen 0.0.0.0 --port 18791
```

沒有 token 驗證與你所信任的網路邊界時，請勿對外開放公開的 gateway。關於
工具行為、核准流程與工作區侷限範圍，請見
[`docs/tools-and-sandbox.md`](docs/zh-Hant/tools-and-sandbox.md)。

## 既有參考文件

- [`README.md`](README.zh-Hant.md) — 發布版／套件 README
- [`MIGRATION.md`](MIGRATION.md) — 從 OpenClaw 與 Hermes Agent 遷移（英文）
- [`docs/features/meta-skill-user-guide.md`](docs/features/meta-skill-user-guide.md) —
  MetaSkill 使用者指南（英文）
- [`docs/authoring/meta-skills.md`](docs/authoring/meta-skills.md) —
  MetaSkill 撰寫指南（英文）
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — 貢獻者工作流程（英文）
- [`CHANGELOG.md`](CHANGELOG.md) — 發行歷史（英文）

## 改善這份文件

OpenSquilla 的文件是產品的一部分。如果某個設定步驟令人困惑、某個指令已經
過時，或某份功能指南需要更清楚的範例，請針對 `main` 分支開一個小型
pull request。既有的 `dev` pull request，在分支轉換期間可以繼續進行。

請閱讀 [`docs/contributing-docs.md`](docs/contributing-docs.md) 瞭解文件
相關的具體指引。（英文）

---

[說明索引](docs/zh-Hant/README.md) ·
[改善這些文件](docs/contributing-docs.md) ·
[回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml) ·
[貢獻指南](CONTRIBUTING.md)
