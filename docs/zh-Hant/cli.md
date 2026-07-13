<!-- 譯自 ../cli.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/cli.md -->

# CLI 參考手冊

> 本文件譯自 [`cli.md`](../cli.md)，內容以英文版為準。

`opensquilla` CLI 是設定、執行、檢視與自動化操作 OpenSquilla 最快的方式。

執行：

```sh
opensquilla --help
opensquilla <command> --help
```

## 主要指令

| 指令 | 用途 |
| --- | --- |
| `opensquilla init` | 初始化工作區。 |
| `opensquilla doctor` | 診斷就緒程度，並印出復原步驟。 |
| `opensquilla uninstall` | 移除 OpenSquilla；預設會保留你的資料（使用 `--purge-*` 可刪除）。 |
| `opensquilla onboard` | 執行或檢視首次執行設定。 |
| `opensquilla configure` | 重新設定 provider、router、頻道、搜尋、影像生成或記憶嵌入。 |
| `opensquilla gateway` | 執行並管理 gateway 伺服器。 |
| `opensquilla chat` | 啟動互動式終端機聊天。 |
| `opensquilla agent` | 執行單次、對自動化友善的 Agent 回合。 |
| `opensquilla code-task` | 透過 Coding mode 的 host workflow，執行有防護機制的程式碼任務。 |
| `opensquilla sessions` | 列出、檢視、繼續、中止、刪除或匯出工作階段。 |
| `opensquilla skills` | 列出、搜尋、瀏覽、安裝、更新、發布並檢視 skill。 |
| `opensquilla memory` | 檢視並維護記憶。 |
| `opensquilla channels` | 設定並檢視訊息頻道。 |
| `opensquilla providers` | 設定並檢視 LLM provider。 |
| `opensquilla search` | 設定並使用網路搜尋。 |
| `opensquilla sandbox` | 檢視或變更預設的 sandbox 模式。 |
| `opensquilla cron` | 管理排程的 OpenSquilla 執行。 |
| `opensquilla cost` | 檢視用量與預估成本。 |
| `opensquilla diagnostics` | 啟用或停用執行期診斷日誌記錄。 |
| `opensquilla replay` | 從決策日誌重播已記錄的回合。 |
| `opensquilla migrate` | 從外部 agent runtime 匯入狀態。 |
| `opensquilla models` | 檢視可用的模型。 |
| `opensquilla agents` | 管理持久化 Agent。 |
| `opensquilla mcp-server` | 執行 OpenSquilla MCP 伺服器橋接。 |
| `opensquilla swebench` | 執行選用的 SWE-bench 求解／評測工作流程。 |
| `opensquilla dist` | 輸出可重現的工作區狀態清冊。 |
| `opensquilla reset` | 重設工作階段，並同步清空記憶。 |

## 執行方式

Web UI 與 gateway：

```sh
opensquilla gateway run
opensquilla gateway start --json
opensquilla gateway status
opensquilla gateway restart
opensquilla gateway stop
```

終端機聊天：

```sh
opensquilla chat
opensquilla chat --model gpt-5.4-mini
opensquilla chat --session <session-key>
opensquilla chat --standalone --workspace /path/to/project
```

終端機聊天預設使用穩定的 Python 原生終端機後端。OpenTUI 是一個預覽版後端，
需要在評估該後端時，明確使用 `OPENSQUILLA_TUI_BACKEND=opentui` 選用。一般的
終端機聊天不需要 Bun 或 OpenTUI 的 node 模組。OpenTUI 預覽版適用於已在本機
安裝 Bun 相依套件的原始碼 checkout：

```sh
bun install --frozen-lockfile --cwd=src/opensquilla/cli/tui/opentui/package
OPENSQUILLA_TUI_BACKEND=opentui uv run opensquilla chat
```

過時的後端數值，會在啟動前就被拒絕。終端機聊天的使用方式請見
[`tui.md`](../tui.md)；後端架構、外掛插槽、Router HUD 與重播基準測試工作流程，
請見 [`features/tui-frontend.md`](../features/tui-frontend.md)。

Web 聊天與 CLI gateway TUI 支援 `/meta`，可手動啟動 MetaSkill：`/meta` 會列出
可用的工作流程，`/meta <name>` 則會執行指定的工作流程。頻道介面可以用
`/meta` 列出 MetaSkill，但無法直接啟動 MetaSkill 執行。獨立模式的 CLI 聊天，
需要 gateway 模式才能使用 `/meta`。

