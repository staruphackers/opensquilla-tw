# Squilla Router Provider 模型矩阵与工具统计

本文档整理当前仓库内置和新增的 Squilla Router provider 档位配置。本文不记录任何 API key 明文。

## 结论

已配置两类 router 档位：

- `tier_profile`：legacy provider 中已有的可持久化 Squilla Router 预置。文档只展示当前要启用和维护的 provider。
- `synthesized inline preset`：非 legacy provider 的内联档位。不会写成 `squilla_router.tier_profile`，保存时展开成 `squilla_router.tiers`，避免旧版本配置校验失败。

## 事实

- OpenRouter C3 已配置为 `anthropic/claude-opus-4.8`；Gateway E2E 的实际请求模型为 `anthropic/claude-opus-4.8`，返回模型为 `anthropic/claude-4.8-opus-20260528`。
- `C:\projects\keys\api.keys` 中未明文记录任何输出到本文档的 key；Gateway E2E 通过运行时环境实际访问了 OpenRouter、DashScope、DeepSeek、Moonshot、OpenAI、Qianfan、Volcengine、Zhipu、MiniMax、Kimi Coding、MiMo 等 provider。
- 当前 key 文件里 `OPENROUTER_API_KEY` 已非空；OpenRouter C0-C3 已获得真实 LLM 回复。
- Moonshot 当前 key 需要 key 文件中的 `MOONSHOT_BASE_URL=https://api.moonshot.cn/v1` 才能 smoke 通过；registry 默认 `https://api.moonshot.ai/v1` 对这把 key 返回 401。
- Kimi Coding 和 MiMo Coding 在 key 文件中是自由文本小节；代码不会解析自由文本 key，因此新增 provider 使用显式 env var：`KIMI_CODING_API_KEY`、`MIMO_API_KEY`。
- Volcengine 普通 Ark endpoint 可用；Coding Plan 使用独立 `VOLCENGINE_CODING_API_KEY` 和 `https://ark.cn-beijing.volces.com/api/plan/v3`，低 token smoke 已通过。
- Google Gemini 官方 OpenAI-compatible 文档使用 `https://generativelanguage.googleapis.com/v1beta/openai/`；当前 Gateway 配置与此一致，但本地 Gemini key 在四档 E2E 中均返回 `Please pass a valid API key`。
- Kimi Code 官方文档要求 OpenAI-compatible base URL 使用 `https://api.kimi.com/coding/v1`，Anthropic-compatible base URL 使用 `https://api.kimi.com/coding/`，并且两种协议都统一使用固定模型 ID `kimi-for-coding`。
- MiniMax 官方 OpenAI-compatible 文档要求 base URL `https://api.minimax.io/v1`，Chat Completions endpoint 为 `https://api.minimax.io/v1/chat/completions`；普通 `minimax_openai` 的 registry 默认值已从旧的 `https://api.minimaxi.com/v1` 改为 `https://api.minimax.io/v1`。
- 直连官方 endpoint 已证明 URL 可达：当前这把普通 `MINIMAX_API_KEY` 返回 401 `invalid api key (2049)`，不是 URL 404；但 Gateway 四档复测路径仍记录为 404。因此当前支持版本应使用已逐档调通的 MiniMax Anthropic-compatible，不把普通 `minimax_openai` 纳入已调通支持集。
- 小米 MiMo 官网公开展示 `Xiaomi MiMo-V2.5`、`Xiaomi MiMo-V2.5-Pro` 和 `API Access` 入口；当前未找到可访问的官方 OpenAI/Anthropic endpoint 细节文档。
- Claude 外部审阅未成功：本机 `claude` 启动脚本依赖的临时 `npx.cmd` 已不存在，未获得可用审阅输出。

## 推断

