# SQLite 结果持久化说明

`Job Fit Agent` 的 Web 分析流程会在生成页面结果和导出文件后，将成功匹配的记录写入 SQLite。这个模块用于沉淀历史分析批次，方便后续做 SQL 查询、候选人对比、统计看板或历史记录页面。

## 设计目标

- 保留每次分析的 JD、简历文本和匹配结果。
- 使用三表结构表达岗位、简历和匹配关系。
- 通过事务写入，避免部分记录保存失败导致数据不一致。
- 保持部署简单：SQLite 是本地单文件数据库，不需要额外服务。

## 数据表

### `jobs`

保存岗位信息。

- `id`：主键
- `source`：JD 来源，例如上传文件名或“页面粘贴 JD”
- `jd_text`：岗位描述文本
- `created_at`：创建时间

### `resumes`

保存简历信息。

- `id`：主键
- `filename`：简历文件名
- `resume_text`：简历全文
- `created_at`：创建时间

### `matches`

保存岗位与简历之间的一次匹配结果。

- `id`：主键
- `job_id`：关联 `jobs.id`
- `resume_id`：关联 `resumes.id`
- `score`：匹配分
- `level`：匹配等级
- `conclusion`：一句话结论
- `matched_skills`：已匹配技能
- `missing_skills`：缺失技能
- `strengths_json`：优势列表
- `gaps_json`：短板列表
- `suggestions_json`：改进建议
- `raw_json`：完整结构化匹配结果
- `created_at`：创建时间

表结构定义见 [sql/schema.sql](sql/schema.sql)，常用查询见 [sql/queries.sql](sql/queries.sql)。

## 核心接口

### 初始化数据库

```python
from database import init_db

db_path = init_db()
print(db_path)
```

默认路径是 `sql/job_fit.db`。如果需要自定义路径，可以设置环境变量：

```text
JOB_FIT_DB_PATH=./data/job_fit.db
```

### 保存分析结果

```python
from database import save_analysis_results

saved_count = save_analysis_results(
    jd_source="页面粘贴 JD",
    jd_text="需要 Python、FastAPI、LLM 应用经验",
    results=ranked_results,
    resume_texts={
        "candidate.docx": "简历全文..."
    },
)
```

Web 端已经在 `/analyze` 流程中调用该接口。保存失败不会影响页面结果和报告导出，系统会在页面提示 SQLite 持久化失败原因。

### 查询数据库

```python
from database import connect_db

conn = connect_db()
try:
    rows = conn.execute("""
        SELECT resumes.filename, matches.score, matches.level
        FROM matches
        JOIN resumes ON matches.resume_id = resumes.id
        ORDER BY matches.created_at DESC
    """).fetchall()
finally:
    conn.close()
```

## 验证方式

运行数据库单元测试：

```bash
python -m unittest tests.test_database -v
```

运行示例脚本：

```bash
python example_use_database.py
```

运行完整测试：

```bash
python -m unittest discover -s tests -v
```

## 与 Memory 的区别

SQLite 和轻量 Memory 不是同一层能力：

- Memory：保存在 `.job_fit_agent/memory.json`，用于记录用户求职画像、最近短板和历史事件，服务于 Agent 分析流程。
- SQLite：保存在 `sql/job_fit.db`，用于结构化保存岗位、简历和匹配结果，服务于历史查询、统计和数据管理。

## 当前边界

- 目前已完成 Web 分析结果自动入库，但还没有单独的历史记录页面。
- 查询示例以 SQL 文件和示例脚本为主，后续可以增加 FastAPI 查询接口。
- 数据库保存的是规则分析后的结构化结果，不负责重新评分。
- SQLite 适合本地单机项目；如果后续变成多人系统，可以迁移到 PostgreSQL。
