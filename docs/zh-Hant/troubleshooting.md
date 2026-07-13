<!-- 譯自 ../troubleshooting.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/troubleshooting.md -->

# 疑難排解

> 本文件譯自 [`troubleshooting.md`](../troubleshooting.md)，內容以英文版為準。

先從這裡開始：

```sh
opensquilla doctor
opensquilla doctor --json
opensquilla gateway status
```

當 gateway 正在執行時，位於 <http://127.0.0.1:18791/control/> 的 Web UI Health 畫面，也會回報就緒程度與復原步驟。

## 找不到 `opensquilla` 指令

執行 `uv tool install` 之後，請開啟新的終端機視窗，或執行：

```sh
uv tool update-shell
```

檢查執行檔：

```sh
command -v opensquilla
```

在 Windows PowerShell 上：

```powershell
where.exe opensquilla
```

## Gateway 未執行

啟動它：

```sh
opensquilla gateway run
```

或是使用受管理的背景程序：

```sh
opensquilla gateway start --json
opensquilla gateway status
```

開啟：

```text
http://127.0.0.1:18791/control/
```

若需要專門介紹 gateway 的完整指南，請見 [`gateway.md`](./gateway.md)。

## 桌面版 Gateway 啟動時回報遷移鎖定

首次執行期間，桌面應用程式會啟動本地端 gateway，並在開啟 Control UI 之前，套用尚未完成的 SQLite 遷移。如果啟動過程被中斷，gateway 可能會針對 `sessions.db` 回報 yoyo 遷移鎖定。

近期版本在鎖定紀錄列所指向的，僅是已消失或無效的程序 ID 時，會自動復原。只要任何已記錄的 pid 仍存活，gateway 就會持續明確顯示這次遷移失敗，不會清除鎖定。

請檢查桌面版 gateway 的日誌，尋找以下事件：

```text
migrator.lock_timeout
migrator.stale_lock_cleared
migrator.lock_held_by_live_process
migrator.stale_lock_retry_failed
```

如果日誌顯示鎖定是由存活中的程序持有，請等待該 gateway 完成啟動，或乾淨地停止該程序。除非你已確認記錄中的程序已不再執行，否則請勿移除 `yoyo_lock` 資料列，也不要執行 yoyo break-lock。

## 為錯誤回報收集診斷資訊

只要一個動作，就能收集維護者需要的所有資訊：

- **CLI：**`opensquilla bundle`——即使 gateway 無法啟動，也能運作。
- **Web UI：**日誌頁面 → **Diagnostic bundle** 按鈕。
- **桌面應用程式：**應用程式選單 → **Download Diagnostics…**（如果應用程式無法連上它的 gateway，則會改為開啟日誌資料夾）。

這個 bundle 是單一 zip 檔案，內含 gateway 日誌、近期錯誤紀錄、router 決策與追蹤片段、離線健康狀態報告，以及所有機密都經過遮罩處理的設定內容。本機路徑會正規化為 `~`，且對話內容預設會**排除**在外，除非你明確選擇加入（使用 `--include-content` 或勾選對話框中的核取方塊）。請將這個 zip 檔案附加到你的 GitHub issue。

當某個回合失敗時，錯誤訊息結尾會附上類似 `(ref: a1b2c3d4)` 的參照代碼。請在你的回報中引用這組代碼——它能將你的描述，與 bundle 內記錄的錯誤直接對應起來。

### 日誌儲存位置

- CLI／gateway 安裝方式：`~/.opensquilla/logs/`（`debug.log` 是輪替的 gateway 日誌；`gateway.log` 則記錄常駐化後的 stdout）。
- 桌面應用程式（macOS）：`~/Library/Application Support/OpenSquilla/logs/`
  （封裝後的建置版本）或 `~/Library/Application Support/@opensquilla/desktop-electron/logs/`
  （開發用建置版本）——`desktop.log` 是應用程式生命週期日誌，
  `gateway.log` 則是內嵌 gateway 的輸出。gateway 自身的狀態，則存放在
  旁邊的 `opensquilla/state/` 之下。

## Port 已被使用

使用其他 port：

```sh
opensquilla gateway run --port 18792
```

或是停止受管理的 gateway：

```sh
opensquilla gateway stop
```

## 尚未設定 Provider

執行：

```sh
opensquilla onboard
opensquilla providers list
opensquilla providers configure openrouter
```

使用環境變數形式的機密：

```sh
export OPENAI_API_KEY="sk-..."
opensquilla configure provider --provider openai --api-key-env OPENAI_API_KEY
```

## Router 相依性問題

如果 SquillaRouter 無法載入，OpenSquilla 仍然可以用直連模型路由的方式繼續執行。若要停用 router：

```sh
opensquilla configure router --router disabled
opensquilla gateway restart
```

在 Windows 上，ONNX Runtime 可能需要 Visual Studio 2015-2022 x64 版的 Visual C++ Redistributable。請先安裝它，再重新啟動 shell 與 gateway。

在 macOS 終端機安裝方式下，LightGBM 可能需要系統的 OpenMP runtime。如果啟動時的日誌顯示 `lightgbm/lib/lib_lightgbm.dylib` 出現
`Library not loaded: @rpath/libomp.dylib`，請安裝它，然後重新啟動 gateway：

```sh
brew install libomp
opensquilla gateway restart
```

桌面應用程式已內建打包好所需的原生 runtime；這個修復步驟僅適用於終端機安裝或原始碼安裝方式。

## 搜尋功能無法運作

檢視搜尋 provider：

```sh
opensquilla search list
opensquilla search status
```

使用 DuckDuckGo 走免金鑰路徑：

