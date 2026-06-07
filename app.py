import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from prompts import SUMMARY_PROMPT
from tools import (
    AgentTraceStep,
    JobMemoryTool,
    JobRAGTool,
    ResumeLoadIssue,
    build_agent_trace_step,
    build_tool_observation,
    compute_match_score,
    extract_candidate_skills,
    extract_job_requirements,
    format_agent_trace,
    get_jd_text,
    get_resume_texts_safely,
    resolve_resume_paths,
)


DEFAULT_REQUEST = "请分析候选人的简历与目标岗位 JD 的匹配情况，并总结匹配分、优势、短板和改进建议。"
DEBUG_ENV_VALUES = {"1", "true", "yes", "on", "debug"}
TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
DEFAULT_USER_ID = "default_user"


SKILL_DISPLAY_NAMES = {
    "Python": "Python 编程",
    "FastAPI": "FastAPI 后端框架",
    "REST API": "REST API 接口开发",
    "SQL": "SQL 数据库",
    "Pandas": "Pandas 数据处理",
    "OpenAI API": "大模型 API 接入",
    "Prompt Engineering": "提示词设计",
    "LLM Application": "大模型应用开发",
    "Tool Calling": "工具调用 / Function Calling",
    "RAG": "RAG 检索增强",
    "Vector Database": "向量数据库",
    "Docker": "Docker 容器化",
    "Git": "Git 版本管理",
}

GAP_SUGGESTIONS = {
    "Tool Calling": "补一个工具调用小项目，例如让 AI 助手调用天气、计算器或数据库查询函数，并在简历中写清楚“模型如何决定调用工具、工具结果如何返回给模型”。",
    "Vector Database": "补充向量数据库实践，例如用 Chroma、FAISS 或 Milvus 做文档向量化和相似度检索，并把它接入 RAG 问答流程。",
    "RAG": "补一个完整 RAG 流程：文档切分、向量化、检索、拼接上下文、生成回答，并记录检索命中效果。",
    "Git": "把项目放到 Git 仓库，补充分支管理、提交记录和 README，证明基本协作能力。",
    "Docker": "给项目增加 Dockerfile 和启动说明，证明项目可以被别人稳定运行。",
    "FastAPI": "把命令行项目封装成 FastAPI 接口，例如提供 /match 或 /chat 接口，体现服务化能力。",
}


def get_optional_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def is_debug_output() -> bool:
    value = get_optional_env("OUTPUT_MODE", "SHOW_STEPS", "DEBUG_OUTPUT")
    return bool(value and value.strip().lower() in DEBUG_ENV_VALUES)


def is_llm_summary_enabled() -> bool:
    value = get_optional_env("USE_LLM_SUMMARY", "LLM_SUMMARY", "ENABLE_LLM_SUMMARY")
    return bool(value and value.strip().lower() in TRUTHY_ENV_VALUES)


def load_llm_client() -> tuple[OpenAI, str] | None:
    load_dotenv()
    api_key = get_optional_env("OPENAI_API_KEY", "DEEPSEEK_API_KEY")
    base_url = get_optional_env("OPENAI_BASE_URL", "DEEPSEEK_BASE_URL")
    model_name = get_optional_env("MODEL_NAME", "DEEPSEEK_MODEL")
    if not api_key or not base_url or not model_name:
        return None
    return OpenAI(api_key=api_key, base_url=base_url), model_name


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量分析简历与岗位 JD 的匹配度，输出可解释评分、短板和改进建议。"
    )
    parser.add_argument(
        "request",
        nargs="*",
        help="可选的分析请求。不传时使用默认请求。",
    )
    parser.add_argument(
        "--resume-dir",
        help="简历目录，优先级高于 RESUME_DIR / RESUME_FOLDER。",
    )
    parser.add_argument(
        "--resume-files",
        help="指定简历文件路径，多个文件用分号或换行分隔。",
    )
    parser.add_argument(
        "--jd-file",
        help="岗位 JD 文件路径。",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="显示 Thought / Action / Observation 调试流程。",
    )
    parser.add_argument(
        "--llm-summary",
        action="store_true",
        help="启用模型补充总结。",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="直接使用内置示例数据运行，不等待交互输入。",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="记忆与 RAG 命名空间。默认读取 JOB_FIT_USER_ID，未配置时使用 default_user。",
    )
    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="关闭求职画像记忆读写。",
    )
    parser.add_argument(
        "--no-rag",
        action="store_true",
        help="关闭轻量 RAG 索引与检索。",
    )
    return parser.parse_args(argv)