- Qianfan 目前只验证到 `ernie-4.5-turbo-128k` 文本模型和 `ernie-4.5-turbo-vl-32k` 视觉模型，因此文本四档先统一使用 `ernie-4.5-turbo-128k`。
- MiniMax 不再使用 `MiniMax-M2.7-highspeed`；c0/c1 使用 `MiniMax-M2.7`，c2/c3 使用 `MiniMax-M3`。
- MiMo 当前 router 档位来自本地 key / Gateway 实测口径：`mimo-v2.5` 作为 c0/c1，`mimo-v2.5-pro` 作为 c2/c3；这不是公开官方 endpoint 文档确认结果。
- `minimax_coding_openai` 仍保留 `https://api.minimaxi.com/v1`，因为这组 Coding Plan key 在 Gateway 四档中已真实返回；不能把普通 `minimax_openai` 的官方 global URL 修正反向套用到这组已实测可用的 coding key。

## 限制与未知

- Gemini 当前本地 key 返回 invalid API key，因此 Gemini 3.x 档位来自前序文档/代码配置，不是这把 key 的 live smoke 结果。
- Qianfan `/models` 返回 rate limit，模型可用性来自 chat smoke，而不是完整模型列表。
- Kimi/MiMo/Volcengine Coding Plan 的官方计费、上下文窗口和工具调用细节未在代码中固化；当前 catalog 只记录模型身份、reasoning/tool/vision 能力和已确认的 Qianfan VL 视觉能力。
- Kimi Coding OpenAI-compatible 和 MiMo OpenAI-compatible 在非受限网络权限下已复测通过；此前连接失败是当前 shell/sandbox 网络限制，不是 provider 配置失败。
- MiniMax OpenAI-compatible 在非受限网络权限下仍返回 404；不能纳入当前 key 的已调通支持版本。
- MiMo 的公开官方 API endpoint 文档未找到，因此 MiMo OpenAI/Anthropic endpoint 仍属于实测配置，不属于官方文档确认配置。

## Gateway E2E 验证状态（2026-07-10）

验证方式：通过本地 Gateway 对每个 provider 的 c0/c1/c2/c3 逐档真实请求，要求获得真实 LLM 回复，并把 raw JSON 证据落盘。

证据目录：
- 全量 80 档验证：`tmp\gateway_matrix_e2e_20260710_full2\summary.json`、`tmp\gateway_matrix_e2e_20260710_full2\report.md`、`tmp\gateway_matrix_e2e_20260710_full2\raw\*.json`
- Kimi/MiMo OpenAI parser 修复后复测：`tmp\gateway_matrix_e2e_20260710_patch_verify\summary.json`
- MiniMax OpenAI 官方 URL 修正后复测：`tmp\gateway_matrix_e2e_20260710_minimax_openai_fix\summary.json`
- MiniMax OpenAI 官方 URL 直连复核：`tmp\minimax_openai_url_check_20260710.json`
- 非受限网络下的调通复测：`tmp\gateway_matrix_e2e_20260710_tune2_escalated\summary.json`
- Kimi Coding OpenAI c0 单独重试：`tmp\gateway_matrix_e2e_20260710_kimi_openai_c0_retry\summary.json`

总体结果：

| 指标 | 结果 | 说明 |
| --- | ---: | --- |
| 全量 case | 80 | 20 个 provider × 4 档。 |
| 获得真实 LLM 回复 | 64/80 | 以 `assistant_text` 非空为准。 |
| 严格 runner 通过 | 59/80 | 严格检查包含 marker、tier metadata 等；OpenRouter 有真实回复但 strict 不通过。 |
| 完全无回复失败 | 16/80 | Gemini 4、Kimi Coding OpenAI 4、MiMo OpenAI 4、MiniMax OpenAI 4。 |

调通复测结果：