```sh
opensquilla configure search --search-provider duckduckgo
```

使用 Brave，並搭配金鑰：

```sh
export BRAVE_SEARCH_API_KEY="..."
opensquilla configure search --search-provider brave --api-key-env BRAVE_SEARCH_API_KEY
```

當你的工作流程需要更即時的資訊，或更豐富的來源內容時，可使用 Bocha、IQS、Tavily 或 Exa：

```sh
export BOCHA_SEARCH_API_KEY="..."
opensquilla configure search --search-provider bocha --api-key-env BOCHA_SEARCH_API_KEY

export IQS_SEARCH_API_KEY="..."
opensquilla configure search --search-provider iqs --api-key-env IQS_SEARCH_API_KEY

export TAVILY_API_KEY="..."
opensquilla configure search --search-provider tavily --api-key-env TAVILY_API_KEY

export EXA_API_KEY="..."
opensquilla configure search --search-provider exa --api-key-env EXA_API_KEY
```

無論是免金鑰、部分金鑰，或是全部都設定金鑰的組合，都可以檢視實際生效的 runtime 狀態：

```sh
opensquilla search status --json
```

## 頻道設定已儲存，但頻道離線

編輯頻道設定後，請重新啟動 gateway：

```sh
opensquilla gateway restart
opensquilla channels status <name> --json
```

對於 webhook 頻道，請確認該 provider 能夠連線到 gateway，且 callback 用的機密資訊相符。

## 工具被拒絕

檢視 sandbox 與權限狀態：

```sh
opensquilla sandbox status
opensquilla doctor
```

對於一次性執行，請明確選擇權限模式：

```sh
opensquilla agent --permissions restricted -m "Read only"
opensquilla agent --permissions full -m "Trusted local automation"
```

## Agent 似乎忘記了舊有的 context

長時間的工作階段可能會壓縮舊有的歷史紀錄，這在 context 壓力下是預期中的行為。

檢視工作階段：

```sh
opensquilla sessions show <session-key>
opensquilla sessions export <session-key>
```

如果精確的舊文字內容很重要，請將它保留在檔案、記憶筆記，或已匯出的工作階段中。

## 回合成本過高或速度過慢

可以試試：

```sh
opensquilla configure router --router recommended
opensquilla diagnostics on
opensquilla cost
```

若是自動化情境：

```sh
opensquilla agent --max-iterations 20 --timeout 600 -m "Bounded task"
```

若工具輸出結果過於龐大，請見
[`features/tool-compression.md`](../features/tool-compression.md)。

## Docker：其他機器無法連上 Web UI

預設的 compose port 發布方式僅限 loopback
（`127.0.0.1:18791:18791`），因此其他裝置無法連上 gateway。
請改為發布到所有網路介面——並且要先設定權杖驗證：

```yaml
ports:
  - "18791:18791"
```

請將 `OPENSQUILLA_LISTEN` 保持在 `0.0.0.0`；對外開放與否是由
`ports` 對應設定所控制，而不是由綁定位址控制。如果主機有執行防火牆，
請允許來自你區域網路（LAN）的 TCP 18791 傳入連線。完整流程請見：
[`docker.md`](../docker.md)。

## Docker：Web UI 可以連線，但設定變更遭拒

容器化的 gateway 會綁定萬用位址，因此每個瀏覽器——
包括與 gateway 位於同一台主機上的瀏覽器——都會被視為遠端操作者。
沒有權杖的遠端操作者，可以聊天，但無法管理設定或 onboarding。請啟用權杖驗證：

```yaml
environment:
  OPENSQUILLA_AUTH_MODE: token
  OPENSQUILLA_AUTH_TOKEN: ${OPENSQUILLA_AUTH_TOKEN:?generate one with openssl rand -hex 32}
```

請將權杖值放進 `compose.yaml` 旁、已加入 git 忽略清單的 `.env` 中，然後使用
權杖登入，權杖會帶在 URL 裡：

```text
http://<server-address>:18791/control/?token=<value>
```

請特別使用 `token` 模式——`password` 與 `trusted-proxy` 模式不
支援 Web UI 連線。如果這些變數沒有作用，狀態 volume 裡的 `config.toml`
可能已經包含一個 `[auth]` 區段——啟動時 TOML 中的值，優先於
`OPENSQUILLA_AUTH_*`；請在該處（或在 Web UI 中）編輯權杖，然後重新啟動。

## Docker：使用 bind mount 掛載狀態目錄時，Gateway 啟動失敗

容器是以非 root 的 UID 10001 執行。如果 bind mount 目錄的擁有者是其他
使用者，就會無法寫入，導致 gateway 在建立資料庫時失敗。
請將目錄的擁有權交給容器使用者，然後重新啟動：

```sh
sudo chown -R 10001:10001 /srv/opensquilla
docker compose up -d
```

預設的具名 volume（`opensquilla-state`）沒有這個問題——映像檔會
預先以正確的擁有者建立狀態根目錄。

## Docker：建置失敗，顯示「model assets are unavailable」

`docker build` 會驗證內建的 router 模型，並拒絕把 Git LFS 指標檔案
原封不動地打包進映像檔中。請在建置之前先把它們還原成實際內容
（在 Debian 上，`git-lfs` 是與 `git` 分開的獨立套件）：

```sh
sudo apt install -y git git-lfs
git lfs pull --include="src/opensquilla/squilla_router/models/**"
docker build -t opensquilla:local .
```

使用預先建置好的映像檔，可以完全避開這個問題——請見 [`docker.md`](../docker.md)。

---

[說明索引](./README.md) · [產品指南](../../README.product.zh-Hant.md) · [協助改善本頁](../contributing-docs.md) · [回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