def read_user_prompt(request_parts: list[str] | None = None, demo: bool = False) -> str:
    if request_parts:
        return " ".join(request_parts).strip()

    if demo or not sys.stdin.isatty():
        return DEFAULT_REQUEST

    try:
        prompt = input("按回车开始分析简历与岗位 JD：").strip()
    except EOFError:
        return DEFAULT_REQUEST
    return prompt or DEFAULT_REQUEST


def call_llm_summary(client: OpenAI, model_name: str, prompt: str) -> str:
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": prompt},
        ],
        stream=False,
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


def build_llm_summary_prompt(
    user_prompt: str,
    resume_text: str,
    jd_text: str,
    match_result: str,
    memory_context: str = "",
    rag_context: str = "",
) -> str:
    memory_block = f"\n历史记忆上下文：\n{memory_context}\n" if memory_context else ""
    rag_block = f"\nRAG 检索上下文：\n{rag_context}\n" if rag_context else ""
    return f"""
用户请求：
{user_prompt}

候选人简历：
{resume_text}

岗位 JD：
{jd_text}

结构化匹配结果：
{match_result}
{memory_block}{rag_block}
""".strip()


def print_step(step: int, thought: str, action: str, observation: str) -> None:
    print(f"--- 第 {step} 步 ---")
    print(f"Thought: {thought}")
    print(f"Action: {action}")
    print(observation)
    print("=" * 60)


def print_header(
    llm_config: tuple[OpenAI, str] | None,
    resume_paths: list[str],
    jd_path: str | None,
    debug_output: bool,
    llm_summary_enabled: bool,
) -> None:
    print("=" * 64)
    print("简历岗位匹配分析")
    print("=" * 64)

    if llm_config:
        _, model_name = llm_config
        summary_status = "启用模型总结" if llm_summary_enabled else "仅显示本地规则报告"
        print(f"模型：{model_name}（已配置，{summary_status}）")
    else:
        print("模型：未配置，使用本地规则生成报告")

    print(f"输出模式：{'详细调试' if debug_output else '简洁报告'}")

    if resume_paths:
        print(f"简历数量：{len(resume_paths)}")
        for index, path in enumerate(resume_paths, start=1):
            print(f"  {index}. {Path(path).name}")
    else:
        print("简历数量：1（内置示例简历）")

    if jd_path:
        print(f"岗位 JD：{Path(jd_path).name}")
    else:
        print("岗位 JD：内置示例 JD")

    print("=" * 64)
    print()


def print_load_warnings(issues: list[ResumeLoadIssue]) -> None:
    if not issues:
        return

    print("读取提醒")
    for issue in issues:
        print(f"- 已跳过 {Path(issue.path).name}：{issue.reason}")
    print()


def display_skill_name(name: str) -> str:
    return SKILL_DISPLAY_NAMES.get(name, name)


def join_skill_names(skills: list[dict[str, Any]], limit: int | None = None) -> str:
    names = [display_skill_name(str(skill.get("name", ""))) for skill in skills if skill.get("name")]
    if limit:
        names = names[:limit]
    return "、".join(names) if names else "无"


def get_score_comment(score: int) -> str:
    if score >= 85:
        return "非常适合，可以优先考虑。"
    if score >= 75:
        return "比较适合，建议进入下一轮筛选。"
    if score >= 60:
        return "有一定基础，但需要重点确认短板。"
    return "匹配度偏低，不建议直接进入下一轮。"


def build_strength_lines(match_data: dict[str, Any]) -> list[str]:
    category_scores = match_data.get("category_scores", [])
    strong_categories = [
        item for item in category_scores if item.get("score", 0) >= 80 and item.get("matched")
    ]
    lines = []
    for item in strong_categories[:3]:
        matched = "、".join(display_skill_name(name) for name in item.get("matched", []))
        lines.append(f"{item['category']}覆盖较好：已匹配 {matched}。")

    if not lines:
        matched_skills = join_skill_names(match_data.get("matched_skills", []), limit=5)
        lines.append(f"已匹配技能：{matched_skills}。")

    return lines