| provider | 调通结果 | 证据 |
| --- | ---: | --- |
| `kimi_coding_openai` | 4/4 | `tmp\gateway_matrix_e2e_20260710_tune2_escalated\summary.json` 中 c1-c3 通过；`tmp\gateway_matrix_e2e_20260710_kimi_openai_c0_retry\summary.json` 中 c0 通过。 |
| `kimi_coding_anthropic` | 4/4 | `tmp\gateway_matrix_e2e_20260710_tune2_escalated\summary.json` |
| `mimo_openai` | 4/4 | `tmp\gateway_matrix_e2e_20260710_tune2_escalated\summary.json` |
| `mimo_anthropic` | 4/4 | `tmp\gateway_matrix_e2e_20260710_tune2_escalated\summary.json` |
| `minimax` | 4/4 | `tmp\gateway_matrix_e2e_20260710_tune2_escalated\summary.json` |
| `minimax_global` | 4/4 | `tmp\gateway_matrix_e2e_20260710_tune2_escalated\summary.json` |
| `minimax_openai` | 0/4 | Gateway 四档均为 `HTTP 404: 404 page not found`；直连官方 endpoint 返回 401 `invalid api key (2049)`，说明 URL 本身可达。 |
| `gemini` | 0/4 | 同一证据目录中四档均为 `Please pass a valid API key`。 |

Provider 汇总：

| provider | 严格通过 | 真实回复 | 当前判定 |
| --- | ---: | ---: | --- |
| `openrouter` | 0/4 | 4/4 | 请求和回复真实有效；strict 失败来自 marker/tier metadata，不是模型不可达。 |
| `dashscope` | 4/4 | 4/4 | 通过。 |
| `deepseek` | 4/4 | 4/4 | 通过。 |
| `gemini` | 0/4 | 0/4 | 官方 base URL 正确；当前 key invalid。 |
| `moonshot` | 4/4 | 4/4 | 通过，依赖本地 `MOONSHOT_BASE_URL=https://api.moonshot.cn/v1`。 |
| `openai` | 4/4 | 4/4 | GPT-5 系列四档通过。 |
| `volcengine` | 4/4 | 4/4 | 普通 Ark 四档通过。 |
| `zhipu` | 4/4 | 4/4 | 通过。 |
| `volcengine_coding_plan` | 4/4 | 4/4 | Coding Plan 四档通过。 |
| `minimax_coding_openai` | 4/4 | 4/4 | Coding Plan OpenAI-compatible 四档通过。 |
| `minimax_coding_anthropic` | 4/4 | 4/4 | Coding Plan Anthropic-compatible 四档通过。 |
| `kimi_coding_openai` | 4/4 | 4/4 | 官方配置正确；非受限网络复测后四档通过。 |
| `kimi_coding_anthropic` | 4/4 | 4/4 | Anthropic-compatible 四档通过。 |
| `mimo_openai` | 4/4 | 4/4 | parser 问题已修；非受限网络复测后四档通过。 |
| `mimo_anthropic` | 4/4 | 4/4 | 非受限网络复测后四档通过。 |
| `qianfan` | 4/4 | 4/4 | 通过。 |
| `minimax` | 4/4 | 4/4 | Anthropic-compatible 四档通过。 |
| `minimax_openai` | 0/4 | 0/4 | Gateway 路径复测 404；直连官方 URL 为 401 `invalid api key (2049)`；不纳入当前 key 的支持版本。 |
| `minimax_cn` | 4/4 | 4/4 | Anthropic-compatible 四档通过。 |
| `minimax_global` | 4/4 | 4/4 | Anthropic-compatible global 四档通过。 |

失败复核：

