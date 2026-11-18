from fastapi.testclient import TestClient


def test_student_cannot_create_update_delete_quiz(
    client: TestClient, student_token: str, teacher_token: str, auth_headers
):
    # 1. Create attempt by student -> 403
    create_res = client.post(
        "/api/v1/quizzes",
        json={
            "title": "Hacker Quiz",
            "topic": "security",
            "questions": [],
        },
        headers=auth_headers(student_token),
    )
    assert create_res.status_code == 403

    # Teacher creates a valid quiz
    t_create_res = client.post(
        "/api/v1/quizzes",
        json={
            "title": "Teacher Quiz",
            "topic": "python",
            "questions": [
                {
                    "question_text": "What is 2+2 in Python?",
                    "options": ["3", "4", "5", "22"],
                    "correct_option": 1,
                    "explanation": "2+2 is 4",
                }
            ],
        },
        headers=auth_headers(teacher_token),
    )
    assert t_create_res.status_code == 201
    quiz_id = t_create_res.json()["id"]

    # Student update attempt -> 403
    update_res = client.put(
        f"/api/v1/quizzes/{quiz_id}",
        json={"title": "Altered Title"},
        headers=auth_headers(student_token),
    )
    assert update_res.status_code == 403

    # Student delete attempt -> 403
    delete_res = client.delete(
        f"/api/v1/quizzes/{quiz_id}",
        headers=auth_headers(student_token),
    )
    assert delete_res.status_code == 403


def test_correct_answers_hidden_from_students(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    # Teacher creates quiz
    create_res = client.post(
        "/api/v1/quizzes",
        json={
            "title": "Data Types Quiz",
            "topic": "basics",
            "questions": [
                {
                    "question_text": "Which type is immutable?",
                    "options": ["list", "tuple", "dict", "set"],
                    "correct_option": 1,
                    "explanation": "Tuples cannot be mutated.",
                }
            ],
        },
        headers=auth_headers(teacher_token),
    )
    assert create_res.status_code == 201
    quiz_id = create_res.json()["id"]

    # Teacher gets quiz detail -> sees correct_option & explanation
    teacher_detail = client.get(
        f"/api/v1/quizzes/{quiz_id}",
        headers=auth_headers(teacher_token),
    )
    assert teacher_detail.status_code == 200
    t_q = teacher_detail.json()["questions"][0]
    assert t_q["correct_option"] == 1
    assert t_q["explanation"] == "Tuples cannot be mutated."

    # Student gets quiz detail -> correct_option & explanation MUST NOT be present
    student_detail = client.get(
        f"/api/v1/quizzes/{quiz_id}",
        headers=auth_headers(student_token),
    )
    assert student_detail.status_code == 200
    s_q = student_detail.json()["questions"][0]
    assert "correct_option" not in s_q
    assert "explanation" not in s_q
    assert s_q["question_text"] == "Which type is immutable?"
    assert s_q["options"] == ["list", "tuple", "dict", "set"]

    # Student starts attempt -> questions in start response also do NOT contain answers
    start_res = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts",
        headers=auth_headers(student_token),
    )
    assert start_res.status_code == 201
    start_data = start_res.json()
    start_q = start_data["questions"][0]
    assert "correct_option" not in start_q
    assert "explanation" not in start_q


def test_quiz_attempt_scoring_and_feedback(
    client: TestClient, teacher_token: str, student_token: str, other_student_token: str, auth_headers
):
    # Teacher creates a 2-question quiz
    create_res = client.post(
        "/api/v1/quizzes",
        json={
            "title": "Control Flow Quiz",
            "topic": "flow",
            "description": "Test conditionals and loops",
            "questions": [
                {
                    "question_text": "Keyword to exit a loop early?",
                    "options": ["stop", "break", "exit", "continue"],
                    "correct_option": 1,
                    "explanation": "break exits the nearest enclosing loop",
                },
                {
                    "question_text": "Keyword to skip to next iteration?",
                    "options": ["skip", "pass", "continue", "next"],
                    "correct_option": 2,
                    "explanation": "continue proceeds to next cycle",
                },
            ],
        },
        headers=auth_headers(teacher_token),
    )
    assert create_res.status_code == 201
    quiz_data = create_res.json()
    quiz_id = quiz_data["id"]
    q1_id = quiz_data["questions"][0]["id"]
    q2_id = quiz_data["questions"][1]["id"]

    # Student starts attempt
    start_res = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts",
        headers=auth_headers(student_token),
    )
    assert start_res.status_code == 201
    attempt_id = start_res.json()["attempt_id"]

    # Another student tries to submit to this attempt -> 403
    other_sub = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": [{"question_id": q1_id, "selected_option": 1}]},
        headers=auth_headers(other_student_token),
    )
    assert other_sub.status_code == 403

    # Student submits 1 correct (q1) and 1 wrong (q2 selected option 0 instead of 2)
    submit_res = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={
            "answers": [
                {"question_id": q1_id, "selected_option": 1},
                {"question_id": q2_id, "selected_option": 0},
            ]
        },
        headers=auth_headers(student_token),
    )
    assert submit_res.status_code == 200
    result = submit_res.json()

    assert result["score"] == 50.0
    assert result["correct_answers"] == 1
    assert result["total_questions"] == 2
    assert result["completed"] is True
    assert result["completed_at"] is not None

    # Check feedback
    fb1 = next(f for f in result["feedback"] if f["question_id"] == q1_id)
    assert fb1["is_correct"] is True
    assert fb1["selected_option"] == 1
    assert fb1["correct_option"] == 1
    assert "break" in fb1["explanation"]

    fb2 = next(f for f in result["feedback"] if f["question_id"] == q2_id)
    assert fb2["is_correct"] is False
    assert fb2["selected_option"] == 0
    assert fb2["correct_option"] == 2
    assert "continue" in fb2["explanation"]

    # Cannot resubmit completed attempt -> 400
    resubmit_res = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": []},
        headers=auth_headers(student_token),
    )
    assert resubmit_res.status_code == 400

    # Retrieve attempt result via GET /quizzes/attempts/{id}
    get_attempt_res = client.get(
        f"/api/v1/quizzes/attempts/{attempt_id}",
        headers=auth_headers(student_token),
    )
    assert get_attempt_res.status_code == 200
    assert get_attempt_res.json()["score"] == 50.0

    # List my attempts
    my_attempts = client.get(
        f"/api/v1/quizzes/{quiz_id}/my-attempts",
        headers=auth_headers(student_token),
    )
    assert my_attempts.status_code == 200
    assert len(my_attempts.json()) == 1
    assert my_attempts.json()[0]["id"] == attempt_id


