<!-- 譯自 ../configuration.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/configuration.md -->

# 設定

> 本文件譯自 [`configuration.md`](../configuration.md)，內容以英文版為準。

OpenSquilla 可以透過入門精靈、Web UI 設定流程、CLI 指令、環境變數與 TOML
檔案來設定。日常設定請使用 CLI 指令，只有在進階或腳本化部署時才編輯 TOML。

## 設定載入順序

OpenSquilla 會依照以下順序讀取設定：

1. `OPENSQUILLA_GATEWAY_CONFIG_PATH`
2. `./opensquilla.toml`
3. `~/.opensquilla/config.toml`
4. 內建預設值

當你想要寫入或檢視專案本機的設定檔時，請使用 `--config ./opensquilla.toml`。

## 機密資訊處理

機密資訊建議以環境變數參照的方式提供：

```sh
export OPENROUTER_API_KEY="sk-..."
opensquilla configure provider --provider openrouter --api-key-env OPENROUTER_API_KEY
```

避免把原始 API 金鑰提交到 TOML 檔案、shell 歷史紀錄、範例或問題回報中。

## 首次執行精靈

```sh
opensquilla onboard
```

常見選項：

```sh
opensquilla onboard --if-needed
opensquilla onboard --minimal
opensquilla onboard --provider openrouter --api-key-env OPENROUTER_API_KEY
opensquilla onboard --provider openai --model gpt-5.4-mini --api-key-env OPENAI_API_KEY
opensquilla onboard --provider ollama --model llama3.1
opensquilla onboard status
```

路由模式預設為 `recommended`。如果你想使用直連單一模型的路由方式，請使用
`--router disabled`。

## 重新設定單一區段

`configure` 指令可以編輯指定的區段：

```sh
opensquilla configure provider --provider openrouter --api-key-env OPENROUTER_API_KEY
opensquilla configure router --router recommended
opensquilla configure router --router openrouter-mix
opensquilla configure router --router disabled
opensquilla configure search --search-provider duckduckgo
opensquilla configure search --search-provider tavily --api-key-env TAVILY_API_KEY
opensquilla configure channels
opensquilla configure image-generation
opensquilla configure memory-embedding
```

支援的區段：

- `provider`
- `router`
- `channels`
- `search`
- `image-generation`
- `memory-embedding`

## 設定決策表

| 需求 | 建議指令 |
| --- | --- |
| 初次設定 | `opensquilla onboard` |
| CI 或安裝腳本 | `opensquilla onboard --if-needed` |
| 變更供應商 | `opensquilla configure provider ...` |
| 啟用或停用路由 | `opensquilla configure router ...` |
| 設定網頁搜尋 | `opensquilla configure search ...` |
| 設定訊息平台 | `opensquilla configure channels` |
| 檢視目前的值 | `opensquilla config get` |
| 保存進階金鑰設定 | `opensquilla config set <key> <value> --config <path>` |

## 工具政策

進階的腳本化執行可以用 `[tools]` 縮小模型可見的工具介面。若要在其餘條件
相同的多次執行之間比較工具介面差異，請保持呼叫端 harness 不變，並把工具
差異表達在設定中：

```toml
[tools]
profile = "coding"
also_allow = ["retrieve_tool_result"]
deny = ["execute_code", "background_process", "process"]
file_edit_requires_fresh_read = true
file_edit_flexible_recovery = true
```

`profile = "coding"` 會保留檔案系統、搜尋、shell、工作階段與記憶相關工具，
並在既有工作區檔案被編輯前，先啟用新鮮的 `read_file` 上下文讀取。上面的
`deny` 清單移除了額外的 Python／背景行程介面，適用於縮小範圍的執行；若省略
它，則會使用預設的 coding 介面。`file_edit_flexible_recovery` 預設為
`true`：當精確比對 `old_text` 失敗時，`edit_file` 可以套用唯一比對的空白／
縮排修復，並記錄修復事件是否被採用或拒絕，供診斷使用。

## 供應商設定

檢視供應商支援情況：

```sh
opensquilla providers list
opensquilla providers configure openrouter
opensquilla providers status
```

已通過入門引導驗證的供應商包括：

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

OpenSquilla 也內建了其他供應商的登記項目，涵蓋額外相容 OpenAI 的服務或自架
後端。請在你的安裝環境執行 `opensquilla providers list`，檢視目前的目錄
內容。

延伸閱讀：[`providers-and-models.md`](./providers-and-models.md)

## 路由設定

路由模式：

| 模式 | 適用時機 |
| --- | --- |
| `recommended` | 你想使用所選供應商的預設路由設定檔。 |
| `openrouter-mix` | 你想使用 OpenRouter 的混合模型預設值。 |
| `disabled` | 你想讓每一輪都使用同一個已設定的供應商／模型。 |