| provider | 档位 | 失败证据 | 当前处理 |
| --- | --- | --- | --- |
| `gemini` | c0-c3 | `tmp\gateway_matrix_e2e_20260710_full2\raw\gemini__*.json` 返回 `Please pass a valid API key` | 保留官方 base URL，等待有效 `GEMINI_API_KEY`。 |
| `kimi_coding_openai` | c0-c3 | full run 为空响应；修复后受限网络连接失败；非受限网络下四档通过 | 已调通；官方要求固定 `kimi-for-coding`。 |
| `mimo_openai` | c0-c3 | full run 触发 `tool_calls: null` parser 问题；修复后受限网络连接失败；非受限网络下四档通过 | 已调通；endpoint 仍为实测配置，公开官方 endpoint 文档未找到。 |
| `minimax_openai` | c0-c3 | full run 旧 `api.minimaxi.com/v1` 返回 404；改为官方 `api.minimax.io/v1` 后 Gateway 非受限网络仍返回 404；直连官方 endpoint 返回 401 `invalid api key (2049)` | 不纳入当前 key 的支持版本；使用 `minimax` / `minimax_global`。 |

## Provider Key 与验证状态

| 名称 | provider key | 后端形态 | env key | 默认 base_url | 状态 | router 配置 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OpenRouter | `openrouter` | OpenAI-compatible | `OPENROUTER_API_KEY` | `https://openrouter.ai/api/v1` | real-reply 4/4 | `tier_profile` | C3 请求 `anthropic/claude-opus-4.8`，返回 `anthropic/claude-4.8-opus-20260528`；strict 失败来自 marker/tier metadata。 |
| Aliyun DashScope | `dashscope` | OpenAI-compatible | `DASHSCOPE_API_KEY` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | real-reply 4/4 | `tier_profile` | Qwen 3.6/3.7 档位。 |
| DeepSeek | `deepseek` | OpenAI-compatible | `DEEPSEEK_API_KEY` | `https://api.deepseek.com` | real-reply 4/4 | `tier_profile` | DeepSeek V4 Flash/Pro。 |
| Moonshot AI | `moonshot` | OpenAI-compatible | `MOONSHOT_API_KEY` | `https://api.moonshot.ai/v1` | real-reply 4/4 with local base override | `tier_profile` | 当前 key 需 `MOONSHOT_BASE_URL=https://api.moonshot.cn/v1`；Kimi K2.6/K2.7 Code。 |
| OpenAI | `openai` | OpenAI-compatible | `OPENAI_API_KEY` | `https://api.openai.com/v1` | real-reply 4/4 | `tier_profile` | 改为当前 key 可用的 GPT-5 系列。 |
| OpenAI Responses | `openai_responses` | Responses API | `OPENAI_API_KEY` | `https://api.openai.com/v1` | supported | 无 | 直连 Responses API，不配置 Squilla Router 档位。 |
| Volcengine Ark | `volcengine` | OpenAI-compatible | `VOLCENGINE_API_KEY` | `https://ark.cn-beijing.volces.com/api/v3` | real-reply 4/4 | `tier_profile` | Doubao Seed 2.0 档位。 |
| Volcengine Coding Plan | `volcengine_coding_plan` | OpenAI-compatible | `VOLCENGINE_CODING_API_KEY` | `https://ark.cn-beijing.volces.com/api/plan/v3` | real-reply 4/4 | `synthesized inline preset` | key 文件中有独立火山 coding plan key；`/api/plan` 无 `/v3` 返回 404。 |
| Zhipu (Z.AI) | `zhipu` | OpenAI-compatible | `ZAI_API_KEY` | `https://open.bigmodel.cn/api/paas/v4` | real-reply 4/4 | `tier_profile` | GLM-5 系列档位。 |
| Baidu Qianfan | `qianfan` | OpenAI-compatible | `QIANFAN_API_KEY` | `https://qianfan.baidubce.com/v2` | chat-smoked | `synthesized inline preset` | 新增 Qianfan router 档位。 |
| Google Gemini | `gemini` | OpenAI-compatible | `GEMINI_API_KEY` | `https://generativelanguage.googleapis.com/v1beta/openai` | key invalid 0/4 | `tier_profile` | 官方 OpenAI-compatible base URL 匹配；当前 key 返回 invalid API key。 |
| MiniMax Anthropic-compatible | `minimax` | Anthropic-compatible | `MINIMAX_API_KEY` | `https://api.minimaxi.com/anthropic` | real-reply 4/4 | `synthesized inline preset` | 新增 MiniMax router 档位。 |
| MiniMax Mainland Anthropic-compatible | `minimax_cn` | Anthropic-compatible | `MINIMAX_CN_API_KEY` | `https://api.minimaxi.com/anthropic` | real-reply 4/4 | `synthesized inline preset` | 代码使用独立 env key；Gateway 四档已返回真实回复。 |
| MiniMax Global Anthropic-compatible | `minimax_global` | Anthropic-compatible | `MINIMAX_API_KEY` | `https://api.minimax.io/anthropic` | real-reply 4/4 | `synthesized inline preset` | 使用 MiniMax global Anthropic endpoint。 |
| MiniMax OpenAI-compatible | `minimax_openai` | OpenAI-compatible | `MINIMAX_API_KEY` | `https://api.minimax.io/v1` | not-supported-for-current-key 0/4 | `synthesized inline preset` | 官方 OpenAI-compatible URL 已修正且直连可达；当前普通 key 被官方 endpoint 判定为 invalid，推荐不用这一项。 |
| MiniMax Coding OpenAI-compatible | `minimax_coding_openai` | OpenAI-compatible | `MINIMAX_CODING_API_KEY` | `https://api.minimaxi.com/v1` | real-reply 4/4 | `synthesized inline preset` | Gateway 四档通过；不使用 highspeed。 |
| MiniMax Coding Anthropic-compatible | `minimax_coding_anthropic` | Anthropic-compatible | `MINIMAX_CODING_API_KEY` | `https://api.minimaxi.com/anthropic` | real-reply 4/4 | `synthesized inline preset` | Gateway 四档通过；不使用 highspeed。 |
| Kimi Coding OpenAI-compatible | `kimi_coding_openai` | OpenAI-compatible | `KIMI_CODING_API_KEY` | `https://api.kimi.com/coding/v1` | real-reply 4/4 | `synthesized inline preset` | 官方 endpoint 和固定模型 ID 正确；非受限网络四档通过。 |
| Kimi Coding Anthropic-compatible | `kimi_coding_anthropic` | Anthropic-compatible | `KIMI_CODING_API_KEY` | `https://api.kimi.com/coding` | real-reply 4/4 | `synthesized inline preset` | 官方 endpoint 和固定模型 ID 正确；Gateway 四档通过。 |
| MiMo OpenAI-compatible | `mimo_openai` | OpenAI-compatible | `MIMO_API_KEY` | `https://token-plan-cn.xiaomimimo.com/v1` | real-reply 4/4 | `synthesized inline preset` | parser 已修；非受限网络四档通过；公开官方 endpoint 文档未找到。 |
| MiMo Anthropic-compatible | `mimo_anthropic` | Anthropic-compatible | `MIMO_API_KEY` | `https://token-plan-cn.xiaomimimo.com/anthropic` | real-reply 4/4 | `synthesized inline preset` | `/models` 不可用；Gateway Anthropic messages 四档通过。 |

