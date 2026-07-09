# OpenSquilla Preview Knowledge Hybrid Retrieval Design

## 背景

`opensquilla-knowledge-preview` 已经具备 `baai/bge-m3` 向量索引和 hybrid 检索能力，preview 服务端 `/v1/status` 能看到：

- `vectorChunksIndexed`
- `vectorCoveragePct`
- `embeddingModel`
- `embeddingDimensions`

同时 `/v1/search` 已支持：

- `sqlite_fts5_default`
- `vector_bge_m3_1024`
- `hybrid_rrf_bge_m3_fts5`

OpenSquilla 当前通过 `KnowledgeBackend -> HttpKnowledgeBackend -> opensquilla-knowledge HTTP API` 调用知识服务，接口层已经基本能透传 `retrievalProfile`。但 OpenSquilla 的 RAG 页面和 agent 工具还停留在 FTS 时代：

- UI 只暴露 `SQLite FTS5`
- `retrievalProfile` 与 `indexProfiles` 共用一个状态变量
- UI 不展示 vector/hybrid 的状态和分数字段
- agent 工具只能通过 `filters` 隐式传入 `retrievalProfile`
- preview `[knowledge].timeout_seconds = 30.0`，对慢 vector/hybrid 查询不够

本设计只优化 preview 对新检索能力的承载体验，不改 U1-U4 的 shared knowledge 链路，不新增 vector build job API。

## 目标

让 OpenSquilla preview 能正确使用并展示 `opensquilla-knowledge-preview` 的 vector/hybrid 检索能力，同时保持 U1-U4 不受影响。

具体目标：

1. RAG 页面支持选择 `FTS / Vector / Hybrid` 检索模式。
2. 拆分入库索引配置和查询检索配置，避免把 hybrid 查询策略误传为 ingest index profile。
3. RAG 页面展示向量索引状态和 hybrid/vector 结果分数字段。
4. `knowledge_search` agent 工具显式支持 `retrieval_profile` 和 `collection_id`。
5. preview gateway 的 knowledge HTTP timeout 调整为 90 秒，缓解当前 query embedding 慢导致的 30 秒超时。

## 非目标

本轮不做：

- 不新增 `/v1/capabilities`
- 不新增 vector index build HTTP job API
- 不改 `opensquilla-knowledge` shared service `18765`
- 不改 U1-U4 的 endpoint 或 timeout
- 不重构整个 RAG 页面
- 不改 embedding 模型或重新跑向量索引

## 方案选择

采用方案 A：只改 OpenSquilla 侧的 preview 承载能力。

理由：

- 现有 HTTP backend 已能透传 `filters`，无需重写后端适配层。
- preview 已隔离到 `18766`，可以独立验证 hybrid/vector。
- 改动范围集中在 UI、RPC 参数透传、agent 工具 schema、preview runtime 配置。
- 避免把本轮扩大成 `opensquilla-knowledge` 服务端任务系统。

## 架构

保持当前调用链：

```text
KnowledgeView.vue
  -> gateway RPC: knowledge.search/status/get
  -> HttpKnowledgeBackend
  -> opensquilla-knowledge-preview: /v1/search /v1/status
```

这轮不让 OpenSquilla 直接读取 `knowledge.db`，不把 embedding 逻辑放进 OpenSquilla gateway。

新增或调整的数据边界：

```text
indexProfile = "sqlite_fts5_default"

retrievalProfile =
  | "sqlite_fts5_default"
  | "vector_bge_m3_1024"
  | "hybrid_rrf_bge_m3_fts5"
```

`knowledge.ingest` 只使用 `indexProfile`：

```json
{
  "indexProfiles": ["sqlite_fts5_default"]
}
```

`knowledge.search` 使用 `retrievalProfile`：

```json
{
  "query": "用户问题",
  "topK": 8,
  "collectionId": "datasets",
  "retrievalProfile": "hybrid_rrf_bge_m3_fts5"
}
```

## 前端设计

文件：

- `opensquilla-webui/src/views/KnowledgeView.vue`

### 类型扩展

`KnowledgeStatus` 增加可选字段：

```ts
vectorChunksIndexed?: number
vectorCoveragePct?: number
embeddingModel?: string
embeddingDimensions?: number
embeddingWarnings?: string[]
retrievalWarnings?: string[]
```

`KnowledgeResult` 增加可选字段：

```ts
vectorRank?: number | null
vectorScore?: number | null
fusionScore?: number | null
```

字段全部可选，保证 U1-U4 shared service 没有这些字段时 UI 不崩。

### 状态变量

