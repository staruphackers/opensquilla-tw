<!-- 譯自 docs/web-ui.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/web-ui.md -->

# Web UI

> 本文件譯自 [`web-ui.md`](../web-ui.md)，內容以英文版為準。

OpenSquilla 的 Web UI 是本地端的控制台，用於設定、聊天工作階段、核准、頻道、
日誌、Agent、使用量與運作狀態。當你想要以瀏覽器進行聊天、檢視工具活動、取得
持久化的核准紀錄，以及快速掌握 runtime 健康狀況時，這是最合適的介面。

在 0.4 發行系列中，預設的控制 UI 是由 gateway 提供服務的 Vue 產品 UI。舊版
前端僅保留作為維護者的回退備援，並非一般使用者的標準路徑。

## 啟動 Web UI

在前景執行 gateway：

```sh
opensquilla gateway run
```

開啟：

```text
http://127.0.0.1:18791/control/
```

或啟動受管理的背景 gateway：

```sh
opensquilla gateway start --json
opensquilla gateway status
```

為了安全，gateway 預設綁定在 `127.0.0.1`。

關於 gateway 生命週期、host／port 與對外開放的詳細說明，請見
[`gateway.md`](./gateway.md)。

## 主要區塊

| 區塊 | 用途 |
| --- | --- |
| 對話 | 執行與繼續聊天工作階段、檢視工具活動、啟動 `/meta` 工作流程、發佈 artifact，以及使用手動壓縮控制項。 |
| 對話紀錄 | 從側邊欄切換使用中的工作階段，讓長時間執行的工作保持可見。 |
| 概覽／健康狀況 | 檢視就緒狀態、provider 狀態、記憶狀態、sandbox 狀態，以及復原提示。 |
| 設定 | 透過彈出視窗流程，設定 provider、router、搜尋、頻道、權限，以及其他設定區塊。 |
| 頻道 | 檢視已設定頻道的配接器狀態，並可直接跳至引導式設定流程進行變更。 |
| Skill | 瀏覽 skill 就緒狀態與 MetaSkill 可用性。 |
| 工作階段 | 檢視持久化的工作階段紀錄與運作狀態。 |
| Agent | 管理持久化的 Agent 項目。 |
| 用量 | 檢視 token 與預估成本的彙總資訊。 |
| 排程任務 | 檢視並管理排程執行。 |
| 日誌 | 檢視 runtime 日誌與診斷資訊。 |
| 核准 | 回應敏感工具呼叫的核准請求。 |

## 聊天工作階段

聊天 UI 支援：

- 串流輸出助理回應；
- 工具呼叫卡片；
- 針對 provider、router、工具與使用量事件的回合活動與 RunTrace 檢視；
- 針對敏感操作的行內核准請求；
- 有預覽可用時，顯示帶縮圖的 artifact 卡片；
- 用於生成產出的產物抽屜；
- 用於交接的分享與匯出動作；
- 用於切換工作階段的對話側邊欄；
- 在以 gateway 為後端的聊天工作階段中列出並啟動 `/meta`；
- 壓縮或 runtime 工作進行中時的待處理訊息佇列行為；
- 手動執行 `/compact`；
- 有可用資訊時，顯示每回合的使用量與節省成本中繼資料；
- 可複製的工作階段金鑰；
- 行動版分頁，讓聊天、工作階段與運作檢視在小螢幕上依然可以切換使用。

使用工作階段選擇器在既有工作階段之間切換。回報錯誤，或請 OpenSquilla 的
其他介面檢視同一個工作階段時，請複製工作階段金鑰。

當你想要讓程式碼修改透過 `opensquilla code-task` 執行時，可以從聊天介面
啟用 Coding 模式。開啟 Coding 模式後，程式碼變更會改用
[`cli.md`](./cli.md#coding-mode-and-code-task) 中說明的受保護主機工作流程，
而不是一般的工作階段內編輯。

## 手動壓縮

長時間的工作階段可以從聊天介面進行壓縮。如果不需要壓縮，UI 會顯示：

```text
Already within context budget; no compact was applied
```

如果壓縮正在進行中，請等待它進入結束狀態，再假設下一則訊息已套用壓縮後的
context。請見 [`features/compaction-and-cache.md`](../features/compaction-and-cache.md)。

## Artifacts

當 Agent 發佈檔案時，Web UI 會顯示一張 artifact 卡片。artifact 卡片可用於：

- 生成的 HTML 原型；
- 報告與簡報摘要；
- 匯出的資料檔案；
- PDF、投影片、圖片，以及其他生成的產出。

artifact 卡片可能包含縮圖或預覽中繼資料，而產物抽屜則能讓已發佈的產出，在
原始回合捲動消失後依然可以找到。

關於頻道傳送限制與 artifact 復原，請見
[`artifacts-and-media.md`](../artifacts-and-media.md)。

## 核准

部分工具需要確認。核准區塊為操作者提供一個持久化的地方，可以核准或拒絕
敏感操作，而不必把決策淹沒在聊天文字之中。

請在以下情況使用核准區塊：

- Agent 想要寫入檔案時；
- 指令需要提升權限時；
- 頻道或外部操作需要人工確認時；
- 無人值守的自動化應該在高風險操作前暫停時。

## 日誌與診斷

進行本地端診斷：

```sh
opensquilla diagnostics on
opensquilla gateway status
opensquilla doctor
```

使用 Web UI 的日誌與健康狀況檢視，來對照 provider 就緒狀態、頻道狀態、
工作階段狀態，以及使用者可見的錯誤。

## 安全性

Web UI 預設是本地端的。如果你要把 gateway 綁定到公開介面，請先設定 token
驗證與網路控管：

```sh
opensquilla gateway run --listen 0.0.0.0 --port 18791
```

請勿把未經驗證的 gateway 對外開放到公開網際網路。

---

[說明索引](./README.md) · [產品指南](../../README.product.zh-Hant.md) ·
[改善這個頁面](../contributing-docs.md) ·
[回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
