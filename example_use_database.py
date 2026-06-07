"""
演示如何使用 SQLite 数据库功能保存分析结果

运行方式：
    python example_use_database.py
"""

import sys
from database import init_db, save_analysis_results, connect_db

# Windows 控制台编码修复
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 1. 初始化数据库（自动创建表结构）
db_path = init_db()
print(f"[OK] 数据库已初始化：{db_path}")

# 2. 模拟分析结果
jd_source = "AI应用开发工程师.md"
jd_text = "岗位要求：Python、FastAPI、LLM应用开发经验。"

analysis_results = [
    {
        "filename": "张三_Python后端.pdf",
        "ok": True,
        "score": 85,
        "level": "高匹配",
        "conclusion": "非常适合，可以优先考虑。",
        "matched_skills": "Python、FastAPI、LLM Application",
        "missing_skills": "Docker、RAG",
        "strengths": [
            "Python 编程基础扎实",
            "有 FastAPI 项目经验"
        ],
        "gaps": [
            "缺少 Docker 容器化经验",
            "RAG 检索增强能力不足"
        ],
        "suggestions": [
            "补充 Docker 容器化实践",
            "学习 RAG 检索增强技术",
            "增加项目部署经验"
        ],
        "raw": {"match_score": 85, "diagnosis": {"level": "高匹配"}}
    },
    {
        "filename": "李四_数据分析.pdf",
        "ok": True,
        "score": 62,
        "level": "中等匹配",
        "conclusion": "有一定基础，但需要重点确认短板。",
        "matched_skills": "Python、SQL、Pandas",
        "missing_skills": "FastAPI、Tool Calling、RAG",
        "strengths": [
            "数据处理能力较强"
        ],
        "gaps": [
            "缺少后端框架经验",
            "缺少工具调用能力"
        ],
        "suggestions": [
            "补充 FastAPI 后端框架学习",
            "学习 LLM 工具调用机制"
        ],
        "raw": {"match_score": 62}
    }
]

resume_texts = {
    "张三_Python后端.pdf": "姓名：张三\n技能：Python、FastAPI、MySQL\n项目：开发过 REST API 接口",
    "李四_数据分析.pdf": "姓名：李四\n技能：Python、SQL、Pandas、数据可视化\n项目：数据分析报表系统"
}

# 3. 保存到数据库
saved_count = save_analysis_results(
    jd_source=jd_source,
    jd_text=jd_text,
    results=analysis_results,
    resume_texts=resume_texts
)
print(f"[OK] 成功保存 {saved_count} 条匹配记录")

# 4. 查询验证
conn = connect_db()
try:
    # 查询最近的匹配记录
    rows = conn.execute("""
        SELECT
            resumes.filename,
            matches.score,
            matches.level,
            matches.matched_skills,
            matches.missing_skills
        FROM matches
        JOIN resumes ON matches.resume_id = resumes.id
        ORDER BY matches.created_at DESC
    """).fetchall()

    print("\n查询结果：")
    print("-" * 80)
    for row in rows:
        print(f"简历：{row['filename']}")
        print(f"  匹配分：{row['score']}")
        print(f"  等级：{row['level']}")
        print(f"  已匹配：{row['matched_skills']}")
        print(f"  缺失：{row['missing_skills']}")
        print()
finally:
    conn.close()

print("[OK] 示例执行完成！")
print(f"数据库位置：{db_path}")
print("可以使用 DB Browser for SQLite 或 PyCharm 的数据库工具查看数据")
