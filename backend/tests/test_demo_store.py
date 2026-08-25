from question_paper_gen.demo_store import DemoStore


def _result(*, ready: bool = True) -> dict[str, object]:
    return {
        "content_map": {"subject": "Data Structures"},
        "paper": {"publication_ready": ready},
    }


def test_demo_store_persists_papers_edits_and_approval_activity(tmp_path) -> None:
    store = DemoStore(tmp_path / "demo")
    metadata = {
        "pattern_id": "cat-1-75",
        "course_code": "CS23C04",
        "course_name": "Data Structures",
        "exam_label": "Continuous Assessment Test I",
    }
    job = store.create_job(metadata)
    paper_id = store.create_paper(job["id"], metadata, _result())

    edited = _result()
    edited["faculty_note"] = "Checked"
    store.save_result(
        paper_id,
        edited,
        action="question_edited",
        comment="Updated question 1.1 and its scheme",
    )
    store.transition(paper_id, "faculty", "submit", "Ready for review")
    store.transition(paper_id, "hod", "approve", "Checked by department")
    approved = store.transition(paper_id, "coe", "approve", "Approved for demo")

    reopened = DemoStore(tmp_path / "demo").get_paper(paper_id)
    assert approved["status"] == "approved"
    assert reopened["result"]["faculty_note"] == "Checked"
    assert [activity["action"] for activity in reopened["activities"]] == [
        "generated",
        "question_edited",
        "submit",
        "approve",
        "approve",
    ]


def test_demo_store_requires_a_ready_paper_and_correct_role(tmp_path) -> None:
    store = DemoStore(tmp_path / "demo")
    metadata = {
        "pattern_id": "cat-2-75",
        "course_code": "CS23C04",
        "course_name": "Data Structures",
        "exam_label": "Continuous Assessment Test II",
    }
    job = store.create_job(metadata)
    paper_id = store.create_paper(job["id"], metadata, _result(ready=False))

    try:
        store.transition(paper_id, "faculty", "submit", "")
    except ValueError as error:
        assert "blocking question" in str(error)
    else:
        raise AssertionError("a blocked paper was submitted")

    try:
        store.transition(paper_id, "hod", "approve", "")
    except ValueError as error:
        assert "cannot approve" in str(error)
    else:
        raise AssertionError("the wrong role approved a draft")


def test_demo_store_marks_interrupted_jobs_failed_on_restart(tmp_path) -> None:
    root = tmp_path / "demo"
    store = DemoStore(root)
    job = store.create_job({"pattern_id": "cat-1-75"})
    store.update_job(job["id"], status="running", stage="Generating", progress=50)

    restarted = DemoStore(root).get_job(job["id"])

    assert restarted["status"] == "failed"
    assert "restarted" in restarted["error"]
