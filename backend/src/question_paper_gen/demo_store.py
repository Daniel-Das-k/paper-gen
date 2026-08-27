from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


def default_demo_directory() -> Path:
    configured = os.getenv("DEMO_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "demo_data"


class DemoStore:
    """Small SQLite repository for the single-machine REC demonstration.

    This is deliberately not an authentication or multi-tenant boundary. It
    persists the demo workflow across restarts and keeps that concern out of the
    generation pipeline.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_demo_directory()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.upload_root = self.root / "uploads"
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "demo.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    error TEXT,
                    paper_id TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS papers (
                    id TEXT PRIMARY KEY,
                    pattern_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    course_code TEXT NOT NULL,
                    course_name TEXT NOT NULL,
                    exam_label TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
                    actor_role TEXT NOT NULL,
                    action TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_papers_updated
                    ON papers(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_activities_paper
                    ON activities(paper_id, id);
                """
            )
            existing_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(papers)").fetchall()
            }
            for column, definition in (
                ("year", "TEXT NOT NULL DEFAULT ''"),
                ("semester", "TEXT NOT NULL DEFAULT ''"),
                ("department", "TEXT NOT NULL DEFAULT ''"),
                ("generated_by", "TEXT NOT NULL DEFAULT ''"),
            ):
                if column not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE papers ADD COLUMN {column} {definition}"
                    )
            connection.execute(
                """
                UPDATE jobs
                SET status = 'failed',
                    stage = 'Generation interrupted',
                    error = 'The local backend restarted before this job completed. Start a new generation.',
                    updated_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (_now(),),
            )

    def create_job(self, metadata: dict[str, Any]) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs
                    (id, status, stage, progress, metadata_json, created_at, updated_at)
                VALUES (?, 'queued', 'Files received', 2, ?, ?, ?)
                """,
                (job_id, json.dumps(metadata), timestamp, timestamp),
            )
        return self.get_job(job_id)

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        stage: str | None = None,
        progress: int | None = None,
        error: str | None = None,
        paper_id: str | None = None,
    ) -> dict[str, Any]:
        changes: list[str] = ["updated_at = ?"]
        values: list[Any] = [_now()]
        for column, value in (
            ("status", status),
            ("stage", stage),
            ("progress", progress),
            ("error", error),
            ("paper_id", paper_id),
        ):
            if value is not None:
                changes.append(f"{column} = ?")
                values.append(value)
        values.append(job_id)
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE jobs SET {', '.join(changes)} WHERE id = ?", values
            )
            if cursor.rowcount != 1:
                raise KeyError(job_id)
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return dict(row)

    def create_paper(
        self, job_id: str, metadata: dict[str, Any], result: dict[str, Any]
    ) -> str:
        paper_id = uuid.uuid4().hex
        timestamp = _now()
        subject = str(result.get("content_map", {}).get("subject", "Course"))
        course_name = str(metadata.get("course_name") or subject)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO papers
                    (id, pattern_id, subject, course_code, course_name,
                     exam_label, year, semester, department, generated_by,
                     status, result_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)
                """,
                (
                    paper_id,
                    metadata["pattern_id"],
                    subject,
                    str(metadata.get("course_code", "")),
                    course_name,
                    str(metadata.get("exam_label", "")),
                    str(metadata.get("year", "")),
                    str(metadata.get("semester", "")),
                    str(metadata.get("department", "")),
                    str(metadata.get("generated_by", "Faculty User")),
                    json.dumps(result),
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO activities
                    (paper_id, actor_role, action, comment, created_at)
                VALUES (?, 'faculty', 'generated', ?, ?)
                """,
                (paper_id, f"Generated from local job {job_id[:8]}", timestamp),
            )
        return paper_id

    def list_papers(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT p.id, p.pattern_id, p.subject, p.course_code, p.course_name,
                       p.exam_label, p.year, p.semester, p.department,
                       p.generated_by, p.status, p.created_at, p.updated_at,
                       COALESCE(
                           (SELECT action FROM activities
                            WHERE paper_id = p.id ORDER BY id DESC LIMIT 1),
                           ''
                       ) AS last_action,
                       EXISTS(
                           SELECT 1 FROM activities
                           WHERE paper_id = p.id
                             AND actor_role = 'hod'
                             AND action = 'approve'
                       ) AS hod_approved,
                       COALESCE(
                           (SELECT action FROM activities
                            WHERE paper_id = p.id AND actor_role = 'coe'
                            ORDER BY id DESC LIMIT 1),
                           ''
                       ) AS last_coe_action
                FROM papers AS p ORDER BY p.updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_paper(self, paper_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM papers WHERE id = ?", (paper_id,)
            ).fetchone()
            activities = connection.execute(
                """
                SELECT actor_role, action, comment, created_at
                FROM activities WHERE paper_id = ? ORDER BY id
                """,
                (paper_id,),
            ).fetchall()
        if row is None:
            raise KeyError(paper_id)
        payload = dict(row)
        payload["result"] = json.loads(payload.pop("result_json"))
        payload["activities"] = [dict(activity) for activity in activities]
        payload["last_action"] = (
            payload["activities"][-1]["action"] if payload["activities"] else ""
        )
        payload["hod_approved"] = any(
            activity["actor_role"] == "hod" and activity["action"] == "approve"
            for activity in payload["activities"]
        )
        payload["last_coe_action"] = next(
            (
                activity["action"]
                for activity in reversed(payload["activities"])
                if activity["actor_role"] == "coe"
            ),
            "",
        )
        return payload

    def save_result(
        self,
        paper_id: str,
        result: dict[str, Any],
        *,
        action: str,
        comment: str,
    ) -> dict[str, Any]:
        timestamp = _now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM papers WHERE id = ?", (paper_id,)
            ).fetchone()
            if row is None:
                raise KeyError(paper_id)
            if row["status"] != "draft":
                raise ValueError("Only a draft paper can be edited")
            connection.execute(
                "UPDATE papers SET result_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(result), timestamp, paper_id),
            )
            connection.execute(
                """
                INSERT INTO activities
                    (paper_id, actor_role, action, comment, created_at)
                VALUES (?, 'faculty', ?, ?, ?)
                """,
                (paper_id, action, comment, timestamp),
            )
        return self.get_paper(paper_id)

    def transition(
        self,
        paper_id: str,
        actor_role: str,
        action: str,
        comment: str,
        *,
        selected_set_label: str | None = None,
    ) -> dict[str, Any]:
        transitions = {
            ("draft", "faculty", "finalize"): "faculty_finalized",
            ("faculty_finalized", "faculty", "submit"): "submitted_to_hod",
            ("submitted_to_hod", "hod", "approve"): "submitted_to_coe",
            ("submitted_to_hod", "hod", "return"): "draft",
            ("submitted_to_coe", "coe", "approve"): "approved",
            ("submitted_to_coe", "coe", "return"): "draft",
            ("submitted_to_coe", "coe", "accept"): "approved",
            ("submitted_to_coe", "coe", "decline"): "draft",
        }
        timestamp = _now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, result_json FROM papers WHERE id = ?", (paper_id,)
            ).fetchone()
            if row is None:
                raise KeyError(paper_id)
            target = transitions.get((row["status"], actor_role, action))
            if target is None:
                raise ValueError(
                    f"{actor_role} cannot {action} a paper in {row['status']}"
                )
            result = json.loads(row["result_json"])
            if actor_role == "hod" and action == "approve":
                sets = result.get("sets", [])
                if len(sets) > 1:
                    requested = (selected_set_label or "").strip().upper()
                    selected = next(
                        (
                            candidate
                            for candidate in sets
                            if str(candidate.get("set_label", "")).upper()
                            == requested
                        ),
                        None,
                    )
                    if selected is None:
                        raise ValueError(
                            "HOD must select one generated set before forwarding to CoE"
                        )
                    result["selected_set_label"] = requested
                    for key in (
                        "paper",
                        "blueprint",
                        "answer_key",
                        "pdf_download_url",
                        "scheme_download_url",
                    ):
                        result[key] = selected[key]
                    # Only Set A currently has an editable Word export. Do not
                    # expose that file after the HOD has selected another set.
                    if requested != "A":
                        result["docx_download_url"] = None
            connection.execute(
                """
                UPDATE papers
                SET status = ?, result_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (target, json.dumps(result), timestamp, paper_id),
            )
            connection.execute(
                """
                INSERT INTO activities
                    (paper_id, actor_role, action, comment, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (paper_id, actor_role, action, comment.strip(), timestamp),
            )
        return self.get_paper(paper_id)
