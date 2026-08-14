"""AI skill matching: scoring, ranking and explainability."""

from __future__ import annotations

from fastapi.testclient import TestClient

FULLSTACK_CRITERIA = {
    "required_skills": ["Python", "ReactJS", "FastAPI", "PostgreSQL", "AWS"],
    "min_experience_years": 5,
    "preferred_certifications": ["AWS Certified Solutions Architect"],
    "top_k": 10,
}


def test_skill_match_ranks_the_right_candidate_first(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    response = client.post("/api/skill-match", json=FULLSTACK_CRITERIA, headers=recruiter_headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["total_candidates_evaluated"] >= 3
    assert body["results"], "expected at least one ranked candidate"
    assert body["embedding_model"] and body["graph_backend"]

    top = body["results"][0]
    assert top["full_name"] == "Priya Sharma"
    assert top["rank"] == 1
    assert 0 <= top["overall_score"] <= 100
    scores = [item["overall_score"] for item in body["results"]]
    assert scores == sorted(scores, reverse=True)
    assert [item["rank"] for item in body["results"]] == list(range(1, len(body["results"]) + 1))


def test_match_result_is_explainable(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    body = client.post("/api/skill-match", json=FULLSTACK_CRITERIA, headers=recruiter_headers).json()
    top = body["results"][0]

    matched = {item["requested"] for item in top["matched_skills"]}
    assert {"Python", "ReactJS", "FastAPI", "PostgreSQL"} <= matched
    assert all(item["match_type"] != "missing" for item in top["matched_skills"])
    assert all(item["evidence"] or item["matched_skill"] for item in top["matched_skills"])

    assert top["explanation"]
    assert str(round(top["overall_score"])) in top["explanation"] or "%" in top["explanation"]
    assert top["recommendation"] in {
        "Highly Recommended",
        "Recommended",
        "Consider",
        "Not Recommended",
    }
    assert 0 <= top["confidence"] <= 100
    assert top["interview_questions"]
    assert top["strengths"]

    breakdown = top["breakdown"]
    weights = breakdown["weights"]
    assert abs(sum(weights.values()) - 1.0) < 0.01
    contributions = sum(component["contribution"] for component in breakdown["components"])
    assert abs(contributions - top["overall_score"]) < 1.5
    assert {component["name"] for component in breakdown["components"]} == {
        "skill",
        "semantic",
        "experience",
        "certification",
        "project",
    }


def test_missing_skills_are_reported(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    criteria = {**FULLSTACK_CRITERIA, "required_skills": ["Python", "COBOL", "Fortran"], "top_k": 5}
    body = client.post("/api/skill-match", json=criteria, headers=recruiter_headers).json()
    top = body["results"][0]
    missing = {item["requested"] for item in top["missing_skills"]}
    assert {"COBOL", "Fortran"} <= missing
    assert top["learning_recommendations"]


def test_related_skills_give_partial_credit(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    """Django is not on Priya's resume but is RELATED_TO Python in the taxonomy."""
    criteria = {"required_skills": ["Django"], "top_k": 10, "min_score": 0}
    body = client.post("/api/skill-match", json=criteria, headers=recruiter_headers).json()
    assert body["results"]
    evidences = [
        evidence
        for match in body["results"]
        for evidence in (*match["matched_skills"], *match["related_skills"])
        if evidence["requested"] == "Django"
    ]
    assert evidences, "expected graph-expanded evidence for Django"
    assert any(item["graph_path"] or item["match_type"] in {"related", "parent", "child"} for item in evidences)


def test_mandatory_skill_filters_out_candidates(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    criteria = {
        "required_skills": ["Python", "Apache Spark"],
        "mandatory_skills": ["Apache Spark"],
        "top_k": 10,
    }
    body = client.post("/api/skill-match", json=criteria, headers=recruiter_headers).json()
    top = body["results"][0]
    assert top["full_name"] == "Arjun Mehta"
    assert any(
        item["requested"].lower() == "apache spark" and item["mandatory"] for item in top["matched_skills"]
    )


def test_experience_filter_is_applied(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    criteria = {"required_skills": ["Python"], "min_experience_years": 9, "top_k": 10}
    body = client.post("/api/skill-match", json=criteria, headers=recruiter_headers).json()
    for match in body["results"]:
        assert match["breakdown"]["experience_score"] >= 0
    assert body["results"][0]["total_experience_years"] >= 8


def test_custom_weights_change_the_ranking_inputs(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    criteria = {
        **FULLSTACK_CRITERIA,
        "weights": {"skill": 1.0, "semantic": 0.0, "experience": 0.0, "certification": 0.0, "project": 0.0},
    }
    body = client.post("/api/skill-match", json=criteria, headers=recruiter_headers).json()
    top = body["results"][0]
    assert top["breakdown"]["weights"]["skill"] == 1.0
    assert abs(top["overall_score"] - top["breakdown"]["skill_score"]) < 1.0


def test_match_runs_are_persisted_and_listable(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    created = client.post(
        "/api/skill-match",
        json={**FULLSTACK_CRITERIA, "job_title": "Senior Full Stack Engineer"},
        headers=recruiter_headers,
    ).json()
    assert created["run_id"]

    runs = client.get("/api/skill-match/runs", headers=recruiter_headers)
    assert runs.status_code == 200
    assert any(run["id"] == created["run_id"] for run in runs.json())

    detail = client.get(f"/api/skill-match/runs/{created['run_id']}", headers=recruiter_headers)
    assert detail.status_code == 200
    assert detail.json()["results"]


def test_score_single_candidate_endpoint(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    candidate_id = uploaded_candidates[0]["candidate_id"]
    response = client.post(
        f"/api/candidate/{candidate_id}/score", json=FULLSTACK_CRITERIA, headers=recruiter_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["candidate_id"] == candidate_id
    assert body["explanation"]


def test_gap_analysis(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    response = client.post(
        "/api/skill-match/gap-analysis",
        json=["Python", "Kubernetes", "COBOL"],
        headers=recruiter_headers,
    )
    assert response.status_code == 200
    items = {item["skill"]: item for item in response.json()}
    assert items["Python"]["candidates_with_skill"] >= 2
    assert items["COBOL"]["candidates_with_skill"] == 0
    assert 0 <= items["Python"]["coverage_percent"] <= 100


def test_hiring_manager_cannot_run_matching(client: TestClient, manager_headers) -> None:
    response = client.post("/api/skill-match", json=FULLSTACK_CRITERIA, headers=manager_headers)
    assert response.status_code in {200, 403}