## Coding Plan 核对

| 目标 | 当前状态 | provider key | 协议形态 | 默认 base_url | 结论 |
| --- | --- | --- | --- | --- | --- |
| MiniMax Coding | 已新增 | `minimax_coding_openai`, `minimax_coding_anthropic` | OpenAI-compatible / Anthropic-compatible | `https://api.minimaxi.com/v1`, `https://api.minimaxi.com/anthropic` | 使用 `MINIMAX_CODING_API_KEY`；两种协议 Gateway 四档均有真实回复；档位不使用 highspeed。 |
| 火山引擎 | 普通 Ark 和 Coding Plan 均已落地 | `volcengine`, `volcengine_coding_plan` | OpenAI-compatible | `https://ark.cn-beijing.volces.com/api/v3`, `https://ark.cn-beijing.volces.com/api/plan/v3` | `volcengine_coding_plan` 使用独立 key，Seed 2.0 模型 chat smoke 通过。 |
| Kimi Coding | 已新增 | `kimi_coding_openai`, `kimi_coding_anthropic` | OpenAI-compatible / Anthropic-compatible | `https://api.kimi.com/coding/v1`, `https://api.kimi.com/coding` | 官方要求固定 `kimi-for-coding`；两种协议四档均已调通。 |
| MiMo Coding | 已新增 | `mimo_openai`, `mimo_anthropic` | OpenAI-compatible / Anthropic-compatible | `https://token-plan-cn.xiaomimimo.com/v1`, `https://token-plan-cn.xiaomimimo.com/anthropic` | 两种协议四档均已调通；公开官方 endpoint 文档未找到。 |

