<!-- 譯自 ../sessions.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/sessions.md -->

# 工作階段與歷史紀錄

> 本文件譯自 [`sessions.md`](../sessions.md)，內容以英文版為準。

工作階段是持久保存的 OpenSquilla 對話。透過工作階段，你可以檢視過去的工作
內容、繼續對話、匯出逐字稿，或停止仍在執行中的回合。

在以下情況請使用工作階段：

- 從 CLI 或 Web UI 繼續先前的聊天；
- 找出某個 artifact、成本報告或頻道討論串所屬的工作階段鍵；
- 匯出逐字稿以供除錯或分享；
- 在不刪除工作階段的情況下，中止長時間執行的回合；
- 刪除不再需要的舊工作階段。

## 需求

工作階段指令會使用 gateway 的 RPC 介面。執行大多數工作階段指令之前，請先
啟動或連線到 gateway：

```sh
opensquilla gateway run
```

或使用受管理的背景 gateway：

```sh
opensquilla gateway start --json
opensquilla gateway status
```

## 列出最近的工作階段

```sh
opensquilla sessions list
opensquilla sessions list --limit 20
opensquilla sessions list --status idle
opensquilla sessions list --agent main
opensquilla sessions list --channel telegram
opensquilla sessions list --since 2026-05-01
```

在腳本中使用 `--json`：

```sh
opensquilla sessions list --json
```

## 檢視工作階段

```sh
opensquilla sessions show <session-key>
opensquilla sessions show <session-key> --json
```

輸出內容包含已解析的工作階段鍵、agent id、狀態、模型、更新時間、標題，以及
（如有的話）最新的預覽內容。

## 繼續工作階段

```sh
opensquilla sessions resume <session-key>
```

這會在既有的工作階段上開啟終端機聊天。當你想保留相同的對話狀態、而不是
開始一段全新的聊天時，可使用此功能。

## 中止執行中的回合

```sh
opensquilla sessions abort <session-key>
opensquilla sessions abort <session-key> --json
```

如果有正在執行的回合，中止會停止它，但不會刪除該工作階段。

## 匯出逐字稿

匯出為 Markdown：

```sh
opensquilla sessions export <session-key>
opensquilla sessions export <session-key> --output session.md
```

匯出為 JSON：

```sh
opensquilla sessions export <session-key> --format json --output session.json
```

匯出的逐字稿適合用於錯誤回報、稽核，或將任務內容轉移到文件中。在公開分享
匯出檔之前，請先移除機密資訊、私人本地路徑、provider 權杖，以及私人頻道
識別碼。

## 刪除工作階段

```sh
opensquilla sessions delete <session-key>
opensquilla sessions delete <session-key> --yes
```

刪除工作階段是用來清理資料。如果之後可能還需要逐字稿，請先匯出。

## Web UI 工作流程

Web UI 使用相同的工作階段系統。在控制台中，可使用聊天工作階段選擇器來切換
工作階段、檢視狀態，並繼續最近的工作。

開啟：

```text
http://127.0.0.1:18791/control/
```

## 疑難排解

如果指令無法連上 gateway：

```sh
opensquilla gateway status
opensquilla doctor
```

如果舊的 context 顯示為已摘要化，代表該工作階段可能已將較舊的歷史紀錄
壓縮過。這在長時間執行、context 壓力較大的工作階段中屬於正常現象。當你
需要精確文字內容時，請匯出該工作階段。

延伸閱讀：

- [`features/compaction-and-cache.md`](../features/compaction-and-cache.md)
- [`web-ui.md`](./web-ui.md)
- [`operations.md`](../operations.md)

---

[文件索引](./README.md) · [產品指南](../../README.product.zh-Hant.md) · [改善本頁](../contributing-docs.md) · [回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
