# Job Fit Agent Web

这是项目的 FastAPI Web 页面版本，负责简历上传、JD 输入、批量匹配分析、结果展示和报告导出。

## 功能

- 粘贴或上传岗位 JD。
- 批量上传 `.docx`、`.pdf`、`.doc` 简历。
- 展示候选人的匹配分、排名、优势、短板和改进建议。
- 导出 JSON、Markdown、Word 详细报告和 Excel 排名表。
- 勾选“AI智能分析”后调用模型补充候选人评价。
- 点击“写汇总报告”后在网页内生成批量筛选报告。
- 默认只运行本地规则，不会自动调用 AI。

## 启动

在项目根目录安装依赖：

```bash
pip install -r requirements.txt
```

启动服务：

```bash
uvicorn web_app.main:app --reload
```

打开：

```text
http://127.0.0.1:8000
```

## AI 配置

如需启用 AI，在 `web_app/.env` 中配置：

```text
WEB_AI_PROVIDER=openai
WEB_AI_API_KEY=你的密钥
WEB_AI_BASE_URL=https://api.deepseek.com/v1
WEB_AI_MODEL=deepseek-chat
```

也支持 Anthropic Messages 兼容接口：

```text
WEB_AI_PROVIDER=anthropic
WEB_AI_API_KEY=你的密钥
ANTHROPIC_AUTH_TOKEN=你的密钥
WEB_AI_BASE_URL=https://example.com
WEB_AI_MODEL=your-model
```

## 目录结构

```text
web_app/
  main.py              # FastAPI 后端入口
  templates/           # Jinja2 HTML 模板
    pages/             # 页面级模板
  static/              # 前端静态资源
    css/               # 样式
    js/                # 页面交互脚本
    assets/            # 图片、图标、字体等资源
  ai_config/           # AI 配置说明
  处理结果/             # 每次分析生成的导出文件
```
