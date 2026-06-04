# Web AI 配置说明

这个目录记录 Web 页面调用 AI 的配置方式。真实密钥不要写进代码，也不要提交到仓库。

## OpenAI / DeepSeek 兼容接口

在 `web_app/.env` 中配置：

```text
WEB_AI_PROVIDER=openai
WEB_AI_API_KEY=你的密钥
WEB_AI_BASE_URL=https://api.deepseek.com/v1
WEB_AI_MODEL=deepseek-chat
```

## Anthropic Messages 兼容接口

如果服务商使用 Anthropic Messages 格式，可以配置：

```text
WEB_AI_PROVIDER=anthropic
WEB_AI_API_KEY=你的密钥
ANTHROPIC_AUTH_TOKEN=你的密钥
WEB_AI_BASE_URL=https://example.com
WEB_AI_MODEL=your-model
```

## 通用变量

也可以使用根目录 `.env` 的通用变量：

```text
OPENAI_API_KEY=你的密钥
OPENAI_BASE_URL=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat
```

或：

```text
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

## 调用规则

- 页面默认不调用模型。
- 勾选“AI智能分析”并提交时，才会调用模型补充候选人评价。
- 点击“写汇总报告”时，才会基于本次结果调用模型生成汇总报告。
- 没有配置密钥时，本地规则分析仍可正常使用。
