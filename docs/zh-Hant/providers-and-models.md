<!-- 譯自 ../providers-and-models.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/providers-and-models.md -->

# 供應商與模型

> 本文件譯自 [`providers-and-models.md`](../providers-and-models.md)，內容以英文版為準。

OpenSquilla 透過單一設定介面支援多個 LLM 供應商。你可以執行直連單一模型
模式，也可以啟用 SquillaRouter 進行分層路由。

當你需要設定供應商、檢視模型支援情況，或是在直連模型模式與路由模式之間
做選擇時，可參考本頁內容。

## 檢視供應商

列出本機安裝環境中的供應商中繼資料：

```sh
opensquilla providers list
opensquilla providers list --json
```

顯示執行中閘道器的執行期供應商診斷資訊：

```sh
opensquilla providers status
opensquilla providers status openrouter --json
opensquilla providers status --probe-models
```

`providers list` 不需要閘道器正在執行；`providers status` 則需要。

## 設定供應商

互動模式：

```sh
opensquilla providers configure openrouter
```

非互動、入門引導風格的設定：

```sh
export OPENROUTER_API_KEY="sk-..."
opensquilla configure provider --provider openrouter --api-key-env OPENROUTER_API_KEY
```

直連供應商範例：

```sh
opensquilla configure provider --provider openai --model gpt-5.4-mini --api-key-env OPENAI_API_KEY
opensquilla configure provider --provider anthropic --model claude-sonnet-4-5 --api-key-env ANTHROPIC_API_KEY
opensquilla configure provider --provider gemini --model gemini-2.5-flash --api-key-env GEMINI_API_KEY
opensquilla configure provider --provider ollama --model llama3.1
```

API 金鑰建議以環境變數參照的方式提供，避免機密資訊直接寫入設定檔。

### 端點（base URL）解析

`llm.base_url` 會依照**明確設定 → 推導出的環境變數 → 供應商預設值**的
順序解析：

- 你儲存的自訂端點（Web UI 進階選項、`config.set`，或手動寫在 TOML 中的
  `base_url`）永遠優先。
- 如果設定從未選擇過端點——沒有 `base_url`，或該欄位仍是供應商自己的
  預設 URL——則會套用推導出的環境變數（`OPENAI_BASE_URL`、
  `OPENROUTER_BASE_URL`、`<PROVIDER>_BASE_URL`）。這正是能把整批部署一次
  指向企業代理伺服器，而不必逐一修改設定檔的做法。
- `OPENSQUILLA_LLM_BASE_URL` 會在設定模型建構階段（`OPENSQUILLA_LLM_*`
  設定層）介入：只要 TOML 沒有設定 `base_url`，它就會填入該值，解析器
  接著會把它視為一個明確值——因此它會勝過上述由供應商推導出的環境變數，
  但 TOML 中寫明的 `base_url` 仍然優先於它。

API 金鑰透過 `api_key` / `api_key_env` 遵循相同的「明確設定優先」規則。

## 已通過入門引導驗證的供應商

此版本提供以下供應商的入門引導支援：

- TokenRhythm
- OpenRouter
- OpenAI
- Anthropic
- Ollama
- DeepSeek
- Gemini
- DashScope / Qwen
- Moonshot AI
- Zhipu / Z.AI
- Baidu Qianfan
- Volcengine Ark

供應商登記中可能還包含其他相容供應商，供進階或自架部署使用。請在你的
安裝環境執行 `opensquilla providers list`，檢視目前的目錄內容。

### OpenAI：`openai` vs `openai_responses`

OpenAI 以兩個供應商 id 對外提供，兩者共用相同的 `OPENAI_API_KEY` 與
base URL（`https://api.openai.com/v1`）：

- `openai` — chat/completions 請求格式。適用於標準的聊天式對話輪次，並
  具有廣泛的工具相容性。
- `openai_responses` — 原生 Responses API 格式（具備 `chat` 與 `responses`
  能力）。當你想要 Responses API 的行為，而非 chat/completions 介面時，
  可使用此選項。

兩者讀取相同的金鑰與 base URL，因此只需變更 `provider` 即可切換。

### Volcengine Ark：一般版與 coding-plan 端點

一般的 Ark chat/completions 模型請使用 `volcengine`。其預設 base URL 是
相容 OpenAI 的端點 `https://ark.cn-beijing.volces.com/api/v3`。

Volcengine 相容 OpenAI Responses 的 coding-plan 訂閱介面，請使用
`volcengine_coding_plan`。其預設 base URL 為
`https://ark.cn-beijing.volces.com/api/coding/v3`；OpenSquilla 送出請求時
會附加 `/responses`。

