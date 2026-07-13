<!-- 譯自 ../tools-and-sandbox.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/tools-and-sandbox.md -->

# 工具、核准與 Sandbox

> 本文件譯自 [`tools-and-sandbox.md`](../tools-and-sandbox.md)，內容以英文版為準。

OpenSquilla 工具讓 agent 擁有實用的能力。政策層、核准介面、工作區限制，以及
sandbox 狀態，共同控制這些工具被允許執行的動作方式。

在執行無人值守的自動化作業、檔案編輯、shell 命令，或頻道串接的 agent 之前，
請先閱讀本頁。

若需要更聚焦的權限說明，請參閱
[`approvals-and-permissions.md`](./approvals-and-permissions.md)。

## 內建工具領域

| 領域 | 範例 |
| --- | --- |
| 檔案系統 | `read_file`、`write_file`、`edit_file`、`list_dir`、`glob_search`、`grep_search`、試算表讀取。 |
| Shell 與程式碼 | `exec_command`、`background_process`、`process`、`execute_code`。 |
| Git | `git_status`、`git_diff`、`git_log`、`git_commit`、`apply_patch`。 |
| Web | `web_search`、`web_discover`、`web_fetch`、`http_request`。 |
| 記憶 | `memory_search`、`memory_save`、`memory_get`、`memory_delete`。 |
| 工作階段 | `sessions_send`、`sessions_spawn`、`sessions_list`、`sessions_history`、`session_status`。 |
| Artifacts | `publish_artifact`。 |
| 媒體 | 影像生成、PDF、TTS，以及媒體輔助工具。 |
| Skills | `skill_list`、`skill_view`、`skill_create`、`skill_edit`、`install_skill_deps`、`meta_invoke`。 |
| 管理 | cron 與 gateway 管理。 |
| 頻道／平台 | 訊息傳遞，以及 Feishu／Lark 的文件、聊天、雲端硬碟、wiki、媒體與權限輔助工具。 |

## 權限模式

在無人值守執行時，請使用更嚴格的模式：

```sh
opensquilla agent --permissions restricted -m "Inspect this repo"
```

只有在你信任這項任務與工作區時，才使用更寬鬆的模式：

```sh
opensquilla agent --permissions full --workspace /path/to/project -m "Run tests and fix failures"
```

在互動式工作中，Web UI 的核准介面可以暫停敏感的工具呼叫以供審查。在自動化
情境中，請在作業開始前，先選好權限模式與工作區政策。

詳見：[`approvals-and-permissions.md`](./approvals-and-permissions.md)

## 核准流程

敏感動作是否會暫停以等待人工核准，取決於權限模式、工具政策、頻道介面，以及
執行期設定。

以下情境的核准格外重要：

- 檔案系統寫入；
- shell 命令；
- 外部頻道或 webhook 傳送；
- 即將發布的產生 artifact；
- 會影響其他服務的動作。

當你需要在聊天捲動紀錄之外進行持久性審查時，請使用 Web UI 的核准頁面。

## 工作區控制

唯讀端限制：

```sh
opensquilla agent --workspace /path/to/project --workspace-strict -m "Summarize this repo"
```

寫入限制：

```sh
opensquilla agent \
  --workspace /path/to/project \
  --workspace-lockdown \
  --scratch-dir /path/to/project/.scratch \
  -m "Investigate and prepare a minimal patch"
```

`--workspace-lockdown` 適用於寫入動作必須留在工作區或暫存目錄內的自動化情境。

## Sandbox 指令

```sh
opensquilla sandbox status
opensquilla sandbox on
opensquilla sandbox full
opensquilla sandbox bypass
opensquilla sandbox reset
```

sandbox 的行為會因平台而異。請將 `sandbox status` 與 `doctor` 視為目前這台
機器的真實狀態來源。

## 建議模式

| 任務 | 建議狀態 |
| --- | --- |
| 唯讀儲存庫摘要 | `--workspace` 搭配 `--workspace-strict` |
| 搭配測試的本地修補 | `--workspace`、`--workspace-lockdown`，加上一個暫存目錄 |
| 可能有寫入動作的聊天 | Web UI，並保持核准畫面可見 |
| 頻道串接的 agent | 保守的權限，加上明確的頻道設定 |
| Provider／除錯調查 | 開啟診斷，並使用最小的工具權限 |

## Web 安全性

OpenSquilla 的 web 工具會使用 provider 設定與防護機制。當網頁搜尋行為異常時，
請使用 provider 診斷：

```sh
opensquilla search status
opensquilla search query "test query"
opensquilla diagnostics on
```

搜尋結果與擷取到的頁面都是外部資料，應該用來輔助回答內容，而不是凌駕於工具
政策或使用者指示之上。

若要取得有來源依據的答案，`web_search` 是預設的高階 web 工具。`web_discover`
是輕量的連結探索工具，`web_fetch` 會讀取特定頁面，而 `http_request` 則保留
給原始的 HTTP／API 請求使用。

## 工具壓縮

大型工具結果在顯示給模型之前，可能會先被壓縮。這是正常現象，用來保護目前
使用中的 context window。詳見
[`features/tool-compression.md`](../features/tool-compression.md)。

## Artifacts 與媒體

工具呼叫可以發布 artifact 並產生媒體內容。使用者可見的 artifact、文件、
影像、PDF 與 TTS 工作流程，詳見
[`artifacts-and-media.md`](../artifacts-and-media.md)。

## 疑難排解

如果工具無法執行：

1. 檢查權限狀態：

   ```sh
   opensquilla sandbox status
   opensquilla doctor
   ```

2. 檢查 gateway 或頻道介面是否需要核准。
3. 確認工作區路徑正確無誤。
4. 若持續失敗，請使用診斷功能：

   ```sh
   opensquilla diagnostics on
   ```

---

[文件索引](./README.md) · [產品指南](../../README.product.zh-Hant.md) · [改善本頁](../contributing-docs.md) · [回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
