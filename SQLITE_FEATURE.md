# SQLite 数据库功能说明

## 概述

项目已成功集成 SQLite 数据库功能，用于持久化存储简历匹配分析结果。

## 功能特性

### 1. 数据库结构

数据库包含三张主表：

#### jobs 表（岗位信息）
- `id`: 主键
- `source`: JD 来源（文件名或描述）
- `jd_text`: 岗位描述文本
- `created_at`: 创建时间

#### resumes 表（简历信息）
- `id`: 主键
- `filename`: 简历文件名
- `resume_text`: 简历文本内容
- `created_at`: 创建时间

#### matches 表（匹配结果）
- `id`: 主键
- `job_id`: 关联岗位 ID（外键）
- `resume_id`: 关联简历 ID（外键）
- `score`: 匹配分数（0-100）
- `level`: 匹配等级（高匹配/中等匹配/低匹配）
- `conclusion`: 一句话结论
- `matched_skills`: 已匹配技能（逗号分隔）
- `missing_skills`: 缺失技能（逗号分隔）
- `strengths_json`: 优势列表（JSON 格式）
- `gaps_json`: 短板列表（JSON 格式）
- `suggestions_json`: 改进建议（JSON 格式）
- `raw_json`: 完整原始数据（JSON 格式）
- `created_at`: 创建时间

### 2. 核心 API

#### `init_db(db_path=None) -> Path`
初始化数据库，自动创建表结构和索引。

```python
from database import init_db

# 使用默认路径 sql/job_fit.db
db_path = init_db()

# 或指定自定义路径
db_path = init_db("/path/to/custom.db")
```

#### `save_analysis_results(...) -> int`
保存批量分析结果到数据库。

```python
from database import save_analysis_results

saved_count = save_analysis_results(
    jd_source="AI工程师.md",
    jd_text="需要Python、FastAPI、LLM经验",
    results=[
        {
            "filename": "张三.pdf",
            "ok": True,
            "score": 85,
            "level": "高匹配",
            "conclusion": "非常适合",
            "matched_skills": "Python、FastAPI",
            "missing_skills": "Docker",
            "strengths": ["Python基础扎实"],
            "gaps": ["缺少Docker经验"],
            "suggestions": ["补充容器化实践"],
            "raw": {"match_score": 85}
        }
    ],
    resume_texts={"张三.pdf": "简历全文..."}
)
```

#### `connect_db(db_path=None) -> sqlite3.Connection`
连接数据库，自动启用外键约束和 Row 工厂。

```python
from database import connect_db

conn = connect_db()
try:
    rows = conn.execute("SELECT * FROM matches").fetchall()
    for row in rows:
        print(row["filename"], row["score"])
finally:
    conn.close()
```

### 3. 配置方式

可通过环境变量指定数据库路径：

```bash
# .env 文件
JOB_FIT_DB_PATH=./custom_path/job_fit.db
```

或使用默认路径：`sql/job_fit.db`

## 使用示例

### 快速开始

```bash
# 1. 运行示例代码
python example_use_database.py

# 2. 运行测试
python -m unittest tests.test_database
```

### 常用 SQL 查询

项目提供了常用查询示例：`sql/queries.sql`

```sql
-- 查看最近的匹配记录
SELECT
    matches.id,
    resumes.filename,
    jobs.source AS jd_source,
    matches.score,
    matches.level,
    matches.created_at
FROM matches
JOIN resumes ON matches.resume_id = resumes.id
JOIN jobs ON matches.job_id = jobs.id
ORDER BY matches.created_at DESC;

-- 查看高匹配候选人（分数 >= 80）
SELECT
    resumes.filename,
    matches.score,
    matches.matched_skills,
    matches.missing_skills
FROM matches
JOIN resumes ON matches.resume_id = resumes.id
WHERE matches.score >= 80
ORDER BY matches.score DESC;

-- 按匹配等级统计数量
SELECT level, COUNT(*) AS total
FROM matches
GROUP BY level
ORDER BY total DESC;
```

## 文件结构

```
job-fit-agent/
├── database.py                 # 数据库操作核心模块
├── sql/
│   ├── schema.sql             # 数据库表结构定义
│   ├── queries.sql            # 常用查询示例
│   ├── job_fit.db             # 数据库文件（自动生成，已忽略）
│   └── README.md              # SQL 目录说明
├── tests/
│   └── test_database.py       # 数据库功能测试
└── example_use_database.py    # 使用示例代码
```

## 数据库工具推荐

### 1. DB Browser for SQLite
免费的图形化 SQLite 工具，支持浏览、查询、导出数据。

下载地址：https://sqlitebrowser.org/

### 2. PyCharm 数据库工具
PyCharm 内置的数据库工具，支持 SQL 自动补全和查询执行。

使用方式：
1. 打开 Database 工具窗口
2. 添加 Data Source → SQLite
3. 选择 `sql/job_fit.db` 文件

### 3. SQLite CLI（命令行）
```bash
# 安装（Windows）
# 下载 sqlite-tools-win32 from https://www.sqlite.org/download.html

# 使用
sqlite3 sql/job_fit.db
sqlite> .tables
sqlite> SELECT * FROM matches;
```

## 与 JSON 存储的对比

| 特性 | SQLite | JSON 文件 |
|------|--------|-----------|
| **查询能力** | ✅ 强大的 SQL 查询 | ❌ 需要加载全部数据 |
| **性能** | ✅ 索引优化，大数据量高效 | ❌ 数据量大时性能下降 |
| **并发** | ✅ 支持并发读写 | ❌ 容易冲突 |
| **关系查询** | ✅ 支持 JOIN、聚合 | ❌ 需要手动实现 |
| **数据完整性** | ✅ 外键约束、事务 | ❌ 依赖代码保证 |
| **部署简单** | ✅ 单文件，无需服务 | ✅ 单文件 |
| **可读性** | ⚠️ 需要工具查看 | ✅ 直接打开 |

## 集成到 Web 应用

可以在 `web_app/main.py` 中集成数据库保存：

```python
from database import save_analysis_results

@app.post("/api/analyze")
async def analyze_endpoint(...):
    # ... 执行分析 ...
    
    # 保存到数据库
    save_analysis_results(
        jd_source=jd_filename,
        jd_text=jd_text,
        results=all_results,
        resume_texts=resume_texts_dict
    )
    
    return all_results
```

## 测试验证

```bash
# 运行单元测试
python -m unittest tests.test_database -v

# 预期输出
test_save_analysis_results_persists_match_record ... ok

----------------------------------------------------------------------
Ran 1 test in 0.044s

OK
```

## 注意事项

1. **数据库文件已添加到 `.gitignore`**，不会提交到版本控制
2. **首次使用会自动创建数据库和表结构**
3. **支持外键约束**，删除 job 或 resume 会级联删除相关 matches
4. **默认使用本地时间**，`created_at` 字段自动填充

## 恢复历史

SQLite 功能从 git stash 恢复，对应提交：
- Stash: `stash@{0}: On master: before restoring accidental sqlite changes`
- Commit: `ae5908d`

## 下一步建议

1. ✅ 已恢复基础 SQLite 功能
2. 🔲 集成到 Web 应用的保存逻辑
3. 🔲 添加数据查询和导出 API
4. 🔲 实现历史记录对比功能
5. 🔲 添加数据统计和可视化

---

**功能已完整恢复并测试通过！** 🎉