## 原有支持模型

| provider | 默认模型 | c0 | c1 | c2 | c3 | image_model |
| --- | --- | --- | --- | --- | --- | --- |
| dashscope | `qwen3.6-plus` | `qwen3.6-flash` | `qwen3.6-plus` | `qwen3-max` | `qwen3-max` | - |
| deepseek | `deepseek-v4-flash` | `deepseek-v4-flash` | `deepseek-v4-flash` | `deepseek-v4-pro` | `deepseek-v4-pro` | - |
| gemini | `gemini-2.5-flash` | `gemini-2.5-flash-lite` | `gemini-2.5-flash` | `gemini-2.5-pro` | `gemini-2.5-pro` | - |
| moonshot | `kimi-k2.5` | `kimi-k2.5` | `kimi-k2.5` | `kimi-k2.6` | `kimi-k2.6` | - |
| openai | `gpt-5.4-mini` | `gpt-5.4-nano` | `gpt-5.4-mini` | `gpt-5.5` | `gpt-5.5` | - |
| openrouter | `deepseek/deepseek-v4-pro` | `deepseek/deepseek-v4-flash` | `deepseek/deepseek-v4-pro` | `z-ai/glm-5.2` | `z-ai/glm-5.2` | `moonshotai/kimi-k2.6` |
| volcengine | `doubao-seed-2-0-lite-260215` | `doubao-seed-2-0-mini-260215` | `doubao-seed-2-0-lite-260215` | `doubao-seed-2-0-pro-260215` | `doubao-seed-2-0-code-preview-260215` | - |
| zhipu | `glm-5` | `glm-4.7-flashx` | `glm-5` | `glm-5.1` | `glm-5.1` | - |

## 当前配置后的支持模型

阅读口径：
- `tier_profile`：可持久化到 `squilla_router.tier_profile` 的 legacy 路由预置。
- `synthesized inline preset`：运行时内联预置；保存配置时展开为 `squilla_router.tiers`。

### 核心 `tier_profile`（当前 key 已调通）

| provider | default | c0 / c1 | c2 / c3 | image |
| --- | --- | --- | --- | --- |
| `openrouter` | `deepseek/deepseek-v4-pro` | `deepseek/deepseek-v4-flash` / `deepseek/deepseek-v4-pro` | `z-ai/glm-5.2` / `anthropic/claude-opus-4.8` | `moonshotai/kimi-k2.6` |
| `dashscope` | `qwen3.7-plus` | `qwen3.6-flash` / `qwen3.7-plus` | `qwen3.7-max` / `qwen3.7-max` | - |
| `deepseek` | `deepseek-v4-flash` | `deepseek-v4-flash` / `deepseek-v4-flash` | `deepseek-v4-pro` / `deepseek-v4-pro` | - |
| `moonshot` | `kimi-k2.6` | `kimi-k2.6` / `kimi-k2.6` | `kimi-k2.6` / `kimi-k2.7-code` | - |
| `openai` | `gpt-5.4-mini` | `gpt-5.4-nano` / `gpt-5.4-mini` | `gpt-5.5` / `gpt-5.5` | - |
| `volcengine` | `doubao-seed-2-0-lite-260215` | `doubao-seed-2-0-lite-260215` / `doubao-seed-2-0-lite-260215` | `doubao-seed-2-0-pro-260215` / `doubao-seed-2-0-pro-260215` | - |
| `zhipu` | `glm-5` | `glm-5-turbo` / `glm-5` | `glm-5.1` / `glm-5.2` | - |

