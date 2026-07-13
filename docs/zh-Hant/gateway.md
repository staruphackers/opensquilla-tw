<!-- 譯自 ../gateway.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/gateway.md -->

# Gateway

> 本文件譯自 [`gateway.md`](../gateway.md)，內容以英文版為準。

OpenSquilla 的 gateway，是 Web UI、頻道、RPC 客戶端、工作階段、核准、診斷與用量檢視背後的本地端伺服器。大多數日常使用的 OpenSquilla 介面，都要在 gateway 執行時才能發揮最佳效果。

想要啟動、停止、檢視、對外開放，或排解 gateway 的問題時，請參考本頁。

## 前景 Gateway

在目前的終端機中執行 gateway：

```sh
opensquilla gateway run
```

開啟控制台：

```text
http://127.0.0.1:18791/control/
```

若要停止前景執行的 gateway，請按 `Ctrl+C`。

## 受管理的背景 Gateway

啟動受管理的背景程序，並等待就緒：

```sh
opensquilla gateway start --json
```

檢視狀態：

```sh
opensquilla gateway status
opensquilla gateway status --json
```

重新啟動或停止：

```sh
opensquilla gateway restart
opensquilla gateway stop
```

停止與重新啟動都會正常關閉：處理中的 Agent 回合與背景完成作業，會在程序結束前先排空，且強制終止的期限會超過這段排空預算，確保工作不會在寫入途中被中斷。可透過 `OPENSQUILLA_GATEWAY_GRACEFUL_TIMEOUT`（單位為秒；預設 30，有上限）調整各階段的排空預算。前景 gateway 收到 `Ctrl+C` ／ `SIGTERM` 時，也會執行相同的排空程序。在 Windows 上——因為沒有真正的 `SIGTERM`——桌面應用程式與 `gateway stop` 會透過僅限擁有者的 loopback `POST /api/system/shutdown` 觸發排空程序。

當你需要 Web UI、頻道、排程任務，以及在目前終端機分頁關閉後仍要繼續執行的本地端自動化時，請使用受管理的 gateway。

## Host 與 Port

使用不同的 port：

```sh
opensquilla gateway run --port 18792
opensquilla gateway status --port 18792
```

綁定到特定的 host：

```sh
opensquilla gateway run --listen 127.0.0.1 --port 18791
```

`--listen` 是綁定 host 用的別名；兩者同時提供時，會以 `--listen` 為準，優先於 `--bind`。

## 安全性預設值

gateway 預設使用 loopback 範圍（通常是 `127.0.0.1`），因為本地端 gateway 掌控著聊天、工具、工作階段、頻道、核准與設定等功能。

公開綁定為選擇加入（opt-in）：

```sh
opensquilla gateway run --listen 0.0.0.0 --port 18791
```

請勿在沒有權杖驗證，以及你完全理解的網路邊界防護下，將 gateway 暴露在不受信任的網路環境中。

## 設定檔路徑

使用指定的設定檔：

```sh
opensquilla gateway run --config /path/to/opensquilla.toml
opensquilla gateway status --config /path/to/opensquilla.toml
```

OpenSquilla 也會讀取 [`configuration.md`](./configuration.md) 所述的標準設定位置。

## 遠端狀態檢查

直接檢視某個 gateway URL：

```sh
opensquilla gateway status --gateway ws://localhost:18791/ws
```

當客戶端或 MCP 橋接以明確的 gateway URL 設定時，這個做法很有用。

## 何時該重新啟動

變更以下項目後，請重新啟動 gateway：

- provider 或 router 設定；
- 頻道設定；
- 持久化 Agent 項目；
- 全域 sandbox 模式；
- 搜尋或影像生成設定；
- 已設定 provider 所使用的環境變數。

```sh
opensquilla gateway restart
```

## 疑難排解

檢查狀態與就緒程度：

```sh
opensquilla gateway status
opensquilla doctor
```

如果 port 已被使用：

```sh
opensquilla gateway run --port 18792
```

如果 Web UI 無法連線，請確認 URL 與 gateway 綁定的 host、port 是否相符。

延伸閱讀：

- [`web-ui.md`](./web-ui.md)
- [`configuration.md`](./configuration.md)
- [`channels.md`](./channels.md)
- [`troubleshooting.md`](./troubleshooting.md)

---

[說明索引](./README.md) · [產品指南](../../README.product.zh-Hant.md) · [協助改善本頁](../contributing-docs.md) · [回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
