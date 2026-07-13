<!-- 譯自 ../channels.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/channels.md -->

# 頻道

> 本文件譯自 [`channels.md`](../channels.md)，內容以英文版為準。

頻道讓 OpenSquilla 可以從訊息平台執行，同時與 CLI 及 Web UI 共用相同的
agent 執行期。當你想讓同一個 agent 從 Slack、Telegram、Feishu／Lark、
Discord、DingTalk、WeCom、Matrix、QQ 或其他受支援的配接器回覆訊息時，
可使用頻道功能。

## 受支援的頻道類型

檢視你本地端的安裝內容：

```sh
opensquilla channels types
opensquilla channels types --json
opensquilla channels describe feishu
```

此版本提供以下頻道家族：

| 類型 | 標籤 | 傳輸方式 | 是否需要公開 URL |
| --- | --- | --- | :---: |
| `dingtalk` | DingTalk | websocket | 否 |
| `discord` | Discord | websocket | 否 |
| `feishu` | Feishu／Lark | 混合 | 依模式而定 |
| `matrix` | Matrix | websocket | 否 |
| `qq` | QQ Bot | websocket | 否 |
| `slack` | Slack | 混合 | 依模式而定 |
| `telegram` | Telegram | 混合 | 依模式而定 |
| `wecom` | WeCom | webhook | 是 |

本地端 `channels describe <type>` 的輸出內容，是必填欄位、機密資訊、extra
與重新啟動行為的真實來源。

## 設定流程

互動式設定：

```sh
opensquilla configure channels
```

明確新增一個頻道：

```sh
opensquilla channels add telegram --name personal
```

視需要加入 provider 專屬欄位。Slack 支援兩種模式：

```sh
# Slack Socket Mode: outbound websocket, no public URL.
opensquilla channels add slack --name team \
  --field connection_mode=socket \
  --field app_token=xapp-... \
  --token xoxb-...

# Slack Events API webhook: requires a public Request URL and signing secret.
opensquilla channels add slack --name team-webhook \
  --field connection_mode=webhook \
  --field signing_secret=... \
  --token xoxb-...
```

設定變更後，請重新啟動 gateway 行程：

```sh
opensquilla gateway restart
```

驗證執行期連線：

```sh
opensquilla channels status
opensquilla channels status personal --json
```

儲存一個頻道，證明的是設定已經寫入。`channels status` 證明的則是目前執行中
的 gateway 是否已載入並連接該頻道。

## 管理頻道

```sh
opensquilla channels list
opensquilla channels enable <name>
opensquilla channels disable <name>
opensquilla channels edit <name>
opensquilla channels restart <name>
opensquilla channels logout <name>
opensquilla channels remove <name>
```

設定變更後請使用 `gateway restart`。`channels restart <name>` 僅適用於
已經載入且正在運作中的配接器。

## Slack 模式

Slack Socket Mode 使用對外發起的 websocket 連線，不需要公開的 Request URL。
它需要 bot 權杖（`xoxb-...`），加上一組儲存為 `app_token` 的 app 層級權杖
（`xapp-...`）。

Slack webhook 模式使用 Events API 的 Request URL，需要 bot 權杖加上
`signing_secret`，而且 gateway 必須讓 Slack 連得上。

當你希望配接器回覆到原本的對話串時，請將 `slack_channel_id` 保持空白；
只有在你想要一個預設的備援頻道時，才需要設定它。當回覆內容應保留在 Slack
討論串中時，請啟用 `reply_in_thread`。

## Webhook 頻道

Slack webhook 模式與 WeCom 都需要一個公開、provider 連得上的 URL。Feishu
與 Telegram 則視模式而定，可能也需要。

對於公開頻道：

- 將 gateway 綁定到一個可連上的網路介面；
- 將它放在受信任的反向代理或通道之後；
- 設定驗證方式；
- 仔細檢查 provider 的回呼 URL 與機密資訊。

在受控網路中綁定的範例：

```sh
opensquilla gateway run --listen 0.0.0.0 --port 18791
```

請勿將未經驗證的 gateway 公開暴露在網際網路上。

## 附件與 Artifacts

不同的頻道配接器，在附件與 artifact 傳送行為上可能有所差異。OpenSquilla
會透過相同的執行期路徑，將 agent 的執行動作正規化，但平台傳輸層仍然會
控制檔案大小限制、訊息討論串結構，以及下載／上傳能力。

當某個頻道無法直接傳送大型 artifact 時，請使用 Web UI 的 artifact 卡片或
工作階段匯出功能作為復原途徑。

## 疑難排解

如果某個頻道沒有回應：

1. 檢查設定項目：

   ```sh
   opensquilla channels list
   ```

2. 檢查執行期狀態：

   ```sh
   opensquilla channels status <name> --json
   ```

3. 設定變更後重新啟動 gateway 行程：

   ```sh
   opensquilla gateway restart
   ```

4. 對於 webhook 頻道，請確認公開 URL、provider 回呼機密資訊，以及
   gateway 的驗證／網路邊界設定。

---

[文件索引](./README.md) · [產品指南](../../README.product.zh-Hant.md) · [改善本頁](../contributing-docs.md) · [回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