def build_gap_lines(match_data: dict[str, Any]) -> list[str]:
    missing_skills = match_data.get("missing_skills", [])
    if not missing_skills:
        return ["岗位要求中的核心技能基本都有体现，短板不明显。"]

    lines = []
    for skill in missing_skills[:4]:
        name = str(skill.get("name", ""))
        category = skill.get("category", "未分类")
        lines.append(f"缺少 {display_skill_name(name)}，影响 {category} 这类能力的匹配。")
    return lines


def build_suggestion_lines(match_data: dict[str, Any]) -> list[str]:
    missing_names = [str(skill.get("name", "")) for skill in match_data.get("missing_skills", [])]
    suggestions = [GAP_SUGGESTIONS[name] for name in missing_names if name in GAP_SUGGESTIONS]

    if len(suggestions) < 2:
        suggestions.append("把已有项目写得更具体：说明使用了什么技术、解决了什么问题、最终产出了什么结果。")
    if len(suggestions) < 3:
        suggestions.append("把 AI 项目服务化：提供 FastAPI 接口、错误处理、日志和 Docker 启动方式，体现接近真实工作的工程能力。")

    return suggestions[:3]


def print_numbered(title: str, lines: list[str]) -> None:
    print(title)
    for index, line in enumerate(lines, start=1):
        print(f"  {index}. {line}")
    print()


def print_simple_report(index: int, total: int, resume_label: str, match_data: dict[str, Any]) -> None:
    score = int(match_data.get("match_score", 0))
    diagnosis = match_data.get("diagnosis", {})
    level = diagnosis.get("level", "未知")

    print("-" * 64)
    print(f"简历 {index}/{total}：{Path(resume_label).name}")
    print("-" * 64)
    print(f"匹配分：{score} / 100")
    print(f"匹配等级：{level}")
    print(f"一句话结论：{get_score_comment(score)}")
    print()


def print_match_details(match_data: dict[str, Any]) -> None:
    print_numbered("优势", build_strength_lines(match_data))
    print_numbered("短板", build_gap_lines(match_data))
    print_numbered("改进建议", build_suggestion_lines(match_data))

    print(f"已匹配技能：{join_skill_names(match_data.get('matched_skills', []))}")
    print(f"缺失技能：{join_skill_names(match_data.get('missing_skills', []))}")
    print()


def print_llm_summary(
    llm_config: tuple[OpenAI, str] | None,
    llm_summary_enabled: bool,
    user_prompt: str,
    resume_text: str,
    jd_text: str,
    match_result: str,
    memory_context: str = "",
    rag_context: str = "",
) -> None:
    if not llm_config or not llm_summary_enabled:
        return

    client, model_name = llm_config
    prompt = build_llm_summary_prompt(
        user_prompt,
        resume_text,
        jd_text,
        match_result,
        memory_context=memory_context,
        rag_context=rag_context,
    )
    try:
        summary = call_llm_summary(client, model_name, prompt)
    except Exception as error:
        print(f"模型总结失败：{error}")
        print()
        return

    print("模型补充分析")
    print(summary.strip())
    print()


def print_batch_summary(results: list[dict[str, Any]]) -> None:
    if len(results) <= 1:
        return

    ranked = sorted(results, key=lambda item: item["score"], reverse=True)
    print("=" * 64)
    print("批量汇总排名")
    print("=" * 64)
    for index, item in enumerate(ranked, start=1):
        print(f"{index}. {Path(item['resume_label']).name}：{item['score']} 分，{item['level']}")
    print()


def truncate_text(text: str, limit: int = 520) -> str:
    clean_text = re.sub(r"\s+", " ", str(text)).strip()
    if len(clean_text) <= limit:
        return clean_text
    return f"{clean_text[:limit]}..."


def build_trace_observation(tool_name: str, payload: str, limit: int = 520) -> str:
    return build_tool_observation(tool_name, truncate_text(payload, limit=limit))


def build_gap_memory_content(resume_label: str, match_data: dict[str, Any]) -> str:
    score = int(match_data.get("match_score", 0))
    level = match_data.get("diagnosis", {}).get("level", "未知")
    missing = join_skill_names(match_data.get("missing_skills", []), limit=5)
    matched = join_skill_names(match_data.get("matched_skills", []), limit=5)
    return f"{Path(resume_label).name} 匹配分 {score}，等级 {level}；已匹配 {matched}；主要短板 {missing}。"