一次性自動化：

```sh
opensquilla agent -m "Review the current directory"
opensquilla agent --json -m "Return a short machine-readable summary"
opensquilla agent --workspace /path/to/project --workspace-strict -m "Inspect this repo"
opensquilla agent --timeout 600 --max-iterations 30 -m "Run a bounded investigation"
```

實用的自動化旗標：

| 旗標 | 用途 |
| --- | --- |
| `--workspace` | 設定工作區根目錄。 |
| `--workspace-strict` | 將讀取類檔案工具限制在該工作區內。 |
| `--workspace-lockdown` | 將寫入動作侷限在工作區或暫存目錄內。 |
| `--scratch-dir` | 將暫存的指令碼／日誌／候選修補檔，放在已知的目錄中。 |
| `--timeout` | 設定 Agent 的總執行時間上限。 |
| `--max-iterations` | 限制模型／工具迴圈的次數上限。 |
| `--max-provider-retries` | 限制暫時性 provider 重試的次數上限。 |
| `--length-capped-continuations` | 限制 provider 輸出因長度受限而自動接續的次數上限。 |
| `--thinking` | 覆寫推理層級。 |
| `--permissions` | 選擇 restricted、bypass 或 full 權限模式。 |
| `--transcript-path` | 為自動化寫入 JSONL 逐字稿。 |
| `--usage-path` | 寫入用量 JSON。 |
| `--session-db-path` | 讓工作階段重播內容跨多次呼叫持續保存。 |

## Coding Mode 與 Code-Task

Coding mode 會透過 `code-task` 工作流程，處理程式碼修改工作。它是為受信任的
repository 所設計：`code-task` 會在主機上執行一個 OpenSquilla agent，可能會
安裝相依套件，且不是 OS 層級的 sandbox。

```sh
opensquilla code-task solve --repo /path/to/repo --task-file task.md --yes
opensquilla code-task solve --repo https://github.com/org/project.git --issue 123
opensquilla code-task solve --verification-mode scratch --task "Create a small CLI parser" --yes
opensquilla code-task solve --repo /path/to/app --task-file task.md --verification-mode build --yes
```

請只使用一種任務來源：`--issue`、`--task` 或 `--task-file`。非互動式呼叫端
必須加上 `--yes`，以確認你了解受信任主機的邊界。實際工作會在 OpenSquilla
狀態樹底下的獨立執行目錄中進行；只有在工作流程收集並驗證有效變更之後，
來源 repository 才會被更新。

`--verification-mode red-green` 是既有 repository 的預設值。
`--verification-mode build` 適用於應用程式或成品交付檢查。
`--verification-mode scratch` 會建立一個空的、用完即丟的 repository，
且不能與 `--repo` 併用。

## SWE-Bench

`opensquilla swebench` 是選用的評測介面，不屬於一般安裝路徑的一部分。它需要
Docker，以及 `swebench` extra。

```sh
uv tool install --python 3.12 "opensquilla[recommended,swebench] @ https://github.com/opensquilla/opensquilla/releases/download/v0.5.0rc3/opensquilla-0.5.0rc3-py3-none-any.whl"
opensquilla swebench pull django__django-16429 --dataset verified
opensquilla swebench solve django__django-16429 --dataset verified --json
opensquilla swebench eval predictions.jsonl --dataset verified
```

如果你不需要以 Docker 為基礎的 SWE-bench harness，對於受信任的真實
repository 程式碼任務，請改用 `opensquilla code-task`。

## 設定指令

Provider 與 router：

```sh
opensquilla onboard
opensquilla onboard status
opensquilla configure provider --provider openrouter --api-key-env OPENROUTER_API_KEY
opensquilla configure router --router recommended
opensquilla providers list
opensquilla providers configure openrouter
opensquilla providers status
```

搜尋：

```sh
opensquilla search list
opensquilla search configure duckduckgo
opensquilla search query "latest OpenSquilla release"
opensquilla configure search --search-provider duckduckgo
```

頻道：

```sh
opensquilla channels types
opensquilla channels describe telegram
opensquilla channels add telegram --name personal
opensquilla channels list
opensquilla channels status
opensquilla channels enable personal
opensquilla channels disable personal
opensquilla channels restart personal
opensquilla channels remove personal
```

原始設定：

```sh
opensquilla config get llm.provider
opensquilla config set gateway.port 18791
```

更多細節：