```sh
export VOLCENGINE_API_KEY="..."
opensquilla configure provider --provider volcengine_coding_plan --model <model> --api-key-env VOLCENGINE_API_KEY
```

若工具或部署環境需要 Anthropic Messages 協定，請使用
`volcengine_coding_plan_anthropic`。其預設 base URL 為
`https://ark.cn-beijing.volces.com/api/coding`；OpenSquilla 會附加
`/v1/messages`。

```sh
export VOLCENGINE_API_KEY="..."
opensquilla configure provider --provider volcengine_coding_plan_anthropic --model <model> --api-key-env VOLCENGINE_API_KEY
```

請勿把任何一個 coding-plan 供應商指向一般的 `/api/v3` URL。該一般 Ark
URL 不會消耗 Coding Plan 配額。

### Tencent TokenHub：中國大陸、Anthropic 協定與國際端點

騰訊混元的 `hy3` / `hy3-preview` 模型是在 TokenHub 平台上提供服務（舊有的
`api.hunyuan.cloud.tencent.com` 平台正在被淘汰，且從未支援過 `hy3`）。
三個實驗性的供應商 id 對應到官方文件記載的端點：

- `tencent_tokenhub` — 相容 OpenAI 的 chat/completions，位於
  `https://tokenhub.tencentmaas.com/v1`（中國大陸；金鑰來自中國大陸
  TokenHub 控制台，`TENCENT_TOKENHUB_API_KEY`）。`hy3` 的思考功能使用
  `reasoning_effort` 的 `low` / `high`，且 assistant 的 `reasoning_content`
  會依照 hy3 交錯思考（interleaved-thinking）協定的要求，跨輪次重播。
- `tencent_tokenhub_anthropic` — 同一部署的 Anthropic Messages 協定
  （`https://tokenhub.tencentmaas.com` + `/v1/messages`，`x-api-key`
  驗證，使用相同金鑰）。
- `tencent_tokenhub_intl` — 國際部署，位於
  `https://tokenhub-intl.tencentcloudmaas.com/v1`
  （`TENCENT_TOKENHUB_INTL_API_KEY`）。這是獨立的騰訊雲帳戶與金鑰系統，
  其模型清單目前含有第三方模型（DeepSeek、GLM、Kimi、MiniMax），但不含
  `hy3`。

```sh
export TENCENT_TOKENHUB_API_KEY="..."
opensquilla configure provider --provider tencent_tokenhub --model hy3 --api-key-env TENCENT_TOKENHUB_API_KEY
```

TokenHub 也在相同端點背後提供第三方模型；OpenSquilla 不會為這些 id 注入
思考酬載，因為 TokenHub 並未在此閘道器上記載它們的方言（dialect）。

騰訊的 Token Plan 訂閱方案（Hy Token Plan 含 `hy3` / `hy3-preview`；
General 方案則在同一把金鑰下額外提供 `tc-code-latest`、DeepSeek V4、
GLM-5.x、Kimi 與 MiniMax 等 id）以另外兩個供應商 id 的形式，在方案主機
上提供：

- `tencent_token_plan` — Chat Completions，位於
  `https://api.lkeap.cloud.tencent.com/plan/v3`（方案端點不提供
  Responses API）。
- `tencent_token_plan_anthropic` — Anthropic Messages，位於
  `https://api.lkeap.cloud.tencent.com/plan/anthropic`
  （+ `/v1/messages`），使用 bearer 驗證。

兩者都讀取 `TENCENT_TOKEN_PLAN_API_KEY`。方案金鑰是在 TokenHub Token
Plan 控制台頁面建立的專屬 `sk-tp-…` 憑證——不能與按量計費的 TokenHub
金鑰互換。請注意，騰訊的方案條款將這些金鑰限制在互動式 AI 工具使用，
並禁止非互動的批次／自動化呼叫；無人值守的管線應改用按量計費的
`tencent_tokenhub` 供應商。這些方案僅限中國大陸地區使用——國際站僅提供
按量計費的 TokenHub。

## 模型檢視

列出模型：

```sh
opensquilla models list
```

如果依賴執行期的模型檢視功能無法連線，請啟動閘道器：

```sh
opensquilla gateway run
```

若是不需要閘道器的供應商中繼資料，請使用：

```sh
opensquilla providers list
```

### 上下文視窗解析順序

上下文預算、壓縮閾值、用量壓力回報，以及路由器的能力資訊，都是透過相同
的層級來解析模型的上下文視窗，第一個相符者勝出：