把当前单一 `retrievalProfile` 拆成：

```ts
const indexProfile = ref('sqlite_fts5_default')
const retrievalProfile = ref('sqlite_fts5_default')
```

`prepareSample()` 使用 `indexProfile`：

```ts
indexProfiles: [indexProfile.value]
```

`runSearch()` 使用 `retrievalProfile`：

```ts
retrievalProfile: retrievalProfile.value
```

### 检索模式控件

现有 `Retrieval` 下拉框扩展为：

```text
SQLite FTS5        sqlite_fts5_default
Vector bge-m3     vector_bge_m3_1024
Hybrid RRF        hybrid_rrf_bge_m3_fts5
```

控件仍位于现有 RAG 页面，不新增页面。

### 状态指标

当前状态卡片保留：

- RAG
- Files
- Chunks
- Questions
- Tools
- Index

新增或替换为更有价值的指标时，应保持 6 个以内，避免页面密度失控。建议把 `Index` 指标改为更能反映新能力的组合：

- `Vector`：`vectorCoveragePct`，无字段时显示 `-`
- `Embedding`：`baai/bge-m3 · 1024d`，无字段时显示 `not indexed`

如果实现中保持原 6 卡限制更方便，可以把 `Vector` 与 `Embedding` 放在 source summary 或 index hint 中，原则是 preview 页面能直接看到向量覆盖率和 embedding 模型。

### 结果展示

结果卡片不再固定写 `lexical {{ fixed(result.score) }}`。新增一个格式化 helper，根据结果字段决定展示：

- FTS：
  - 主分数：`lexical ${fixed(score)}`
  - meta：`BM25 ${fixed(bm25Rank)}`
- Vector：
  - 主分数：`vector ${fixed(vectorScore)}`
  - meta：`Vector #${vectorRank}`
- Hybrid：
  - 主分数：`fusion ${fixed(fusionScore || score)}`
  - meta：`BM25 ${fixed(bm25Rank)}`、`Vector #${vectorRank}`、`Vector score ${fixed(vectorScore)}`

### 慢查询提示

`searching` 状态保留。显示文案按 profile 区分：

- FTS：`Searching`
- Vector/Hybrid：`Embedding retrieval`

这轮不实现取消、轮询或请求进度条。

## Gateway RPC 设计

文件：

- `src/opensquilla/gateway/rpc_knowledge.py`

`knowledge.search` 保持现有行为，并增加顶层参数透传：

- `embeddingModel`
- `embeddingDimensions`
- `model`
- `dimensions`

合并规则：

- `filters` 仍可传任意服务端支持字段。
- 顶层字段优先覆盖 `filters` 中的同名字段。
- `collectionId` 和 `retrievalProfile` 的现有行为不变。

这让 UI 和后续调用方可以显式设置 embedding 参数，而不需要直接构造 filters。

## Agent 工具设计

文件：

- `src/opensquilla/tools/builtin/knowledge_tools.py`

`knowledge_search` 新增参数：

```text
collection_id?: string
retrieval_profile?: string
```

保留 `collection` 参数兼容旧调用。合并规则：

1. 从 `filters` 复制出新 dict，避免原地修改调用方对象。
2. 如果 `collection_id` 存在，写入 `filters.collectionId`。
3. 如果只有 `collection` 存在，也写入 `filters.collectionId`。
4. 如果 `retrieval_profile` 存在，写入 `filters.retrievalProfile`。
5. 调用 `resolved_manager.search(clean_query, top_k=top_k, filters=merged_filters)`。

工具描述中列出支持的 profile：

- `sqlite_fts5_default`
- `vector_bge_m3_1024`
- `hybrid_rrf_bge_m3_fts5`

## Preview 配置设计

只改 preview runtime：

- `/srv/opensquilla-demo/instances/preview/runtime-gateway.toml`

调整：

```toml
[knowledge]
timeout_seconds = 90.0
```

不改：

- `/srv/opensquilla-demo/instances/u1/runtime-gateway.toml`
- `/srv/opensquilla-demo/instances/u2/runtime-gateway.toml`
- `/srv/opensquilla-demo/instances/u3/runtime-gateway.toml`
- `/srv/opensquilla-demo/instances/u4/runtime-gateway.toml`
- `/etc/systemd/system/opensquilla-demo@.service`

修改后只重启：

```bash
systemctl restart opensquilla-demo@preview
```

## 错误处理

