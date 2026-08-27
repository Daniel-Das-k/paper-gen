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
        "year": "III Year",
        "semester": "5",
        "department": "Computer Science and Engineering",
        "generated_by": "Faculty User",
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
    finalized = store.transition(paper_id, "faculty", "finalize", "Draft complete")
    assert finalized["status"] == "faculty_finalized"
    submitted = store.transition(
        paper_id, "faculty", "submit", "Ready for review"
    )
    assert submitted["status"] == "submitted_to_hod"
    hod_queue = [
        paper
        for paper in store.list_papers()
        if paper["status"] == "submitted_to_hod"
    ]
    assert len(hod_queue) == 1
    assert hod_queue[0]["id"] == paper_id
    assert hod_queue[0]["course_name"] == "Data Structures"
    assert hod_queue[0]["course_code"] == "CS23C04"
    assert hod_queue[0]["generated_by"] == "Faculty User"
    assert hod_queue[0]["year"] == "III Year"
    store.transition(paper_id, "hod", "approve", "Checked by department")
    approved = store.transition(paper_id, "coe", "accept", "Approved for demo")

    reopened = DemoStore(tmp_path / "demo").get_paper(paper_id)
    assert approved["status"] == "approved"
    assert reopened["result"]["faculty_note"] == "Checked"
    summary = store.list_papers()[0]
    assert summary["year"] == "III Year"
    assert summary["generated_by"] == "Faculty User"
    assert summary["hod_approved"] == 1
    assert summary["last_coe_action"] == "accept"
    assert [activity["action"] for activity in reopened["activities"]] == [
        "generated",
        "question_edited",
        "finalize",
        "submit",
        "approve",
        "accept",
    ]


def test_demo_store_allows_faculty_judgment_and_requires_correct_role(tmp_path) -> None:
    store = DemoStore(tmp_path / "demo")
    metadata = {
        "pattern_id": "cat-2-75",
        "course_code": "CS23C04",
        "course_name": "Data Structures",
        "exam_label": "Continuous Assessment Test II",
    }
    job = store.create_job(metadata)
    paper_id = store.create_paper(job["id"], metadata, _result(ready=False))

    finalized = store.transition(
        paper_id,
        "faculty",
        "finalize",
        "Reviewed automated findings and accepted the draft",
    )
    assert finalized["status"] == "faculty_finalized"

    try:
        store.transition(paper_id, "coe", "accept", "")
    except ValueError as error:
        assert "cannot accept" in str(error)
    else:
        raise AssertionError("the wrong role accepted a faculty-finalized paper")


def test_hod_selects_one_generated_set_before_forwarding(tmp_path) -> None:
    store = DemoStore(tmp_path / "demo")
    metadata = {
        "pattern_id": "cat-1-75",
        "course_code": "CS23C04",
        "course_name": "Data Structures",
        "exam_label": "Continuous Assessment Test I",
    }
    result = _result()
    result.update(
        {
            "blueprint": {"set": "A"},
            "answer_key": [{"set": "A"}],
            "pdf_download_url": "/set-a.pdf",
            "scheme_download_url": "/set-a-scheme.pdf",
            "docx_download_url": "/set-a.docx",
            "sets": [
                {
                    "set_label": label,
                    "paper": {"publication_ready": True, "set_label": label},
                    "blueprint": {"set": label},
                    "answer_key": [{"set": label}],
                    "pdf_download_url": f"/set-{label.lower()}.pdf",
                    "scheme_download_url": f"/set-{label.lower()}-scheme.pdf",
                }
                for label in ("A", "B", "C")
            ],
        }
    )
    job = store.create_job(metadata)
    paper_id = store.create_paper(job["id"], metadata, result)
    store.transition(paper_id, "faculty", "finalize", "Draft complete")
    store.transition(paper_id, "faculty", "submit", "Ready")

    try:
        store.transition(paper_id, "hod", "approve", "Reviewed")
    except ValueError as error:
        assert "select one generated set" in str(error)
    else:
        raise AssertionError("HOD forwarded multiple sets without choosing one")

    forwarded = store.transition(
        paper_id,
        "hod",
        "approve",
        "Set B has the clearest coverage",
        selected_set_label="B",
    )

    assert forwarded["status"] == "submitted_to_coe"
    assert forwarded["result"]["selected_set_label"] == "B"
    assert forwarded["result"]["paper"]["set_label"] == "B"
    assert forwarded["result"]["pdf_download_url"] == "/set-b.pdf"
    assert forwarded["result"]["docx_download_url"] is None

    declined = store.transition(
        paper_id,
        "coe",
        "decline",
        "Revise the selected paper before final approval",
    )
    assert declined["status"] == "draft"
    assert declined["activities"][-1]["action"] == "decline"


def test_demo_store_marks_interrupted_jobs_failed_on_restart(tmp_path) -> None:
    root = tmp_path / "demo"
    store = DemoStore(root)
    job = store.create_job({"pattern_id": "cat-1-75"})
    store.update_job(job["id"], status="running", stage="Generating", progress=50)

    restarted = DemoStore(root).get_job(job["id"])

    assert restarted["status"] == "failed"
    assert "restarted" in restarted["error"]
