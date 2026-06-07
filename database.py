from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
SQL_DIR = ROOT_DIR / "sql"
SCHEMA_PATH = SQL_DIR / "schema.sql"
DEFAULT_DB_PATH = SQL_DIR / "job_fit.db"


def get_db_path(db_path: str | Path | None = None) -> Path:
    if db_path:
        return Path(db_path)

    configured_path = os.environ.get("JOB_FIT_DB_PATH")
    if configured_path and configured_path.strip():
        return Path(configured_path.strip())

    return DEFAULT_DB_PATH


def connect_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = get_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path | None = None) -> Path:
    path = get_db_path(db_path)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = connect_db(path)
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()
    return path


def save_analysis_results(
    jd_source: str,
    jd_text: str,
    results: list[dict[str, Any]],
    resume_texts: dict[str, str] | None = None,
    db_path: str | Path | None = None,
) -> int:
    path = init_db(db_path)
    resume_texts = resume_texts or {}

    conn = connect_db(path)
    try:
        job_id = conn.execute(
            "INSERT INTO jobs (source, jd_text) VALUES (?, ?)",
            (jd_source, jd_text),
        ).lastrowid

        saved_count = 0
        for item in results:
            if item.get("ok") is False:
                continue

            filename = get_result_filename(item)
            resume_text = resume_texts.get(filename) or resume_texts.get(str(item.get("resume_label", "")))
            resume_id = conn.execute(
                "INSERT INTO resumes (filename, resume_text) VALUES (?, ?)",
                (filename, resume_text),
            ).lastrowid

            conn.execute(
                """
                INSERT INTO matches (
                    job_id,
                    resume_id,
                    score,
                    level,
                    conclusion,
                    matched_skills,
                    missing_skills,
                    strengths_json,
                    gaps_json,
                    suggestions_json,
                    raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    resume_id,
                    int(item.get("score", 0)),
                    item.get("level"),
                    item.get("conclusion"),
                    item.get("matched_skills"),
                    item.get("missing_skills"),
                    json_dumps(item.get("strengths", [])),
                    json_dumps(item.get("gaps", [])),
                    json_dumps(item.get("suggestions", [])),
                    json_dumps(item.get("raw", {})),
                ),
            )
            saved_count += 1

        conn.commit()
    finally:
        conn.close()

    return saved_count


def get_result_filename(item: dict[str, Any]) -> str:
    filename = item.get("filename") or item.get("resume_label") or "unknown_resume"
    return Path(str(filename)).name


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
