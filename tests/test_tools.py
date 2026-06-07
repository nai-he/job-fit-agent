import json
import tempfile
import unittest
from pathlib import Path

from tools import (
    JobMemoryTool,
    JobRAGTool,
    compute_match_score,
    extract_candidate_skills,
    extract_job_requirements,
    get_resume_texts_safely,
    load_pdf_file,
    resolve_resume_paths,
    parse_resume_paths,
)
import tools


class MatchScoreTest(unittest.TestCase):
    def test_weighted_score_and_gaps(self) -> None:
        resume = "熟悉 Python、FastAPI、Prompt Engineering 和 Docker，做过 RAG 原型。"
        jd = "要求 Python、FastAPI、大模型应用、Prompt Engineering、Docker、Git、向量数据库。"

        candidate_skills = extract_candidate_skills(resume)
        job_requirements = extract_job_requirements(jd)
        result = json.loads(compute_match_score(candidate_skills, job_requirements))

        self.assertGreater(result["match_score"], 50)
        self.assertLess(result["match_score"], 100)
        self.assertIn("Git", {skill["name"] for skill in result["missing_skills"]})
        self.assertIn("Vector Database", {skill["name"] for skill in result["missing_skills"]})

    def test_alias_normalization(self) -> None:
        profile = json.loads(extract_job_requirements("理解 embedding 和向量检索，能设计提示词流程。"))
        names = {skill["name"] for skill in profile["job_requirements"]}

        self.assertIn("Vector Database", names)
        self.assertIn("Prompt Engineering", names)

    def test_parse_resume_paths(self) -> None:
        raw_paths = "E:\\resume1.docx;E:\\resume2.docx\nE:\\resume3.docx"
        self.assertEqual(
            parse_resume_paths(raw_paths),
            ["E:\\resume1.docx", "E:\\resume2.docx", "E:\\resume3.docx"],
        )

    def test_resolve_resume_paths_from_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            (directory / "b.docx").write_text("", encoding="utf-8")
            (directory / "a.docx").write_text("", encoding="utf-8")
            (directory / "c.pdf").write_text("", encoding="utf-8")
            (directory / "d.doc").write_text("", encoding="utf-8")
            (directory / "notes.txt").write_text("", encoding="utf-8")

            self.assertEqual(
                [Path(path).name for path in resolve_resume_paths(resume_dir=directory)],
                ["a.docx", "b.docx", "c.pdf", "d.doc"],
            )

    def test_get_resume_texts_safely_skips_failed_files(self) -> None:
        original_loader = tools.load_text_file

        def fake_load_text_file(path: str | Path) -> str:
            if str(path).endswith("bad.doc"):
                raise RuntimeError("Word is unavailable")
            return "Python FastAPI"

        try:
            tools.load_text_file = fake_load_text_file
            resumes, issues = get_resume_texts_safely("good.docx;bad.doc")
        finally:
            tools.load_text_file = original_loader

        self.assertEqual(resumes, [("good.docx", "Python FastAPI")])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].path, "bad.doc")
        self.assertIn("Word is unavailable", issues[0].reason)

    def test_load_pdf_file_extracts_page_text(self) -> None:
        original_reader = tools.PdfReader

        class FakePage:
            def __init__(self, text: str) -> None:
                self.text = text

            def extract_text(self) -> str:
                return self.text

        class FakeReader:
            def __init__(self, _: str) -> None:
                self.pages = [FakePage("Python FastAPI"), FakePage("RAG")]

        try:
            tools.PdfReader = FakeReader
            self.assertEqual(load_pdf_file("resume.pdf"), "Python FastAPI\nRAG")
        finally:
            tools.PdfReader = original_reader


class LightweightMemoryAndRAGTest(unittest.TestCase):
    def test_memory_tool_persists_and_searches_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            memory_path = Path(temp_dir) / "memory.json"
            memory = JobMemoryTool(memory_path=memory_path, user_id="tester")
            memory.run(
                {
                    "action": "add",
                    "memory_type": "episodic",
                    "content": "张三简历缺少 Docker 和向量数据库实践",
                    "importance": 0.9,
                    "metadata": {
                        "score": 72,
                        "missing_skills": "Docker、Vector Database",
                    },
                }
            )

            summary = json.loads(memory.run({"action": "summary"}))
            search_result = json.loads(memory.run({"action": "search", "query": "Docker 短板"}))

            self.assertEqual(summary["event_count"], 1)
            self.assertEqual(summary["profile"]["last_score"], 72)
            self.assertEqual(search_result["matches"][0]["content"], "张三简历缺少 Docker 和向量数据库实践")

    def test_rag_tool_indexes_and_retrieves_relevant_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "rag.json"
            rag = JobRAGTool(index_path=index_path, namespace="tester")
            rag.run(
                {
                    "action": "add_document",
                    "source": "resume.md",
                    "doc_type": "resume",
                    "text": "候选人熟悉 Python 和 FastAPI，做过 RAG 检索增强问答项目。",
                }
            )
            rag.run(
                {
                    "action": "add_document",
                    "source": "jd.md",
                    "doc_type": "jd",
                    "text": "岗位要求 Docker 部署、向量数据库和 RAG 项目经验。",
                }
            )

            result = json.loads(rag.run({"action": "search", "query": "RAG 项目经验", "limit": 2}))

            self.assertGreaterEqual(len(result["matches"]), 1)
            self.assertIn("RAG", result["matches"][0]["text"])


if __name__ == "__main__":
    unittest.main()