def test_quiz_crud_admin_and_teacher(
    client: TestClient, admin_token: str, teacher_token: str, student_token: str, auth_headers
):
    # Admin creates quiz
    create_res = client.post(
        "/api/v1/quizzes",
        json={
            "title": "Admin Math Quiz",
            "topic": "math",
            "description": "Math essentials",
            "questions": [
                {
                    "question_text": "What is 10 // 3?",
                    "options": ["3.33", "3", "4", "3.0"],
                    "correct_option": 1,
                    "explanation": "Floor division returns integer quotient.",
                }
            ],
        },
        headers=auth_headers(admin_token),
    )
    assert create_res.status_code == 201
    quiz_id = create_res.json()["id"]

    # Teacher updates quiz
    update_res = client.put(
        f"/api/v1/quizzes/{quiz_id}",
        json={
            "title": "Updated Math Quiz",
            "topic": "math",
            "questions": [
                {
                    "question_text": "What is 10 % 3?",
                    "options": ["0", "1", "2", "3"],
                    "correct_option": 1,
                    "explanation": "Modulo returns remainder.",
                }
            ],
        },
        headers=auth_headers(teacher_token),
    )
    assert update_res.status_code == 200
    assert update_res.json()["title"] == "Updated Math Quiz"

    # Filter quizzes by topic
    list_res = client.get(
        "/api/v1/quizzes?topic=math",
        headers=auth_headers(student_token),
    )
    assert list_res.status_code == 200
    quizzes = list_res.json()
    assert len(quizzes) >= 1
    assert any(q["id"] == quiz_id for q in quizzes)

    # Teacher deletes quiz
    del_res = client.delete(
        f"/api/v1/quizzes/{quiz_id}",
        headers=auth_headers(teacher_token),
    )
    assert del_res.status_code == 200

    # Getting deleted quiz -> 404
    get_res = client.get(
        f"/api/v1/quizzes/{quiz_id}",
        headers=auth_headers(student_token),
    )
    assert get_res.status_code == 404


def test_quiz_progress_and_topic_stats_integration(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    # Teacher creates a quiz under topic "algorithms"
    create_res = client.post(
        "/api/v1/quizzes",
        json={
            "title": "Sorting Quiz",
            "topic": "algorithms",
            "questions": [
                {
                    "question_text": "Best case for insertion sort?",
                    "options": ["O(n^2)", "O(n)", "O(log n)", "O(1)"],
                    "correct_option": 1,
                    "explanation": "Already sorted takes O(n)",
                }
            ],
        },
        headers=auth_headers(teacher_token),
    )
    quiz_id = create_res.json()["id"]
    q_id = create_res.json()["questions"][0]["id"]

    # Check progress before quiz attempt
    prog_before = client.get("/api/v1/progress/me", headers=auth_headers(student_token)).json()
    assert prog_before["total_quizzes"] >= 1
    assert prog_before["completed_quizzes"] == 0

    # Student takes the quiz and scores 100%
    start = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts",
        headers=auth_headers(student_token),
    ).json()
    attempt_id = start["attempt_id"]

    client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": [{"question_id": q_id, "selected_option": 1}]},
        headers=auth_headers(student_token),
    )

    # Check progress after quiz attempt
    prog_after = client.get("/api/v1/progress/me", headers=auth_headers(student_token)).json()
    assert prog_after["completed_quizzes"] >= 1
    assert prog_after["total_quiz_attempts"] >= 1
    assert prog_after["quiz_average_score"] == 100.0
    assert prog_after["current_streak"] >= 1

    # Check per-topic stats
    topic_algo = next(t for t in prog_after["topics"] if t["topic"] == "algorithms")
    assert topic_algo["total_quizzes"] >= 1
    assert topic_algo["completed_quizzes"] >= 1
    assert topic_algo["quiz_accuracy_percent"] == 100.0
