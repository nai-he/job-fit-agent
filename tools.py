from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docx import Document

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


BASE_DIR = Path(__file__).resolve().parent
EXAMPLES_DIR = BASE_DIR / "examples"
DEFAULT_RESUME_DIR = EXAMPLES_DIR / "resumes"
SUPPORTED_RESUME_SUFFIXES = {".docx", ".pdf", ".doc"}


@dataclass(frozen=True)
class SkillSpec:
    name: str
    aliases: tuple[str, ...]
    category: str
    weight: float


@dataclass(frozen=True)
class ResumeLoadIssue:
    path: str
    reason: str


SKILL_CATALOG: tuple[SkillSpec, ...] = (
    SkillSpec("Python", ("Python", "py"), "编程语言", 1.2),
    SkillSpec("FastAPI", ("FastAPI",), "后端框架", 1.0),
    SkillSpec("REST API", ("REST API", "RESTful", "接口开发", "API 接口"), "后端工程", 0.9),
    SkillSpec("SQL", ("SQL", "MySQL", "PostgreSQL", "数据库查询"), "数据处理", 0.8),
    SkillSpec("Pandas", ("Pandas", "DataFrame", "CSV 报表"), "数据处理", 0.7),
    SkillSpec("OpenAI API", ("OpenAI API", "OpenAI 兼容接口", "大模型 API", "LLM API"), "LLM 应用", 1.1),
    SkillSpec("Prompt Engineering", ("Prompt Engineering", "提示词", "Prompt", "提示词工程"), "LLM 应用", 1.0),
    SkillSpec("LLM Application", ("大模型应用", "LLM", "AI 应用", "大语言模型"), "LLM 应用", 1.2),
    SkillSpec("Tool Calling", ("工具调用", "function calling", "Action", "工具链路"), "Agent 能力", 1.0),
    SkillSpec("RAG", ("RAG", "检索增强", "Retrieval Augmented Generation"), "检索增强", 1.0),
    SkillSpec("Vector Database", ("Vector Database", "向量数据库", "向量检索", "embedding", "Embedding"), "检索增强", 0.9),
    SkillSpec("Docker", ("Docker", "容器化"), "工程部署", 0.8),
    SkillSpec("Git", ("Git", "版本控制"), "工程协作", 0.7),
)


def parse_resume_paths(raw_paths: str | None) -> list[str]:
    if not raw_paths or not raw_paths.strip():
        return []

    return [part.strip() for part in re.split(r"[;\r\n]+", raw_paths) if part.strip()]


def discover_resume_paths(resume_dir: str | Path | None = None) -> list[str]:
    directory = Path(resume_dir) if resume_dir else DEFAULT_RESUME_DIR
    if not directory.exists():
        raise FileNotFoundError(f"简历目录不存在：{directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"简历路径不是目录：{directory}")

    paths = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_RESUME_SUFFIXES
    )
    if not paths:
        supported = "、".join(sorted(SUPPORTED_RESUME_SUFFIXES))
        raise FileNotFoundError(f"简历目录中没有支持的文件：{directory}，支持格式：{supported}")
    return [str(path) for path in paths]


def resolve_resume_paths(raw_paths: str | None = None, resume_dir: str | Path | None = None) -> list[str]:
    paths = parse_resume_paths(raw_paths)
    if paths:
        return paths
    return discover_resume_paths(resume_dir)


def load_text_file(file_path: str | Path) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在：{path}")

    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8")

    if suffix == ".docx":
        return load_docx_file(path)

    if suffix == ".pdf":
        return load_pdf_file(path)

    if suffix == ".doc":
        return load_doc_file(path)

    raise ValueError(f"暂不支持的文件类型：{path.suffix}")


def load_docx_file(file_path: str | Path) -> str:
    document = Document(str(file_path))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n".join(paragraphs)