### Coding Plan / Coding Provider

| provider | protocol | default | c0 / c1 | c2 / c3 |
| --- | --- | --- | --- | --- |
| `volcengine_coding_plan` | OpenAI-compatible | `doubao-seed-2-0-pro-260215` | `doubao-seed-2-0-lite-260215` / `doubao-seed-2-0-pro-260215` | `doubao-seed-2-0-code-preview-260215` / `doubao-seed-2-0-code-preview-260215` |
| `minimax_coding_openai` | OpenAI-compatible | `MiniMax-M2.7` | `MiniMax-M2.7` / `MiniMax-M2.7` | `MiniMax-M3` / `MiniMax-M3` |
| `minimax_coding_anthropic` | Anthropic-compatible | `MiniMax-M2.7` | `MiniMax-M2.7` / `MiniMax-M2.7` | `MiniMax-M3` / `MiniMax-M3` |
| `kimi_coding_openai` | OpenAI-compatible | `kimi-for-coding` | `kimi-for-coding` / `kimi-for-coding` | `kimi-for-coding` / `kimi-for-coding` |
| `kimi_coding_anthropic` | Anthropic-compatible | `kimi-for-coding` | `kimi-for-coding` / `kimi-for-coding` | `kimi-for-coding` / `kimi-for-coding` |
| `mimo_openai` | OpenAI-compatible | `mimo-v2.5` | `mimo-v2.5` / `mimo-v2.5` | `mimo-v2.5-pro` / `mimo-v2.5-pro` |
| `mimo_anthropic` | Anthropic-compatible | `mimo-v2.5` | `mimo-v2.5` / `mimo-v2.5` | `mimo-v2.5-pro` / `mimo-v2.5-pro` |

### 其他内联路由

| provider | protocol | default | c0 / c1 | c2 / c3 | image |
| --- | --- | --- | --- | --- | --- |
| `qianfan` | OpenAI-compatible | `ernie-4.5-turbo-128k` | `ernie-4.5-turbo-128k` / `ernie-4.5-turbo-128k` | `ernie-4.5-turbo-128k` / `ernie-4.5-turbo-128k` | `ernie-4.5-turbo-vl-32k` |
| `minimax` | Anthropic-compatible | `MiniMax-M2.7` | `MiniMax-M2.7` / `MiniMax-M2.7` | `MiniMax-M3` / `MiniMax-M3` | - |
| `minimax_cn` | Anthropic-compatible | `MiniMax-M2.7` | `MiniMax-M2.7` / `MiniMax-M2.7` | `MiniMax-M3` / `MiniMax-M3` | - |
| `minimax_global` | Anthropic-compatible | `MiniMax-M2.7` | `MiniMax-M2.7` / `MiniMax-M2.7` | `MiniMax-M3` / `MiniMax-M3` | - |

当前不纳入支持版本：

| provider | 原因 | 证据 |
| --- | --- | --- |
| `gemini` | 当前 `GEMINI_API_KEY` 被官方 OpenAI-compatible endpoint 拒绝，错误为 `Please pass a valid API key`。 | `tmp\gateway_matrix_e2e_20260710_tune2_escalated\raw\gemini__*.json` |
| `minimax_openai` | 官方 OpenAI-compatible URL 直连可达，但当前普通 `MINIMAX_API_KEY` 返回 401 `invalid api key (2049)`；Gateway 四档路径仍记录 404；同一 key 的 Anthropic-compatible `minimax` / `minimax_global` 已调通。 | `tmp\minimax_openai_url_check_20260710.json`；`tmp\gateway_matrix_e2e_20260710_tune2_escalated\raw\minimax_openai__*.json` |

