<!-- 譯自 ../mcp-server.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/mcp-server.md -->

# MCP 伺服器橋接

> 本文件譯自 [`mcp-server.md`](../mcp-server.md)，內容以英文版為準。

OpenSquilla 可以執行為 stdio MCP 伺服器橋接，供支援 MCP 的用戶端使用。當
另一個本地 AI 用戶端需要透過 Model Context Protocol，呼叫 OpenSquilla 的
工作階段工作流程時，可使用這項功能。

MCP 橋接是一個整合介面，與 OpenSquilla 的 Web UI、CLI、頻道及 gateway
控制台是分開的。

## 需求

當你需要這個橋接功能時，請安裝含有 `mcp` extra 的 OpenSquilla：

```sh
uv tool install --python 3.12 "opensquilla[recommended,mcp] @ https://github.com/opensquilla/opensquilla/releases/download/v0.5.0rc3/opensquilla-0.5.0rc3-py3-none-any.whl"
```

啟動 OpenSquilla 的 gateway：

```sh
opensquilla gateway run
```

或使用受管理的 gateway：

```sh
opensquilla gateway start --json
opensquilla gateway status
```

## 執行橋接

```sh
opensquilla mcp-server run
```

依預設，橋接會連線到：

```text
ws://localhost:18791/ws
```

使用不同的 gateway：

```sh
opensquilla mcp-server run --gateway ws://localhost:18792/ws
```

這個指令會執行一個 stdio MCP 伺服器。請設定你支援 MCP 的用戶端，以該指令
啟動伺服器行程。

## 安全性注意事項

- 除非你刻意要對外公開，否則請將 gateway 綁定在 `127.0.0.1`。
- 請勿在 MCP client 設定範例中，放入 provider 金鑰或頻道機密資訊。
- 請將 MCP client 視為另一個可呼叫工具的介面。相同的 OpenSquilla 權限、
  工具、工作階段與 gateway 狀態，仍然適用。

## 疑難排解

如果橋接無法啟動：

```sh
opensquilla gateway status
opensquilla doctor
```

如果指令回報缺少 MCP 相依套件，請使用 `mcp` extra 重新安裝。

延伸閱讀：

- [`configuration.md`](./configuration.md)
- [`tools-and-sandbox.md`](./tools-and-sandbox.md)
- [`operations.md`](../operations.md)

---

[文件索引](./README.md) · [產品指南](../../README.product.zh-Hant.md) · [改善本頁](../contributing-docs.md) · [回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