1. **逐模型覆寫** — 設定中的 `[models.<provider_id>."<model_id>"]`
   `context_window`。適用於目錄未收錄的模型（直連 DashScope／TokenHub
   的 id、自架 vLLM 宣告的實際視窗），或用來修正錯誤的目錄值。回報時
   來源標示為 `override`（`config.effective` 中為 `config`，用量上下文
   狀態中為 `model_override`）。
2. **全域覆寫** — `llm.context_window_tokens`（0 = 自動）。這是套用到
   目前啟用中任何模型的粗略手段；逐模型覆寫永遠優先於它。
3. **模型目錄** — 即時 OpenRouter 資料、內建的 models.dev 快照，再來是
   封裝內建的修正值。
4. **預設值** — 本機執行時保守設為 8,192（請用覆寫值配合你實際的
   `num_ctx`／伺服器視窗），其他情況為 200,000。

Web UI 會在「設定 → 聊天模型 → 進階」中提供逐模型覆寫功能，並顯示自動
偵測值／覆寫值／生效值的讀數。

## 直連模型與路由的比較

直連模型模式：

```sh
opensquilla configure router --router disabled
opensquilla configure provider --provider openai --model gpt-5.4-mini --api-key-env OPENAI_API_KEY
```

路由模式：

```sh
opensquilla configure router --router recommended
```

| 模式 | 適用時機 |
| --- | --- |
| 直連模型 | 你正在測試單一確切模型、重現供應商行為，或稽核供應商帳單。 |
| 路由模式 | 你想要一般個人 Agent 的日常使用方式，讓成本與任務複雜度依每輪對話變化。 |

路由詳情請參閱
[`features/squilla-router.md`](../features/squilla-router.md)。

## 定價與成本估算

當供應商回傳真實的計費成本時，OpenSquilla 會回報該實際數字；在其他所有
情況下，則會依據 token 用量在本機端進行估算。每一列用量資料與每一項
按模型分類的明細，都會加上標籤，讓你能分辨自己看到的是哪一種數字。

### 成本如何被估算

每一次計價的呼叫，都會被拆分成四個 token 桶——全新輸入、快取讀取、快取
寫入、輸出——每個桶都以各自的費率計價。結果會帶有一個 `basis` 標籤：

| Basis | 意義 |
| --- | --- |
| `cache_aware` | 該次呼叫中出現的所有桶，費率皆為已知；四桶運算已完整執行。 |
| `cache_blind` | 該次呼叫使用了快取 token，但所需的快取費率未知，因此 OpenSquilla 退回以一般輸入費率，為每一個輸入 token（不論快取或全新）計價。這是保守的上限值，不是實際費用——在大量使用快取的工作階段中，預期會高估成本。 |
| `free` | 該模型或執行環境為零費用（見下方本機執行環境說明）。 |

### 價格解析順序

針對給定的 `(model, provider)` 組合，OpenSquilla 會依照下列層級解析
價格，第一個相符者勝出：

1. **本機執行環境** — `ollama`、`lm_studio`、`ovms`、`vllm` 與 `local`
   永遠免費，與模型 id 無關。
2. **使用者覆寫** — 設定中的 `[models.<provider_id>."<model_id>"]`
   （見 [`configuration.md`](./configuration.md) 與
   `opensquilla.toml.example`）。
3. **模型目錄** — 內建的 models.dev 快照，包含上游有公布時的逐模型
   快取讀取／快取寫入費率。
4. **即時 OpenRouter 端點價格** — 只有在供應商為 `openrouter` 或未指定
   時才會查詢（第一方供應商 id 絕不會查詢 OpenRouter 市集）；若
   OpenRouter 無法連線，則退回靜態表。
5. **靜態表** — OpenSquilla 內建隨附的定價表。
6. **預設值** — 當以上皆未相符時，輸入／輸出 token 每百萬個為 `$3` /
   `$15`。

如果 OpenSquilla 對某個模型估算出錯誤的價格，請新增一筆覆寫設定，不必
等待目錄更新：

```toml
[models.openrouter."z-ai/glm-5.2"]
input_cost_per_mtok = 0.5        # USD per million input tokens
output_cost_per_mtok = 2.0       # USD per million output tokens
cache_read_cost_per_mtok = 0.05  # USD per million cached-prompt-read tokens
cache_write_cost_per_mtok = 0.6  # USD per million cached-prompt-write tokens
```

包含點號或斜線的模型 id 請加上引號。四個欄位皆為選填——只需設定你想
修正的欄位即可。`config.set` / `patch` / `apply` 與
`opensquilla gateway reload` 都能立即套用這些覆寫值；更多範例（包括
自架 `vllm` 與 `custom` 端點）請見 `opensquilla.toml.example`。