指令：

```sh
opensquilla configure router --router recommended
opensquilla configure router --router openrouter-mix
opensquilla configure router --router disabled
```

路由支援的供應商設定檔，取決於你安裝的版本與所設定的供應商。在使用直連
模型執行方式進行評估之前，請先閱讀
[`features/squilla-router.md`](../features/squilla-router.md)。

## 搜尋設定

檢視搜尋供應商：

```sh
opensquilla search list
opensquilla search status
opensquilla search query "OpenSquilla release notes"
```

設定搜尋：

```sh
opensquilla configure search --search-provider duckduckgo
opensquilla configure search --search-provider bocha --api-key-env BOCHA_SEARCH_API_KEY
opensquilla configure search --search-provider brave --api-key-env BRAVE_SEARCH_API_KEY
opensquilla configure search --search-provider tavily --api-key-env TAVILY_API_KEY
opensquilla configure search --search-provider exa --api-key-env EXA_API_KEY
opensquilla configure search --search-provider iqs --api-key-env IQS_SEARCH_API_KEY
```

此版本在執行期支援的搜尋供應商包括 DuckDuckGo、Bocha、Brave Search、阿里雲
IQS、Tavily 與 Exa。DuckDuckGo 是不需要金鑰的路徑。只設定部分金鑰時，只能
設定一個具金鑰的供應商；若設定了全部金鑰，則可以同時提供
`BOCHA_SEARCH_API_KEY`、`BRAVE_SEARCH_API_KEY`、`IQS_SEARCH_API_KEY`、
`TAVILY_API_KEY` 與 `EXA_API_KEY`，讓執行期依模式與能力自動選擇供應商，
除非請求中指名了明確的供應商。`search_provider` 是 `search_api_key` 與
`search_api_key_env` 的憑證錨點，並不是自動搜尋時必定遵守的路由承諾。
未來或尚未在執行期支援的整合，可能也會出現額外的供應商中繼資料。

延伸閱讀：[`search.md`](../search.md)

## 頻道設定

列出支援的頻道類型：

```sh
opensquilla channels types --json
opensquilla channels describe feishu
opensquilla channels add telegram --name personal
opensquilla channels status
```

儲存頻道設定會更新設定內容。編輯後請重啟閘道器：

```sh
opensquilla gateway restart
opensquilla channels status <name> --json
```

詳情請參閱 [`channels.md`](./channels.md)。

## 附件

附件擷取接受**任何檔案類型**。可轉譯的類型家族（圖片、PDF、文字、Office
文件、電子郵件）會被擷取或直接內嵌給模型；其餘的則視為*不透明（opaque）*
附件：這些位元組會被暫存到 Agent 工作區以供工具存取，絕不會被解析、解壓縮，
或內嵌進供應商的提示詞中。

```toml
[attachments]
# Admit opaque (non-rendered) attachment types: archives, binaries,
# audio/video, unknown formats. false restores the legacy fail-closed
# rendered-types-only admission gate on every surface.
accept_opaque = true
# Per-file ceiling for opaque attachments (bytes).
opaque_max_bytes = 31457280            # 30 MiB
# Aggregate RAM ceiling for the in-memory staged-upload store. When reached,
# new uploads get HTTP 507 UPLOAD_STORE_FULL (retryable; staged entries
# expire within the 10-minute TTL); a payload larger than the cap itself is a
# permanent 413. Non-positive or invalid values fall back to the default —
# this cap can be raised but not disabled. Requires a gateway restart.
upload_store_max_total_bytes = 314572800    # 300 MiB
# Disk budget for attachment copies materialized into an agent workspace
# (<workspace>/.opensquilla/attachments). When exceeded, new materializations
# degrade to an unavailable marker; existing files are never evicted. Set to
# 0 (or any non-positive value) to disable the budget entirely.
workspace_attachment_disk_budget_bytes = 1073741824  # 1 GiB
# Persist attachment bytes with session transcripts.
persist_transcripts = true
# media_root = ""                      # default: resolved from the cache dir
transcript_disk_budget_bytes = 2147483648   # 2 GiB
artifact_max_bytes = 31457280               # 30 MiB
artifact_disk_budget_bytes = 536870912      # 512 MiB
```

環境變數覆寫使用 `OPENSQUILLA_ATTACHMENTS_` 前綴
（`OPENSQUILLA_ATTACHMENTS_ACCEPT_OPAQUE`、`OPENSQUILLA_ATTACHMENTS_OPAQUE_MAX_BYTES` 等）。