1. UI 复用现有 `error` 区域展示 RPC/HTTP 错误。
2. Vector/Hybrid 查询失败时，用户看到现有错误提示，不新增复杂错误面板。
3. U1-U4 服务无 vector 字段时，前端使用 fallback 展示，不报错。
4. 本轮不处理服务端 warning 展示；如果服务端返回 `warnings`，后续可以在结果区增加提示条。
5. 慢查询通过 preview timeout 临时缓解，不在本轮实现取消/轮询。

## 测试设计

### Python 测试

文件：

- `tests/test_knowledge/test_rpc_knowledge.py`
- `tests/test_knowledge/test_tools.py`
- `tests/test_knowledge/test_http_backend.py`

测试点：

1. `knowledge.search` 会把 `retrievalProfile`、`embeddingModel`、`embeddingDimensions` 合并进 filters。
2. 顶层 search 参数优先覆盖 filters 中同名字段。
3. `knowledge_search` 工具会把 `collection_id` / `collection` / `retrieval_profile` 转成 backend filters。
4. `HttpKnowledgeBackend.search()` 继续发送 `{query, topK, filters}`，避免协议回退。

### 前端测试

文件建议：

- `opensquilla-webui/src/views/KnowledgeView.retrieval.test.ts`

如果直接 mount `KnowledgeView.vue` 成本过高，则先抽出轻量 helper：

- `opensquilla-webui/src/views/knowledgeRetrieval.ts`

helper 负责：

- retrieval profile 选项列表
- status metric fallback
- result score label/meta formatting

测试点：

1. profile 选项包含 FTS、Vector、Hybrid。
2. ingest payload 使用 `indexProfile`，不使用 hybrid/vector retrieval profile。
3. search payload 使用当前 `retrievalProfile`。
4. hybrid 结果格式化包含 `fusionScore`、`bm25Rank`、`vectorRank`。
5. vector 结果格式化包含 `vectorScore`、`vectorRank`。
6. 缺少 vector status 字段时 fallback 不报错。

## 验证命令

Python：

```bash
cd /root/Q3WORK/opensquilla-knowledge-rag-phase01
pytest tests/test_knowledge/test_rpc_knowledge.py tests/test_knowledge/test_tools.py tests/test_knowledge/test_http_backend.py -q
```

前端：

```bash
cd /root/Q3WORK/opensquilla-knowledge-rag-phase01/opensquilla-webui
npm run test:unit -- KnowledgeView
npm run typecheck
```

preview 配置：

```bash
grep -nA8 -B2 '^\[knowledge\]' /srv/opensquilla-demo/instances/preview/runtime-gateway.toml
grep -nA8 -B2 '^\[knowledge\]' /srv/opensquilla-demo/instances/u1/runtime-gateway.toml
systemctl restart opensquilla-demo@preview
systemctl is-active opensquilla-demo@preview opensquilla-demo@u1 opensquilla-demo@u2 opensquilla-demo@u3 opensquilla-demo@u4
```

服务探针：

```bash
curl -fsS http://127.0.0.1:18766/v1/status | python3 -m json.tool
curl -fsS -X POST http://127.0.0.1:18766/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"苹果公司收入","topK":2,"filters":{"collectionId":"datasets","retrievalProfile":"sqlite_fts5_default"}}' \
  | python3 -m json.tool
```

Hybrid/vector direct probe 可能仍受 OpenRouter 延迟影响，本轮不把其稳定低延迟作为完成条件；完成条件是 OpenSquilla 能正确表达参数、展示字段、preview timeout 已放宽。

## 发布和回滚

发布：

1. 在 `opensquilla-knowledge-rag-phase01` 分支完成代码改动并提交。
2. 构建前端静态资源。
3. 更新 preview 当前工作目录。
4. 调整 preview runtime timeout。
5. 重启 `opensquilla-demo@preview`。

回滚：

1. 回退 OpenSquilla 代码提交。
2. 恢复 preview `timeout_seconds = 30.0`。
3. 重启 `opensquilla-demo@preview`。

U1-U4 未改 endpoint、服务模板或 runtime，因此不需要客户侧回滚动作。

## 成功标准

1. preview RAG 页面能选择 FTS、Vector、Hybrid。
2. 点击构建知识库时，只发送 `indexProfiles: ["sqlite_fts5_default"]`。
3. 点击搜索时，发送当前 `retrievalProfile`。
4. preview 页面能展示 vector coverage 和 embedding model。
5. hybrid/vector 返回结果时，页面能展示对应分数和 rank 字段。
6. agent 工具 schema 明确暴露 `collection_id` 和 `retrieval_profile`。
7. preview timeout 为 90 秒，U1-U4 timeout 和 endpoint 不变。
8. 相关 Python 测试、前端单测、前端 typecheck 通过。