### 成本來源（`costSource`）

每一列用量資料與每一項按模型分類的明細，都帶有一個 `costSource`
（同時也以雙重命名方式提供 `cost_source`）：

| `costSource` | 意義 |
| --- | --- |
| `provider_billed` | 完整成本來自供應商回報的真實帳單。 |
| `opensquilla_estimate` | 沒有可用的計費成本；此數字為本機估算值。 |
| `mixed` | 彙總列中，同一個模型同時有已計費與未計費的呼叫——總額是計費成本加上其餘部分的估算值，不是純粹的帳單金額。 |
| `unavailable` | 沒有定價表條目，也沒有計費成本，因此無法產出金額數字。 |

資料列還帶有兩個附加欄位：`estimateBasis`（即上方的 `cache_aware` /
`cache_blind` / `free` 標籤，只有在該列部分內容是估算值時才會出現）與
`priceSource`（標示是哪一層解析器為其計價——`user_override`、
`catalog`、`live_openrouter`、`static_table`、`default`，或
`local_free`）。Web UI 的按模型用量卡片，會顯示 `costSource` 的小型
來源標籤；當底層 basis 為 `cache_blind` 時，還會提示該數字是上限值，
而非實際套用快取折扣後的費用。

### 哪些供應商提供計費成本、哪些提供估算成本

| 能力 | 供應商 |
| --- | --- |
| 供應商計費成本 | 僅 `openrouter` |
| 可產出快取感知估算 | `anthropic`、`deepseek`、`minimax`（Anthropic 格式）、聚合路由成員 |
| 僅能產出快取讀取感知估算（無快取寫入費率） | `openai`、`openai_responses`、`azure`、`gemini`、`openai_codex` |
| 快取盲估算（出現快取 token 時退回一般輸入費率計價） | 其他相容 OpenAI 的供應商種類 |
| 免費 | 本機執行環境（`ollama`、`lm_studio`、`ovms`、`vllm`、`local`） |
| 訂閱制（沒有帳單可供比對） | coding-plan／訂閱制供應商種類——任何回報的數字都應視為估算值，而非帳單 |

請使用 `opensquilla providers status --probe-models` 與
`opensquilla cost --by-model`，檢視你設定的供應商／模型，在特定工作
階段中落在哪一個類別。

### 單輪與路由預算閘門

每輪對話有兩種 Agent 預算閘門，行為並不相同：

- `max_turn_billed_cost_usd` 只針對真實的供應商計費成本設閘。在從不
  回報計費成本的供應商或路徑上，它處於閒置狀態（永遠不會觸發）——在
  `openrouter` 以外的情境，請勿只依賴這個閘門。
- `max_turn_cost_usd` 使用與本節其他地方相同的累加器設閘：供應商有
  回報時用計費成本，否則用快取感知／快取盲估算值。它適用於所有供應商。
  觸發時，錯誤（`turn_cost_budget_exceeded`）會註明總額是計費、估算，
  還是混合而來。

SquillaRouter 的工作階段預算閘門（`[squilla_router.budget]`，見
[`features/squilla-router.md`](../features/squilla-router.md)）會在每個
`router_budget.warn` / `router_budget.cap` 事件與路由軌跡中，記錄一個
`spend_source`：

| `spend_source` | 意義 |
| --- | --- |
| `billed` | 累計花費為真實的供應商計費成本。 |
| `estimate` | 累計花費為整個工作階段的本機估算值。 |
| `estimate_mixed` | 該工作階段混合了計費與估算成本。 |
| `none` | 尚未記錄任何花費。 |
| `unknown` | 無法判定花費金額；此閘門會暫停，而不是依猜測數字行動。 |

接下來可以閱讀：[`usage-and-cost.md`](./usage-and-cost.md)，了解
`opensquilla cost` CLI 與如何解讀工作階段的用量資料列。

## 供應商疑難排解

從這裡開始：

```sh
opensquilla doctor
opensquilla providers status
opensquilla diagnostics on
```

請檢查：

- API 金鑰的環境變數，已在閘道器行程環境中設定；
- 模型 id 與供應商相符；
- 相容 API 的 base URL 正確無誤；
- 代理伺服器設定與你的網路環境相符；
- 在偵錯單一確切供應商／模型時，路由已停用；
- 設定變更後，閘道器已重新啟動。

---

[說明索引](./README.md) · [產品指南](../../README.product.zh-Hant.md) · [協助改善本頁](../contributing-docs.md) · [回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