大小政策速覽：2 MB 以內的內嵌附件會隨 RPC 訊息一起傳送；較大的檔案則會
透過 `POST /api/v1/files/upload`（10 分鐘 TTL）暫存，文字（整份內容需通過
UTF-8 驗證）、PDF、Office 與不透明類型，每個檔案上限為 30 MiB。電子郵件
一律受限於 2 MB 的文字上限，且絕不會走暫存路徑。每一輪對話：最多 10 個
附件，總計最多 60 MiB。

行為說明：

- 在 `accept_opaque = true`（預設值）時，上傳端點不會再對未轉譯的類型回傳
  HTTP 415 `UNSUPPORTED_MEDIA_TYPE`，`sessions.send` 也不會再拒絕這些檔案；
  停用此旗標的嚴格部署，則會保留舊有的錯誤與代碼不變。
- 不透明檔案只會以跳脫過的中繼資料封套，加上工作區路徑標記的形式送達
  模型；Agent 會在目前的安全分層與核准政策之下，透過檔案系統、shell 或
  程式碼工具來檢視或轉換這些檔案。在沒有沙箱後端的平台上，這些工具動作
  會仰賴核准機制。

## 記憶設定

常用指令：

```sh
opensquilla memory status
opensquilla memory index
opensquilla memory list
opensquilla memory search "project preference"
opensquilla memory show <path>
opensquilla memory dream
opensquilla memory flush-session <session-key>
```

設定 embedding 行為：

```sh
opensquilla configure memory-embedding
```

記憶功能可以結合以 Markdown 為後盾的來源，以及 SQLite 關鍵字與語意索引。
記憶的確切樣貌，取決於所設定的供應商與本機端 embedding 支援情況。

延伸閱讀：[`features/memory.md`](../features/memory.md)

## 沙箱與權限

檢視或變更目前狀態：

```sh
opensquilla sandbox status
opensquilla sandbox on
opensquilla sandbox full
opensquilla sandbox bypass
opensquilla sandbox reset
```

單次自動化執行的權限：

```sh
opensquilla agent --permissions restricted -m "Read the repo and summarize it"
opensquilla agent --permissions full -m "Make a local patch and run tests"
```

若是必須停留在單一工作區內的無人值守自動化：

```sh
opensquilla agent \
  --workspace /path/to/project \
  --workspace-lockdown \
  --scratch-dir /path/to/project/.scratch \
  -m "Investigate and propose the smallest fix"
```

延伸閱讀：[`tools-and-sandbox.md`](./tools-and-sandbox.md)

## 對外 URL 過濾與假 IP DNS

擷取 URL 的工具，會透過 `opensquilla.tools.ssrf` 中共用的 SSRF 防護機制來
驗證解析後的位址。私有、迴圈（loopback）、連結本地（link-local）與保留
範圍，預設一律會被封鎖。

某些受信任的代理伺服器或 fake-IP DNS 設定，會把 `github.com` 這類公開主機
名稱解析到 RFC 2544 效能測試範圍 `198.18.0.0/15` 內的位址。除非操作者明確
選擇加入，否則 OpenSquilla 仍會持續封鎖這些位址：

```toml
[tools]
trusted_fake_ip_cidrs = ["198.18.0.0/15"]
```

此設定只接受 `198.18.0.0/15` 的子網段。迴圈位址、RFC 1918 私有範圍、連結
本地位址，以及其他內部範圍，即使設定了也仍會被強制封鎖。如果公開主機
名稱解析到這些被強制封鎖的範圍，請修正 DNS 或代理伺服器設定，而不是繞過
這道防護機制。

## 閘道器繫結

前景執行：

```sh
opensquilla gateway run --listen 127.0.0.1 --port 18791
```

受管理執行：

```sh
opensquilla gateway start --json
opensquilla gateway status
opensquilla gateway stop
opensquilla gateway restart
```

繫結優先順序：

1. `--listen`
2. `--bind`
3. `OPENSQUILLA_LISTEN`
4. `OPENSQUILLA_GATEWAY_HOST`
5. 設定檔中的 host
6. `127.0.0.1`

## 原始設定編輯

若要調整進階設定，請檢視 `opensquilla.toml.example`，並直接編輯目前使用中
的設定檔。日常的供應商、路由、搜尋、頻道與沙箱變更，請使用 CLI 指令，
以避免常見的欄位結構錯誤。

手動修改檔案之後，請重啟閘道器並執行：

```sh
opensquilla doctor
opensquilla gateway status
```

---

[說明索引](./README.md) · [產品指南](../../README.product.zh-Hant.md) · [協助改善本頁](../contributing-docs.md) · [回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