## 工具统计

本节统计 `src/opensquilla/tools/builtin` 下的内置工具。顶层工具会在 `opensquilla.tools` 导入内置模块时注册。嵌套的启动时工具在源码中定义，但需要 memory、session storage、skill loader 等运行时服务工厂后才会注册。

### 工具数量

| 指标 | 数量 | 说明 |
| --- | ---: | --- |
| 静态 `@tool(...)` 装饰器 | 82 | 源码中发现的全部内置工具装饰器。 |
| 顶层默认注册工具 | 69 | 通过默认导入 `opensquilla.tools` 注册。 |
| 嵌套启动时服务注入工具 | 13 | memory、session search 和 skill 相关工具。 |
| 默认可见的已注册工具 | 64 | 除非 profile 或运行时策略过滤，否则默认可见。 |
| 默认隐藏的已注册工具 | 5 | `canvas`, `create_pptx`, `meta_invoke`, `nodes`, `subagents`. |
| 默认 owner-only 工具 | 3 | `gateway`, `git_commit`, `http_request`. |
| 默认 external-budget 工具 | 4 | `http_request`, `web_discover`, `web_fetch`, `web_search`. |

### 默认注册工具按模块统计

| 模块 | 数量 | 工具 |
| --- | ---: | --- |
| `admin` | 2 | `cron`, `gateway` |
| `agents` | 2 | `agents_list`, `subagents` |
| `artifacts` | 1 | `publish_artifact` |
| `code_exec` | 1 | `execute_code` |
| `feishu_platform` | 16 | `feishu_doc_create`, `feishu_doc_read_raw`, `feishu_doc_list_blocks`, `feishu_scopes_status`, `feishu_chat_send`, `feishu_chat_reply`, `feishu_chat_read`, `feishu_chat_edit`, `feishu_drive_search`, `feishu_drive_meta`, `feishu_drive_upload_artifact`, `feishu_wiki_list_spaces`, `feishu_wiki_list_nodes`, `feishu_wiki_get_node`, `feishu_perm_grant_member`, `feishu_media_upload_artifact` |
| `file_authoring` | 4 | `create_csv`, `create_xlsx`, `create_pptx`, `create_pdf_report` |
| `filesystem` | 7 | `read_file`, `read_spreadsheet`, `write_file`, `edit_file`, `list_dir`, `glob_search`, `grep_search` |
| `git` | 4 | `git_status`, `git_diff`, `git_commit`, `git_log` |
| `media` | 13 | `image`, `image_generate`, `pdf`, `voice_clone`, `voice_convert`, `dubbing_generate`, `dubbing_status`, `dubbing_download`, `music_generate`, `song_generate`, `audio_provider_capabilities`, `voice_search`, `tts` |
| `messaging` | 1 | `message` |
| `meta_tools` | 1 | `meta_invoke` |
| `nodes` | 2 | `canvas`, `nodes` |
| `patch` | 1 | `apply_patch` |
| `router_control` | 1 | `router_control` |
| `sessions` | 6 | `sessions_send`, `sessions_spawn`, `sessions_list`, `sessions_history`, `sessions_yield`, `session_status` |
| `shell` | 3 | `exec_command`, `background_process`, `process` |
| `web` | 3 | `http_request`, `web_search`, `web_discover` |
| `web_fetch` | 1 | `web_fetch` |

### 启动时服务注入工具

| 模块 | 数量 | 工具 |
| --- | ---: | --- |
| `memory_tools` | 4 | `memory_search`, `memory_save`, `memory_get`, `memory_delete` |
| `session_search` | 1 | `session_search` |
| `skill_tools` | 8 | `skill_list`, `skill_view`, `skill_search_community`, `skill_install_community`, `install_skill_deps`, `skill_create`, `skill_edit`, `skill_delete` |
