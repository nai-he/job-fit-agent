import sqlite3
import tempfile
import unittest
from pathlib import Path

from database import save_analysis_results


class DatabasePersistenceTest(unittest.TestCase):
    def test_save_analysis_results_persists_match_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "job_fit_test.db"
            results = [
                {
                    "filename": "resume.pdf",
                    "ok": True,
                    "score": 88,
                    "level": "高匹配",
                    "conclusion": "适合进入下一轮。",
                    "matched_skills": "Python、SQL",
                    "missing_skills": "Docker",
                    "strengths": ["Python 基础扎实"],
                    "gaps": ["Docker 经验不足"],
                    "suggestions": ["补充部署经验"],
                    "raw": {"match_score": 88},
                }
            ]

            saved_count = save_analysis_results(
                "测试 JD",
                "需要 Python 和 SQL",
                results,
                {"resume.pdf": "熟悉 Python 和 SQL"},
                db_path,
            )

            self.assertEqual(saved_count, 1)
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    """
                    SELECT
                        jobs.source,
                        resumes.filename,
                        resumes.resume_text,
                        matches.score,
                        matches.level
                    FROM matches
                    JOIN jobs ON matches.job_id = jobs.id
                    JOIN resumes ON matches.resume_id = resumes.id
                    """
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(row, ("测试 JD", "resume.pdf", "熟悉 Python 和 SQL", 88, "高匹配"))


if __name__ == "__main__":
    unittest.main()
