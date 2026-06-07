# Job Fit Agent Web

这是项目的 FastAPI Web 页面版本，负责简历上传、JD 输入、批量匹配分析、结果展示和报告导出。

## 功能

- 粘贴或上传岗位 JD。
- 批量上传 `.docx`、`.pdf`、`.doc` 简历。
- 展示候选人的匹配分、排名、优势、短板和改进建议。
- 展示每个候选人的 Agent 循环：Perception、Memory、RAG、Thought、Planning、Action、Observation。
- 展开查看 Memory 记忆上下文和 RAG 检索上下文。
- 自动把成功匹配记录写入 SQLite，保存岗位、简历和匹配结果。
- 导出 JSON、Markdown、Word 详细报告和 Excel 排名表。
- 勾选“AI智能分析”后调用模型补充候选人评价。
- 点击“写汇总报告”后在网页内生成批量筛选报告。
- 默认只运行本地规则，不会自动调用 AI。

## Memory / RAG

Web 端默认启用轻量 Memory 与 RAG：

- Memory：把分析结果写入 `.job_fit_agent/memory.json`，用于记录用户求职画像、历史匹配分和短板。
- RAG：把当前批次的 JD 和简历写入 `.job_fit_agent/rag_index.json`，用本地 TF-IDF 检索相关证据片段。

它是第八章“记忆系统 + 检索增强生成”的轻量学习版，不依赖 Qdrant、Neo4j 或外部 Embedding API。

## SQLite 持久化

Web 端每次分析完成后，会把成功读取并完成匹配的记录写入 SQLite：

- `jobs`：保存 JD 来源和 JD 文本。
- `resumes`：保存简历文件名和简历文本。
- `matches`：保存匹配分、等级、优势、短板、建议和原始结构化结果。

默认数据库路径是 `sql/job_fit.db`，也可以通过环境变量 `JOB_FIT_DB_PATH` 指定。数据库文件已在 `.gitignore` 中忽略，不会提交到仓库。

## 启动

在项目根目录安装依赖：

```bash
pip install -r requirements.txt
```

启动服务：

```bash
python -m web_app.main
```

打开：

```text
http://127.0.0.1:8000
```

如果 8000 已被占用，程序会自动使用下一个空闲端口。

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