def load_pdf_file(file_path: str | Path) -> str:
    if PdfReader is None:
        raise RuntimeError("缺少 PDF 读取依赖，请先安装：pip install pypdf")

    reader = PdfReader(str(file_path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text.strip())
    return "\n".join(pages)


def load_doc_file(file_path: str | Path) -> str:
    source_path = Path(file_path).resolve()
    issues: list[str] = []

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            converted_path = convert_doc_with_libreoffice(source_path, Path(temp_dir))
            return load_docx_file(converted_path)
        except RuntimeError as error:
            issues.append(str(error))

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            converted_path = convert_doc_with_word(source_path, Path(temp_dir))
            return load_docx_file(converted_path)
        except RuntimeError as error:
            issues.append(str(error))

    details = "；".join(issues)
    raise RuntimeError(
        f"读取旧版 .doc 失败：{details}。"
        "请确认本机已安装 LibreOffice 或 Microsoft Word，也可以先把该文件另存为 .docx 后上传。"
    )


def find_soffice_executable() -> str | None:
    for env_name in ("SOFFICE_PATH", "LIBREOFFICE_PATH"):
        raw_value = os.environ.get(env_name)
        if not raw_value:
            continue

        candidate = Path(raw_value.strip('"'))
        if candidate.is_dir():
            candidate = candidate / "program" / "soffice.exe"
        if candidate.exists():
            return str(candidate)

    for command in ("soffice", "libreoffice"):
        resolved = shutil.which(command)
        if resolved:
            return resolved

    candidates = [
        Path("C:/Program Files/LibreOffice/program/soffice.exe"),
        Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return None


def convert_doc_with_libreoffice(source_path: Path, output_dir: Path) -> Path:
    soffice_path = find_soffice_executable()
    if not soffice_path:
        raise RuntimeError("未找到 LibreOffice/soffice")

    profile_dir = output_dir / "libreoffice-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    converted_path = output_dir / f"{source_path.stem}.docx"
    command = [
        soffice_path,
        "--headless",
        "--nologo",
        "--nodefault",
        "--nofirststartwizard",
        "--nolockcheck",
        "--norestore",
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--convert-to",
        "docx",
        "--outdir",
        str(output_dir),
        str(source_path),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("LibreOffice 转换超时") from error

    output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    if completed.returncode != 0 or not converted_path.exists():
        reason = output or f"退出码 {completed.returncode}"
        raise RuntimeError(f"LibreOffice 转换失败：{reason}")

    return converted_path


def convert_doc_with_word(source_path: Path, output_dir: Path) -> Path:
    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError(
            "Word COM 不可用：需要本机安装 Microsoft Word 和 pywin32"
        ) from error

    converted_path = output_dir / f"{source_path.stem}.docx"
    word = None
    document = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Open(
            str(source_path),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
        )
        document.SaveAs2(str(converted_path), FileFormat=16)
    except Exception as error:
        raise RuntimeError(f"Word 转换失败：{error}") from error
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass

    if not converted_path.exists():
        raise RuntimeError("Word 转换失败：没有生成 .docx 文件")

    return converted_path


def get_resume_text(resume_path: str | None = None) -> str:
    if resume_path:
        return load_text_file(resume_path)
    return load_text_file(discover_resume_paths()[0])


def get_resume_texts(raw_paths: str | None = None, resume_dir: str | Path | None = None) -> list[tuple[str, str]]:
    paths = resolve_resume_paths(raw_paths, resume_dir)
    return [(path, load_text_file(path)) for path in paths]


def get_resume_texts_safely(
    raw_paths: str | None = None,
    resume_dir: str | Path | None = None,
) -> tuple[list[tuple[str, str]], list[ResumeLoadIssue]]:
    paths = resolve_resume_paths(raw_paths, resume_dir)
    resumes: list[tuple[str, str]] = []
    issues: list[ResumeLoadIssue] = []

    for path in paths:
        try:
            resumes.append((path, load_text_file(path)))
        except Exception as error:
            issues.append(ResumeLoadIssue(path=path, reason=str(error)))

    if not resumes:
        details = "\n".join(f"- {Path(issue.path).name}: {issue.reason}" for issue in issues)
        raise RuntimeError(f"没有成功读取任何简历文件。\n{details}")

    return resumes, issues


def get_jd_text(jd_path: str | None = None) -> str:
    if jd_path:
        return load_text_file(jd_path)
    return load_text_file(EXAMPLES_DIR / "sample_jd.md")


def extract_candidate_skills(resume_text: str) -> str:
    return json.dumps(
        build_skill_profile(resume_text, "candidate_skills"),
        ensure_ascii=False,
        indent=2,
    )


def extract_job_requirements(jd_text: str) -> str:
    return json.dumps(
        build_skill_profile(jd_text, "job_requirements"),
        ensure_ascii=False,
        indent=2,
    )


def build_skill_profile(text: str, field_name: str) -> dict[str, Any]:
    skills = []
    for spec in SKILL_CATALOG:
        aliases = find_matched_aliases(text, spec.aliases)
        if not aliases:
            continue

        skills.append(
            {
                "name": spec.name,
                "category": spec.category,
                "weight": spec.weight,
                "matched_aliases": aliases,
                "evidence": build_evidence(text, aliases[0]),
            }
        )

    categories = sorted({skill["category"] for skill in skills})
    return {
        field_name: skills,
        "skill_count": len(skills),
        "categories": categories,
    }


def find_matched_aliases(text: str, aliases: tuple[str, ...]) -> list[str]:
    return [alias for alias in aliases if contains_alias(text, alias)]


def contains_alias(text: str, alias: str) -> bool:
    if is_ascii_token(alias):
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    return alias.lower() in text.lower()


def is_ascii_token(value: str) -> bool:
    return all(ord(char) < 128 for char in value)


def build_evidence(text: str, alias: str, window: int = 36) -> str:
    lower_text = text.lower()
    index = lower_text.find(alias.lower())
    if index < 0:
        return ""

    start = max(index - window, 0)
    end = min(index + len(alias) + window, len(text))
    snippet = text[start:end].replace("\n", " ").strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def compute_match_score(candidate_skills: str, job_requirements: str) -> str:
    candidate_data = parse_skill_payload(candidate_skills, "candidate_skills")
    job_data = parse_skill_payload(job_requirements, "job_requirements")

    candidate = index_skills(candidate_data.get("candidate_skills", []))
    job = index_skills(job_data.get("job_requirements", []))

    matched_names = sorted(candidate.keys() & job.keys())
    missing_names = sorted(job.keys() - candidate.keys())
    extra_names = sorted(candidate.keys() - job.keys())

    total_weight = sum(skill["weight"] for skill in job.values())
    matched_weight = sum(job[name]["weight"] for name in matched_names)
    match_score = round(matched_weight / total_weight * 100) if total_weight else 0

    category_scores = compute_category_scores(candidate, job)
    result = {
        "match_score": match_score,
        "matched_skills": [merge_skill_view(candidate[name], job[name]) for name in matched_names],
        "missing_skills": [job[name] for name in missing_names],
        "extra_skills": [candidate[name] for name in extra_names],
        "category_scores": category_scores,
        "diagnosis": build_diagnosis(match_score, missing_names, category_scores),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


def index_skills(skills: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(skills, list):
        return {}

    indexed: dict[str, dict[str, Any]] = {}
    for skill in skills:
        if isinstance(skill, str):
            indexed[skill] = {
                "name": skill,
                "category": "未分类",
                "weight": 1.0,
                "matched_aliases": [skill],
                "evidence": "",
            }
            continue

        if not isinstance(skill, dict) or not skill.get("name"):
            continue

        indexed[str(skill["name"])] = {
            "name": str(skill["name"]),
            "category": str(skill.get("category", "未分类")),
            "weight": float(skill.get("weight", 1.0)),
            "matched_aliases": list(skill.get("matched_aliases", [])),
            "evidence": str(skill.get("evidence", "")),
        }

    return indexed


def merge_skill_view(candidate_skill: dict[str, Any], job_skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": job_skill["name"],
        "category": job_skill["category"],
        "weight": job_skill["weight"],
        "candidate_evidence": candidate_skill.get("evidence", ""),
        "job_evidence": job_skill.get("evidence", ""),
    }


def compute_category_scores(
    candidate: dict[str, dict[str, Any]],
    job: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    categories = sorted({skill["category"] for skill in job.values()})
    scores = []
    for category in categories:
        required = [skill for skill in job.values() if skill["category"] == category]
        required_names = {skill["name"] for skill in required}
        matched_names = sorted(required_names & candidate.keys())
        required_weight = sum(skill["weight"] for skill in required)
        matched_weight = sum(skill["weight"] for skill in required if skill["name"] in candidate)
        scores.append(
            {
                "category": category,
                "score": round(matched_weight / required_weight * 100) if required_weight else 0,
                "matched": matched_names,
                "missing": sorted(required_names - candidate.keys()),
            }
        )
    return scores


def build_diagnosis(
    match_score: int,
    missing_names: list[str],
    category_scores: list[dict[str, Any]],
) -> dict[str, Any]:
    weak_categories = [
        item["category"]
        for item in category_scores
        if item["score"] < 70 and item["missing"]
    ]
    if match_score >= 80:
        level = "高匹配"
    elif match_score >= 60:
        level = "中等匹配"
    else:
        level = "低匹配"

    return {
        "level": level,
        "top_gaps": missing_names[:3],
        "weak_categories": weak_categories[:3],
    }


def parse_skill_payload(raw_value: str, field_name: str) -> dict[str, Any]:
    text = (raw_value or "").strip()
    if not text:
        return {field_name: []}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return {field_name: []}

    if isinstance(parsed, dict):
        return parsed

    if isinstance(parsed, list):
        return {field_name: parsed}

    return {field_name: []}


def build_tool_observation(tool_name: str, payload: str) -> str:
    return f"Observation: 工具 {tool_name} 返回 -> {payload}"