- [`configuration.md`](./configuration.md)
- [`providers-and-models.md`](./providers-and-models.md)
- [`search.md`](../search.md)
- [`channels.md`](./channels.md)

## Skill 與 Meta-Skill

```sh
opensquilla skills list
opensquilla skills search pdf
opensquilla skills view pdf-toolkit
opensquilla skills install <skill-name>
opensquilla skills update --all
opensquilla skills uninstall <skill-name>
opensquilla skills inspect meta-skill-creator
opensquilla skills meta proposals list
opensquilla skills meta runs list
opensquilla skills meta runs show <run-id>
opensquilla skills meta runs steps <run-id>
opensquilla skills meta runs replay <run-id> --dry-run
```

當你想在呼叫某個 meta-skill 之前，先看看它編譯後的步驟計畫時，可使用
`skills inspect`。

MetaSkill 預設僅能手動啟動。在 Web 聊天與 CLI gateway TUI 中，執行 `/meta`
可列出工作流程，`/meta <name>` 則可啟動指定的工作流程。除非為了相容舊行為，
而在設定中設為 `meta_skill.auto_trigger = true`，否則自然語言的自動觸發
功能為停用狀態。

延伸閱讀：

- [`features/skills.md`](../features/skills.md)
- [`features/meta-skills.md`](../features/meta-skills.md)
- [`features/meta-skill-user-guide.md`](../features/meta-skill-user-guide.md)
- [`authoring/meta-skills.md`](../authoring/meta-skills.md)

## 工作階段與歷史紀錄

```sh
opensquilla sessions list
opensquilla sessions show <session-key>
opensquilla sessions resume <session-key>
opensquilla sessions abort <session-key>
opensquilla sessions export <session-key>
opensquilla sessions delete <session-key>
```

延伸閱讀：[`sessions.md`](./sessions.md)

## 記憶

```sh
opensquilla memory status
opensquilla memory index
opensquilla memory list
opensquilla memory search "preference"
opensquilla memory show <path>
opensquilla memory dream
opensquilla memory flush-session <session-key>
opensquilla memory repair list
opensquilla memory raw-fallbacks list
```

延伸閱讀：[`features/memory.md`](../features/memory.md)

## 持久化 Agent 與排程

```sh
opensquilla agents list
opensquilla agents add research --name Research --workspace /path/to/research
opensquilla agents delete research
opensquilla cron list
opensquilla cron add --every 1h --text "Summarize important updates" --name hourly-summary
opensquilla cron status <job-id>
opensquilla cron runs <job-id>
```

延伸閱讀：

- [`agents.md`](./agents.md)
- [`scheduling.md`](../scheduling.md)

## 成本、診斷與重播

```sh
opensquilla cost
opensquilla diagnostics status
opensquilla diagnostics on
opensquilla diagnostics off
opensquilla replay --session <session-key> --turn <turn-id>
```

當你需要理解某個回合為何出現特定行為時，可使用診斷與重播功能。

延伸閱讀：

- [`usage-and-cost.md`](./usage-and-cost.md)
- [`diagnostics-and-replay.md`](../diagnostics-and-replay.md)

## MCP Server 橋接

```sh
opensquilla mcp-server run
opensquilla mcp-server run --gateway ws://localhost:18792/ws
```

延伸閱讀：[`mcp-server.md`](./mcp-server.md)

## 解除安裝

```sh
opensquilla uninstall --dry-run        # preview what is removed and kept
opensquilla uninstall                  # remove the program, keep your data
opensquilla uninstall --purge-state    # also delete runtime state (sessions, logs, cache)
opensquilla uninstall --purge-config   # also delete config and secrets
opensquilla uninstall --purge-all      # delete ALL OpenSquilla data (needs a typed phrase)
opensquilla uninstall --json           # machine-readable plan/result
```

你的資料預設會被保留；使用 `--purge-*` 才會選擇刪除，而 `--purge-all` 需要
手動輸入確認用的字句（在非互動介面上，則使用 `--confirm-purge-all "delete
everything"`）。在刪除任何項目之前，正在執行的 gateway 會先排空並停止；
刪除範圍僅限於 OpenSquilla 的家目錄——移動過位置或共用的根目錄，會被拒絕
處理。Docker 與桌面安裝方式，會印出引導式移除步驟，而不是直接刪除映像層或
應用程式套件；原始碼安裝方式則絕不會刪除你的 checkout。

---

[說明索引](./README.md) · [產品指南](../../README.product.zh-Hant.md) · [協助改善本頁](../contributing-docs.md) · [回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
