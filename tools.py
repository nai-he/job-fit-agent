from __future__ import annotations

import ast
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
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
DEFAULT_AGENT_DATA_DIR = BASE_DIR / ".job_fit_agent"
DEFAULT_MEMORY_PATH = DEFAULT_AGENT_DATA_DIR / "memory.json"
DEFAULT_RAG_INDEX_PATH = DEFAULT_AGENT_DATA_DIR / "rag_index.json"
RAG_CHUNK_SIZE = 420
RAG_CHUNK_OVERLAP = 80


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


@dataclass(frozen=True)
class AgentTraceStep:
    phase: str
    thought: str
    tool: str
    action: str
    observation: str


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


def ensure_agent_data_dir(path: Path = DEFAULT_AGENT_DATA_DIR) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json_file(path: Path, data: Any) -> None:
    ensure_agent_data_dir(path.parent)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def tokenize_text(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_+#.-]*|[\u4e00-\u9fff]{2,}", text.lower())
    return [token for token in tokens if len(token.strip()) >= 2]


def split_text_chunks(text: str, chunk_size: int = RAG_CHUNK_SIZE, overlap: int = RAG_CHUNK_OVERLAP) -> list[str]:
    clean_text = re.sub(r"\s+", " ", text).strip()
    if not clean_text:
        return []

    chunks = []
    start = 0
    while start < len(clean_text):
        end = min(start + chunk_size, len(clean_text))
        chunk = clean_text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(clean_text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def compact_json(data: Any, limit: int = 800) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


class JobMemoryTool:
    """Lightweight project memory: stores user goals and past match summaries."""

    def __init__(self, memory_path: str | Path = DEFAULT_MEMORY_PATH, user_id: str = "default") -> None:
        self.memory_path = Path(memory_path)
        self.user_id = user_id

    def run(self, payload: dict[str, Any]) -> str:
        action = str(payload.get("action", "")).strip().lower()
        if action == "add":
            return self.add(payload)
        if action == "search":
            return self.search(str(payload.get("query", "")), int(payload.get("limit", 3)))
        if action == "summary":
            return self.summary(int(payload.get("limit", 5)))
        if action == "clear":
            return self.clear()
        raise ValueError(f"不支持的记忆操作：{action}")

    def load(self) -> dict[str, Any]:
        data = load_json_file(self.memory_path, {"users": {}})
        if not isinstance(data, dict):
            data = {"users": {}}
        users = data.setdefault("users", {})
        if not isinstance(users, dict):
            data["users"] = {}
        data["users"].setdefault(self.user_id, {"profile": {}, "events": []})
        return data

    def save(self, data: dict[str, Any]) -> None:
        write_json_file(self.memory_path, data)

    def add(self, payload: dict[str, Any]) -> str:
        data = self.load()
        user_memory = data["users"][self.user_id]
        event = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "memory_type": payload.get("memory_type", "episodic"),
            "content": str(payload.get("content", "")).strip(),
            "importance": float(payload.get("importance", 0.6)),
            "metadata": payload.get("metadata", {}),
        }
        if not event["content"]:
            return "未写入记忆：content 为空。"

        user_memory.setdefault("events", []).append(event)
        self._update_profile(user_memory, event)
        self.save(data)
        return f"已写入 {event['memory_type']} 记忆：{event['content']}"

    def search(self, query: str, limit: int = 3) -> str:
        data = self.load()
        events = data["users"][self.user_id].get("events", [])
        query_tokens = set(tokenize_text(query))
        scored = []
        for event in events:
            text = f"{event.get('content', '')} {json.dumps(event.get('metadata', {}), ensure_ascii=False)}"
            tokens = set(tokenize_text(text))
            overlap = len(query_tokens & tokens)
            importance = float(event.get("importance", 0.0))
            if overlap or not query_tokens:
                scored.append((overlap + importance * 0.2, event))

        scored.sort(key=lambda item: item[0], reverse=True)
        matches = [event for _, event in scored[:limit]]
        return compact_json({"query": query, "matches": matches})

    def summary(self, limit: int = 5) -> str:
        data = self.load()
        user_memory = data["users"][self.user_id]
        events = user_memory.get("events", [])
        latest = sorted(events, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        return compact_json(
            {
                "user_id": self.user_id,
                "profile": user_memory.get("profile", {}),
                "event_count": len(events),
                "latest_events": latest,
            }
        )

    def clear(self) -> str:
        data = self.load()
        data["users"][self.user_id] = {"profile": {}, "events": []}
        self.save(data)
        return f"已清空用户 {self.user_id} 的记忆。"

    def _update_profile(self, user_memory: dict[str, Any], event: dict[str, Any]) -> None:
        metadata = event.get("metadata", {})
        if not isinstance(metadata, dict):
            return

        profile = user_memory.setdefault("profile", {})
        target_role = metadata.get("target_role")
        if target_role:
            profile["target_role"] = target_role

        missing_skills = metadata.get("missing_skills")
        if missing_skills:
            profile["recent_gaps"] = missing_skills

        score = metadata.get("score")
        if score is not None:
            profile["last_score"] = score


class JobRAGTool:
    """Lightweight TF-IDF RAG tool for resumes, JDs, and historical snippets."""

    def __init__(self, index_path: str | Path = DEFAULT_RAG_INDEX_PATH, namespace: str = "default") -> None:
        self.index_path = Path(index_path)
        self.namespace = namespace

    def run(self, payload: dict[str, Any]) -> str:
        action = str(payload.get("action", "")).strip().lower()
        if action == "add_document":
            return self.add_document(
                source=str(payload.get("source", "unknown")),
                text=str(payload.get("text", "")),
                doc_type=str(payload.get("doc_type", "document")),
                metadata=payload.get("metadata", {}),
            )
        if action == "search":
            return self.search(str(payload.get("query", "")), int(payload.get("limit", 3)))
        if action == "clear":
            return self.clear()
        raise ValueError(f"不支持的 RAG 操作：{action}")

    def load(self) -> dict[str, Any]:
        data = load_json_file(self.index_path, {"namespaces": {}})
        if not isinstance(data, dict):
            data = {"namespaces": {}}
        namespaces = data.setdefault("namespaces", {})
        if not isinstance(namespaces, dict):
            data["namespaces"] = {}
        data["namespaces"].setdefault(self.namespace, {"chunks": []})
        return data

    def save(self, data: dict[str, Any]) -> None:
        write_json_file(self.index_path, data)

    def add_document(
        self,
        source: str,
        text: str,
        doc_type: str = "document",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        chunks = split_text_chunks(text)
        if not chunks:
            return f"未写入 RAG 索引：{source} 内容为空。"

        data = self.load()
        namespace_data = data["namespaces"][self.namespace]
        existing_chunks = namespace_data.setdefault("chunks", [])
        existing_chunks[:] = [
            chunk for chunk in existing_chunks if chunk.get("source") != source or chunk.get("doc_type") != doc_type
        ]

        created_at = datetime.now().isoformat(timespec="seconds")
        for index, chunk in enumerate(chunks, start=1):
            existing_chunks.append(
                {
                    "id": f"{source}:{doc_type}:{index}",
                    "source": source,
                    "doc_type": doc_type,
                    "chunk_index": index,
                    "text": chunk,
                    "tokens": tokenize_text(chunk),
                    "metadata": metadata or {},
                    "created_at": created_at,
                }
            )

        self.save(data)
        return f"已写入 RAG 索引：{source}，类型 {doc_type}，分块 {len(chunks)} 个。"

    def search(self, query: str, limit: int = 3) -> str:
        data = self.load()
        chunks = data["namespaces"][self.namespace].get("chunks", [])
        matches = self._rank_chunks(query, chunks, limit)
        return compact_json({"query": query, "matches": matches}, limit=1200)

    def clear(self) -> str:
        data = self.load()
        data["namespaces"][self.namespace] = {"chunks": []}
        self.save(data)
        return f"已清空命名空间 {self.namespace} 的 RAG 索引。"

    def _rank_chunks(self, query: str, chunks: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        query_tokens = tokenize_text(query)
        if not query_tokens or not chunks:
            return []

        document_frequency: dict[str, int] = {}
        for chunk in chunks:
            for token in set(chunk.get("tokens", [])):
                document_frequency[token] = document_frequency.get(token, 0) + 1

        total_documents = len(chunks)
        query_vector = self._tfidf_vector(query_tokens, document_frequency, total_documents)
        scored = []
        for chunk in chunks:
            chunk_tokens = list(chunk.get("tokens", []))
            chunk_vector = self._tfidf_vector(chunk_tokens, document_frequency, total_documents)
            score = cosine_similarity(query_vector, chunk_vector)
            if score <= 0:
                continue
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "score": round(score, 4),
                "source": chunk.get("source"),
                "doc_type": chunk.get("doc_type"),
                "chunk_index": chunk.get("chunk_index"),
                "text": chunk.get("text"),
                "metadata": chunk.get("metadata", {}),
            }
            for score, chunk in scored[:limit]
        ]

    def _tfidf_vector(
        self,
        tokens: list[str],
        document_frequency: dict[str, int],
        total_documents: int,
    ) -> dict[str, float]:
        term_frequency: dict[str, int] = {}
        for token in tokens:
            term_frequency[token] = term_frequency.get(token, 0) + 1

        vector = {}
        for token, count in term_frequency.items():
            idf = math.log((1 + total_documents) / (1 + document_frequency.get(token, 0))) + 1
            vector[token] = count * idf
        return vector


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    shared_tokens = set(left) & set(right)
    if not shared_tokens:
        return 0.0

    numerator = sum(left[token] * right[token] for token in shared_tokens)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def build_agent_trace_step(phase: str, thought: str, tool: str, action: str, observation: str) -> AgentTraceStep:
    return AgentTraceStep(
        phase=phase,
        thought=thought,
        tool=tool,
        action=action,
        observation=observation,
    )


def format_agent_trace(trace: list[AgentTraceStep]) -> str:
    lines = []
    for index, step in enumerate(trace, start=1):
        lines.extend(
            [
                f"--- Agent 循环 {index}: {step.phase} ---",
                f"Thought: {step.thought}",
                f"Tool Selection: {step.tool}",
                f"Action: {step.action}",
                f"Observation: {step.observation}",
                "=" * 60,
            ]
        )
    return "\n".join(lines)