def build_rag_query(user_prompt: str, match_data: dict[str, Any]) -> str:
    matched = join_skill_names(match_data.get("matched_skills", []), limit=6)
    missing = join_skill_names(match_data.get("missing_skills", []), limit=6)
    return f"{user_prompt}\n已匹配技能：{matched}\n缺失技能：{missing}\n请检索简历和岗位 JD 中与匹配判断最相关的证据。"


def print_debug_flow(
    resume_text: str,
    jd_text: str,
    candidate_skills: str,
    job_requirements: str,
    match_result: str,
) -> None:
    print_step(
        1,
        "先读取候选人简历，作为后续技能提取的输入。",
        "load_resume()",
        build_tool_observation("load_resume", resume_text),
    )
    print_step(
        2,
        "再读取目标岗位 JD，作为后续岗位要求提取的输入。",
        "load_job_description()",
        build_tool_observation("load_job_description", jd_text),
    )
    print_step(
        3,
        "从简历中抽取候选人的标准化技能、类别和证据片段。",
        'extract_candidate_skills(resume_text="...")',
        build_tool_observation("extract_candidate_skills", candidate_skills),
    )
    print_step(
        4,
        "从岗位 JD 中抽取标准化岗位要求、类别和证据片段。",
        'extract_job_requirements(jd_text="...")',
        build_tool_observation("extract_job_requirements", job_requirements),
    )
    print_step(
        5,
        "基于技能权重、类别覆盖和缺口项计算可解释匹配结果。",
        'compute_match_score(candidate_skills="...", job_requirements="...")',
        build_tool_observation("compute_match_score", match_result),
    )


def analyze_resume(
    index: int,
    total: int,
    resume_label: str,
    resume_text: str,
    jd_text: str,
    debug_output: bool,
    user_prompt: str,
    llm_config: tuple[OpenAI, str] | None,
    llm_summary_enabled: bool,
    memory_tool: JobMemoryTool | None = None,
    rag_tool: JobRAGTool | None = None,
) -> dict[str, Any]:
    trace: list[AgentTraceStep] = [
        build_agent_trace_step(
            "Perception",
            "先把环境输入转成可分析文本，确认本轮任务的简历和岗位 JD 都已经可读。",
            "load_text_file / get_jd_text",
            "接收 resume_text 与 jd_text",
            f"简历 {Path(resume_label).name}，文本 {len(resume_text)} 字；JD 文本 {len(jd_text)} 字。",
        )
    ]

    memory_context = ""
    if memory_tool:
        memory_summary = memory_tool.run({"action": "summary", "limit": 3})
        memory_matches = memory_tool.run({"action": "search", "query": user_prompt, "limit": 3})
        memory_context = f"记忆摘要：{memory_summary}\n相关历史：{memory_matches}"
        trace.append(
            build_agent_trace_step(
                "Memory",
                "在正式评分前先查看历史求职画像和上次短板，避免每次分析都从零开始。",
                "JobMemoryTool",
                "summary + search",
                truncate_text(memory_context),
            )
        )

    if rag_tool:
        jd_observation = rag_tool.run(
            {
                "action": "add_document",
                "source": "current_jd",
                "doc_type": "jd",
                "text": jd_text,
                "metadata": {"resume": Path(resume_label).name},
            }
        )
        resume_observation = rag_tool.run(
            {
                "action": "add_document",
                "source": Path(resume_label).name,
                "doc_type": "resume",
                "text": resume_text,
                "metadata": {"batch_index": index},
            }
        )
        trace.append(
            build_agent_trace_step(
                "RAG Indexing",
                "把当前 JD 和简历写入轻量知识库，后续回答可以先检索证据再生成结论。",
                "JobRAGTool",
                "add_document(jd) + add_document(resume)",
                f"{jd_observation} {resume_observation}",
            )
        )

    candidate_skills = extract_candidate_skills(resume_text)
    job_requirements = extract_job_requirements(jd_text)
    match_result = compute_match_score(candidate_skills, job_requirements)
    match_data = json.loads(match_result)

    trace.extend(
        [
            build_agent_trace_step(
                "Thought",
                "从简历和岗位 JD 中抽取标准化技能，形成候选人与岗位的结构化表示。",
                "extract_candidate_skills / extract_job_requirements",
                "抽取技能画像与岗位要求",
                truncate_text(f"候选人技能：{candidate_skills}\n岗位要求：{job_requirements}"),
            ),
            build_agent_trace_step(
                "Planning + Tool Selection",
                "基于岗位技能权重、类别覆盖和缺口项计算匹配度，并决定后续要输出短板和建议。",
                "compute_match_score",
                "计算匹配分、优势、短板和类别覆盖",
                truncate_text(match_result),
            ),
        ]
    )

    rag_context = ""
    if rag_tool:
        rag_context = rag_tool.run({"action": "search", "query": build_rag_query(user_prompt, match_data), "limit": 4})
        trace.append(
            build_agent_trace_step(
                "RAG Retrieval",
                "检索当前简历和 JD 中最相关的证据片段，用于解释为什么这么打分。",
                "JobRAGTool",
                "search(query)",
                truncate_text(rag_context),
            )
        )

    if memory_tool:
        memory_write = memory_tool.run(
            {
                "action": "add",
                "memory_type": "episodic",
                "content": build_gap_memory_content(resume_label, match_data),
                "importance": 0.8,
                "metadata": {
                    "resume_label": Path(resume_label).name,
                    "score": int(match_data.get("match_score", 0)),
                    "level": match_data.get("diagnosis", {}).get("level", "未知"),
                    "missing_skills": join_skill_names(match_data.get("missing_skills", [])),
                    "matched_skills": join_skill_names(match_data.get("matched_skills", [])),
                    "target_role": "AI 应用开发 / Python 后端",
                },
            }
        )
        trace.append(
            build_agent_trace_step(
                "Memory Write",
                "把本次分析结果写入情景记忆，下次比较简历版本或追踪短板时可以复用。",
                "JobMemoryTool",
                "add(episodic)",
                memory_write,
            )
        )

    if debug_output:
        print(f"=== 简历 {index}/{total}：{resume_label} ===")
        print(format_agent_trace(trace))

    print_simple_report(index, total, resume_label, match_data)
    print_match_details(match_data)
    print_llm_summary(
        llm_config,
        llm_summary_enabled,
        user_prompt,
        resume_text,
        jd_text,
        match_result,
        memory_context=memory_context,
        rag_context=rag_context,
    )

    diagnosis = match_data.get("diagnosis", {})
    return {
        "resume_label": resume_label,
        "score": int(match_data.get("match_score", 0)),
        "level": diagnosis.get("level", "未知"),
    }


