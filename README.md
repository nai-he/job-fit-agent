# Job Fit Agent

一个面向招聘筛选场景的简历与岗位 JD 匹配分析工具。项目支持批量读取简历，抽取候选人技能，与岗位要求进行结构化匹配评分，并输出可解释的优势、短板、建议和排名报告。

这个项目适合放在简历里作为 AI 应用开发 / Python 后端方向项目：它不是单纯调用大模型，而是把文件解析、规则评分、Web 上传、报告导出和可选 AI 分析串成了一条完整应用链路。

## 界面预览

![主界面](screenshots/01-interface.png)

## 核心能力

- 批量解析简历：支持 `.docx`、`.pdf`、`.doc`。
- 岗位匹配评分：根据技能覆盖、类别权重和缺口计算可解释分数。
- 技能归一化：将 `embedding`、`向量检索` 等表达归一到统一技能标签。
- 轻量记忆系统：使用 JSON 持久化用户求职画像、历史分析结果和主要短板。
- 轻量 RAG 检索：将当前 JD / 简历分块并用 TF-IDF 检索相关证据片段。
- Agent 循环展示：按 Perception、Memory、RAG、Thought、Planning、Action、Observation 展示分析链路。
- SQLite 结果持久化：将 Web 分析批次中的岗位、简历和匹配结果写入三表结构，便于后续查询和统计。
- 本地规则兜底：没有模型 Key 也能完成完整分析。
- Web 页面操作：上传 JD 和多份简历，直接查看结果。
- 报告导出：生成 JSON、Markdown、Word 详细报告和 Excel 排名表。
- 可选 AI 分析：勾选后调用模型补充候选人评价，也可生成批量汇总报告。

## 技术栈

- Python
- FastAPI
- Jinja2
- python-docx
- pypdf
- openpyxl
- httpx
- OpenAI / DeepSeek 兼容模型接口

## Agent / Memory / RAG 设计

这个项目不是只调用一次大模型，而是把简历筛选任务组织成一个贴近 Agent 基本循环的流程：

```text
Environment：用户上传的简历、岗位 JD、历史求职画像
Perception：读取 PDF / Word / Markdown 文档，转换为文本
Memory：检索用户历史分析记录、目标岗位和能力短板
RAG：对当前 JD / 简历分块，检索支撑匹配判断的证据片段
Thought：抽取候选人技能和岗位技能要求
Planning + Tool Selection：选择评分工具，计算匹配分和缺口
Action：输出优势、短板、建议、排名和报告
Observation：页面卡片、JSON、Markdown、Word、Excel 导出结果
```

为便于学习第八章“记忆与检索”，这里实现的是轻量版本：

- `JobMemoryTool`：保存到 `.job_fit_agent/memory.json`，记录用户求职画像和历史分析结果。
- `JobRAGTool`：保存到 `.job_fit_agent/rag_index.json`，使用文本分块 + TF-IDF + 余弦相似度做本地检索。
- SQLite 持久化：Web 分析完成后会把岗位、简历、匹配分、优势、短板和原始结构化结果保存到 `sql/job_fit.db`。

它没有依赖 Qdrant、Neo4j 或外部 Embedding API，适合作为初学者能跑通、能讲清楚的 Memory/RAG 原型。

## 目录结构

```text
job-fit-agent/
  app.py                 # 命令行入口，负责批量分析和终端报告
  tools.py               # 文件读取、技能抽取、匹配评分等核心逻辑
  database.py            # SQLite 初始化与分析结果持久化
  prompts.py             # AI 总结提示词
  requirements.txt       # Python 依赖
  sql/                   # SQLite 表结构、查询示例和本地数据库
  examples/              # 示例 JD 和示例简历
  tests/                 # 核心逻辑测试
  web_app/               # FastAPI Web 应用
    main.py              # Web 后端入口
    templates/           # Jinja2 页面模板
    static/              # CSS、JS、静态资源
    ai_config/           # AI 配置说明
    处理结果/             # Web 分析导出结果
  dev_resources/         # 本地辅助资料，不属于项目运行主体
```

## 快速运行

安装依赖：

```bash
pip install -r requirements.txt
```

运行命令行版本：

```bash
python app.py
```

运行演示流程：

```bash
python app.py --demo --debug
```

关闭记忆或检索：

```bash
python app.py --demo --debug --no-memory
python app.py --demo --debug --no-rag
```

启动 Web 页面：

```bash
python -m web_app.main
```

浏览器访问：

```text
http://127.0.0.1:8000
```

如果 8000 已被占用，程序会自动使用下一个空闲端口。

## Web 使用方式

1. 在左侧粘贴或上传岗位 JD。
2. 在右侧批量上传候选人简历。
3. 点击“一键分析”查看匹配分、优势、短板和建议。
4. 展开候选人卡片里的 Agent 循环、Memory 上下文和 RAG 检索上下文。
5. 系统自动把成功匹配记录写入 SQLite，便于后续 SQL 查询。
6. 下载 JSON、Markdown、Word 或 Excel 报告。
7. 需要模型补充时，勾选“AI智能分析”或点击“写汇总报告”。

默认不会调用 AI；只有勾选 AI 功能或点击汇总报告时才会读取模型配置。

## AI 配置

Web 端推荐在 `web_app/.env` 中配置：

```text
WEB_AI_PROVIDER=openai
WEB_AI_API_KEY=your_api_key_here
WEB_AI_BASE_URL=https://api.deepseek.com/v1
WEB_AI_MODEL=deepseek-chat
```

也兼容根目录 `.env` 的通用变量：

```text
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat
USE_LLM_SUMMARY=1
```

真实 Key 不要提交到仓库。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 简历项目讲法

可以这样介绍：

> 我做了一个简历与岗位 JD 匹配分析 Agent。它把招聘筛选流程拆成感知、记忆检索、RAG 证据检索、技能抽取、匹配评分和报告生成几个步骤。系统会读取简历和 JD，抽取结构化技能，根据岗位技能权重计算匹配分，并把分析结果写入用户求职画像记忆；同时用轻量 RAG 从当前 JD 和简历中检索证据片段，帮助解释评分依据。Web 端支持批量上传、进度反馈、Agent 循环展示、SQLite 结果持久化和多格式报告导出；在需要更自然表达时，可以调用大模型生成补充分析和汇总报告。

## 当前边界

- 技能抽取主要基于规则词表和别名匹配，语义泛化能力有限。
- 当前 RAG 是轻量 TF-IDF 检索，不是向量数据库版本；后续可升级为 Embedding + Qdrant / Chroma。
- 当前 Memory 是 JSON 持久化，不是复杂长期记忆系统；SQLite 主要用于保存分析结果，后续可继续扩展历史记录页面和统计看板。
- 评分权重来自人工设定，还没有基于真实招聘数据校准。
- `.doc` 文件依赖本机 LibreOffice 或 Microsoft Word 转换能力。
