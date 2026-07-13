<!-- 譯自 ../agents.md @ 8e84dc04；過期檢查：git log 8e84dc04..HEAD -- docs/agents.md -->

# 持久化的 Agent

> 本文件譯自 [`agents.md`](../agents.md)，內容以英文版為準。

OpenSquilla 的 agent 是具名的執行期設定檔。當不同的工作流程需要不同的
預設值時，例如研究用工作區、寫作用工作區，或面向頻道的助理，就可以使用
agent。

內建的 `main` agent 一律可用。額外的 agent 可透過 `opensquilla agents`
設定。

## 何時該建立 Agent

當你想為以下項目建立穩定的身分時，請建立一個持久化的 agent：

- 專屬的工作區；
- 預設的模型選擇；
- 獨立的頻道或自動化目標；
- 週期性任務設定檔；
- 專屬的助理名稱與描述。

請不要為每一段對話都建立新的 agent。一般對話的延續性，請使用工作階段
即可。

## 列出 Agent

```sh
opensquilla agents list
opensquilla agents list --json
```

## 新增 Agent

```sh
opensquilla agents add research \
  --name Research \
  --description "Research and synthesis workspace" \
  --workspace /path/to/research \
  --model gpt-5.4-mini
```

Agent 的變更會寫入設定檔。在依賴更新後的 agent 清單之前，請先重新啟動
gateway：

```sh
opensquilla gateway restart
```

## 搭配工作階段使用 Agent

依 agent 篩選工作階段：

```sh
opensquilla sessions list --agent research
```

為某個 agent 建立排程工作：

```sh
opensquilla cron add \
  --agent research \
  --every 1h \
  --text "Summarize new research notes" \
  --name research-hourly-summary
```

頻道設定也可以依照頻道的設定內容，將收到的訊息路由給已設定的 agent。

## 刪除 Agent

```sh
opensquilla agents delete research
opensquilla agents delete research --force
```

刪除一筆 agent 項目，不會動到工作區檔案與狀態資料。只有在確定不再需要
這些資料時，才需要另外清理。

## Agent 與工作階段、Skill 的比較

| 概念 | 用途 |
| --- | --- |
| Agent | 工作流程的持久身分與預設值。 |
| 工作階段 | 對話歷史紀錄與進行中任務的延續性。 |
| Skill | 可重複使用的工作流程指示或工具例行程序。 |
| Meta-skill | 由多個 skill 步驟組成的複合工作流程。 |

延伸閱讀：

- [`sessions.md`](./sessions.md)
- [`features/skills.md`](../features/skills.md)
- [`features/meta-skills.md`](../features/meta-skills.md)
- [`channels.md`](./channels.md)

---

[文件索引](./README.md) · [產品指南](../../README.product.zh-Hant.md) · [改善本頁](../contributing-docs.md) · [回報文件問題](https://github.com/opensquilla/opensquilla/issues/new?template=docs_report.yml)