def main() -> None:
    args = parse_args()
    llm_config = load_llm_client()
    user_prompt = read_user_prompt(args.request, demo=args.demo)
    user_id = args.user_id or get_optional_env("JOB_FIT_USER_ID") or DEFAULT_USER_ID
    resume_paths_raw = args.resume_files or get_optional_env("RESUME_FILE_PATHS", "RESUME_FILE_PATH")
    resume_dir = args.resume_dir or get_optional_env("RESUME_DIR", "RESUME_FOLDER")
    jd_path = args.jd_file or get_optional_env("JD_FILE_PATH")
    resume_paths = resolve_resume_paths(resume_paths_raw, resume_dir)
    debug_output = args.debug or is_debug_output()
    llm_summary_enabled = args.llm_summary or is_llm_summary_enabled()
    memory_tool = None if args.no_memory else JobMemoryTool(user_id=user_id)
    rag_tool = None if args.no_rag else JobRAGTool(namespace=user_id)

    print_header(llm_config, resume_paths, jd_path, debug_output, llm_summary_enabled)

    jd_text = get_jd_text(jd_path)
    resumes, load_issues = get_resume_texts_safely(resume_paths_raw, resume_dir)
    print_load_warnings(load_issues)

    results = []
    for index, (resume_label, resume_text) in enumerate(resumes, start=1):
        results.append(
            analyze_resume(
                index=index,
                total=len(resumes),
                resume_label=resume_label,
                resume_text=resume_text,
                jd_text=jd_text,
                debug_output=debug_output,
                user_prompt=user_prompt,
                llm_config=llm_config,
                llm_summary_enabled=llm_summary_enabled,
                memory_tool=memory_tool,
                rag_tool=rag_tool,
            )
        )

    print_batch_summary(results)


if __name__ == "__main__":
    main()
