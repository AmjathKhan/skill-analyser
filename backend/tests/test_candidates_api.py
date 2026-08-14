"""Candidate list, profile, editing, notes and lifecycle."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_candidates_is_paginated(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    response = client.get("/api/candidates?page=1&page_size=2", headers=recruiter_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["meta"]["total"] >= 5
    assert body["meta"]["total_pages"] >= 3
    assert body["meta"]["has_next"] is True
    assert body["items"][0]["top_skills"]


def test_list_filters(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    by_skill = client.get("/api/candidates?skills=Apache Spark", headers=recruiter_headers).json()
    assert [item["full_name"] for item in by_skill["items"]] == ["Arjun Mehta"]

    by_experience = client.get("/api/candidates?min_experience=8", headers=recruiter_headers).json()
    assert all(item["total_experience_years"] >= 8 for item in by_experience["items"])

    by_search = client.get("/api/candidates?search=neha", headers=recruiter_headers).json()
    assert by_search["meta"]["total"] == 1
    assert by_search["items"][0]["full_name"] == "Neha Verma"

    by_location = client.get("/api/candidates?location=Hyderabad", headers=recruiter_headers).json()
    assert by_location["meta"]["total"] >= 1


def test_list_sorting(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    by_name = client.get("/api/candidates?sort_by=name&sort_dir=asc", headers=recruiter_headers).json()
    names = [item["full_name"] for item in by_name["items"]]
    assert names == sorted(names)

    by_experience = client.get(
        "/api/candidates?sort_by=experience&sort_dir=desc", headers=recruiter_headers
    ).json()
    years = [item["total_experience_years"] for item in by_experience["items"]]
    assert years == sorted(years, reverse=True)


def test_candidate_detail_contains_full_profile(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    candidate_id = next(
        item["candidate_id"]
        for item in uploaded_candidates
        if item["filename"].startswith("priya")
    )
    response = client.get(f"/api/candidate/{candidate_id}", headers=recruiter_headers)
    assert response.status_code == 200
    body = response.json()

    assert body["full_name"] == "Priya Sharma"
    assert body["email"] == "priya.sharma@example.com"
    assert body["linkedin_url"] and body["github_url"]
    assert body["total_experience_years"] >= 6
    assert body["ai_summary"]
    assert body["skills"] and body["experiences"] and body["educations"]
    assert body["certifications"] and body["projects"]
    assert body["timeline"]
    assert body["resumes"]
    assert 0 <= body["profile_completeness"] <= 100

    skill = body["skills"][0]
    assert {"name", "category", "proficiency", "confidence", "source"} <= set(skill)
    assert any(item["technology_stack"] for item in body["skills"])


def test_update_candidate(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    candidate_id = uploaded_candidates[0]["candidate_id"]
    response = client.put(
        f"/api/candidate/{candidate_id}",
        json={"availability": "Immediate", "notice_period_days": 0, "tags": ["priority"]},
        headers=recruiter_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["availability"] == "Immediate"
    assert body["tags"] == ["priority"]


def test_status_change_is_audited(client: TestClient, recruiter_headers, admin_headers, uploaded_candidates) -> None:
    candidate_id = uploaded_candidates[1]["candidate_id"]
    response = client.patch(
        f"/api/candidate/{candidate_id}/status",
        json={"status": "shortlisted", "reason": "Strong data engineering background"},
        headers=recruiter_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "shortlisted"

    logs = client.get("/api/users/audit/logs?action=candidate_status_change", headers=admin_headers).json()
    assert any(entry["entity_id"] == candidate_id for entry in logs["items"])


def test_invalid_status_is_rejected(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    candidate_id = uploaded_candidates[0]["candidate_id"]
    response = client.patch(
        f"/api/candidate/{candidate_id}/status", json={"status": "banana"}, headers=recruiter_headers
    )
    assert response.status_code == 422


def test_recruiter_notes(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    candidate_id = uploaded_candidates[0]["candidate_id"]
    created = client.post(
        f"/api/candidate/{candidate_id}/notes",
        json={"content": "Great communication in the screening call.", "rating": 4},
        headers=recruiter_headers,
    )
    assert created.status_code == 201
    assert created.json()["rating"] == 4

    detail = client.get(f"/api/candidate/{candidate_id}", headers=recruiter_headers).json()
    assert any(note["content"].startswith("Great communication") for note in detail["notes"])


def test_private_notes_are_hidden_from_other_users(
    client: TestClient, recruiter_headers, manager_headers, uploaded_candidates
) -> None:
    candidate_id = uploaded_candidates[2]["candidate_id"]
    client.post(
        f"/api/candidate/{candidate_id}/notes",
        json={"content": "Private salary expectation note", "is_private": True},
        headers=recruiter_headers,
    )
    seen_by_manager = client.get(f"/api/candidate/{candidate_id}", headers=manager_headers).json()
    assert all("Private salary" not in note["content"] for note in seen_by_manager["notes"])


def test_similar_candidates_uses_the_graph(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    candidate_id = next(
        item["candidate_id"] for item in uploaded_candidates if item["filename"].startswith("priya")
    )
    response = client.get(f"/api/candidate/{candidate_id}/similar?limit=3", headers=recruiter_headers)
    assert response.status_code == 200
    similar = response.json()
    assert similar
    assert all(item["candidate_id"] != candidate_id for item in similar)

    # The UI renders these fields directly, so the shapes are part of the contract.
    top = similar[0]
    assert isinstance(top["shared_skills"], int) and top["shared_skills"] > 0
    assert isinstance(top["shared_skill_names"], list)
    assert all(isinstance(name, str) for name in top["shared_skill_names"])
    assert len(top["shared_skill_names"]) == top["shared_skills"]
    assert 0 < top["similarity_percent"] <= 100
    assert isinstance(top["total_experience_years"], (int, float))
    # Results are ordered by how much of the source profile they cover.
    percents = [item["similarity_percent"] for item in similar]
    assert percents == sorted(percents, reverse=True)


def test_unknown_candidate_returns_404(client: TestClient, recruiter_headers) -> None:
    assert client.get("/api/candidate/424242", headers=recruiter_headers).status_code == 404


def test_hiring_manager_cannot_edit(client: TestClient, manager_headers, uploaded_candidates) -> None:
    candidate_id = uploaded_candidates[0]["candidate_id"]
    response = client.put(
        f"/api/candidate/{candidate_id}", json={"availability": "Nope"}, headers=manager_headers
    )
    assert response.status_code == 403


def test_soft_delete_hides_candidate(client: TestClient, admin_headers, uploaded_candidates) -> None:
    """Deletes a throwaway candidate so the shared sample fixtures stay intact."""
    resume = (
        b"Temp Deletable\n"
        b"temp.deletable@example.com\n"
        b"TECHNICAL SKILLS\n"
        b"Python, Docker\n"
    )
    upload = client.post(
        "/api/upload?wait=true",
        files=[("files", ("temp_deletable.txt", resume, "text/plain"))],
        headers=admin_headers,
    )
    assert upload.status_code == 201, upload.text
    candidate_id = upload.json()["results"][0]["candidate_id"]

    before = client.get("/api/candidates?page_size=100", headers=admin_headers).json()["meta"]["total"]

    response = client.delete(f"/api/candidate/{candidate_id}", headers=admin_headers)
    assert response.status_code == 200

    after = client.get("/api/candidates?page_size=100", headers=admin_headers).json()
    assert after["meta"]["total"] == before - 1
    assert all(item["id"] != candidate_id for item in after["items"])
