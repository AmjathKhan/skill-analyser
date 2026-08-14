"""Semantic / keyword / graph / skill / hybrid candidate search."""

from __future__ import annotations

from fastapi.testclient import TestClient


def search(client: TestClient, headers: dict[str, str], **payload) -> dict:
    response = client.post("/api/search", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_natural_language_query_is_interpreted(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    body = search(client, recruiter_headers, query="Python React PostgreSQL FastAPI 5 years", mode="hybrid")
    interpreted = {skill.lower() for skill in body["interpreted_skills"]}
    assert {"python", "reactjs", "postgresql", "fastapi"} <= interpreted
    assert body["interpreted_experience"] == 5
    assert body["items"]
    assert body["items"][0]["full_name"] == "Priya Sharma"
    assert body["duration_ms"] >= 0


def test_hybrid_hits_expose_score_channels(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    body = search(client, recruiter_headers, query="python fastapi postgresql", mode="hybrid")
    hit = body["items"][0]
    assert hit["ai_score"] > 0
    assert hit["channels"]
    assert hit["matched_skills"]
    assert hit["top_skills"]
    scores = [item["ai_score"] for item in body["items"]]
    assert scores == sorted(scores, reverse=True)


def test_keyword_mode_matches_free_text(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    body = search(client, recruiter_headers, query="Brightline", mode="keyword")
    assert any(hit["full_name"] == "Arjun Mehta" for hit in body["items"])


def test_keyword_mode_matches_each_term_separately(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    """A multi word query must not be treated as a single literal phrase."""
    body = search(client, recruiter_headers, query="Python Kubernetes", mode="keyword")
    assert body["items"]
    assert all(hit["keyword_score"] > 0 for hit in body["items"])


def test_technology_after_in_is_not_read_as_a_location(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    """`... in Kubernetes` describes a skill, not a city, so nothing may be filtered out."""
    body = search(
        client,
        recruiter_headers,
        query="Python developer with 5 years experience in Kubernetes",
        mode="hybrid",
    )
    assert body["items"]
    assert body["interpreted_experience"] == 5
    assert {"Python", "Kubernetes"} <= set(body["interpreted_skills"])


def test_city_after_in_still_filters(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    body = search(client, recruiter_headers, query="Frontend engineer in Hyderabad", mode="hybrid")
    assert body["items"]
    assert all("Hyderabad" in (hit["location"] or "") for hit in body["items"])


def test_semantic_mode_returns_ranked_results(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    body = search(
        client,
        recruiter_headers,
        query="engineer who builds machine learning retrieval systems",
        mode="semantic",
    )
    assert body["items"]
    assert all(hit["semantic_score"] >= 0 for hit in body["items"])


def test_graph_mode_uses_the_knowledge_graph(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    body = search(client, recruiter_headers, query="Kubernetes Terraform", mode="graph")
    assert body["items"]
    assert any(hit["graph_score"] > 0 for hit in body["items"])
    assert any(hit["full_name"] == "Rahul Iyer" for hit in body["items"])


def test_skill_mode_reports_missing_skills(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    body = search(client, recruiter_headers, query="Python PHP", mode="skill")
    assert body["items"]
    assert any("PHP" in hit["missing_skills"] for hit in body["items"])


def test_filters_narrow_results(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    unfiltered = search(client, recruiter_headers, query="python", mode="hybrid")
    filtered = search(
        client,
        recruiter_headers,
        query="python",
        mode="hybrid",
        filters={"min_experience": 9},
    )
    assert filtered["total"] <= unfiltered["total"]
    assert all(hit["total_experience_years"] >= 9 for hit in filtered["items"])


def test_sorting_by_experience(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    body = search(client, recruiter_headers, query="", mode="keyword", sort_by="experience", sort_dir="desc")
    years = [hit["total_experience_years"] for hit in body["items"]]
    assert years == sorted(years, reverse=True)


def test_pagination(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    first = search(client, recruiter_headers, query="", mode="keyword", page=1, page_size=2)
    second = search(client, recruiter_headers, query="", mode="keyword", page=2, page_size=2)
    assert len(first["items"]) == 2
    assert first["page"] == 1 and second["page"] == 2
    assert {hit["candidate_id"] for hit in first["items"]} & {
        hit["candidate_id"] for hit in second["items"]
    } == set()


def test_unknown_terms_are_reported(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    body = search(client, recruiter_headers, query="Python Blorptech", mode="hybrid")
    assert any("blorptech" in term.lower() for term in body["unknown_terms"])


def test_rag_answer_is_generated_on_request(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    body = search(
        client,
        recruiter_headers,
        query="Who is the best fit for a FastAPI and PostgreSQL backend role?",
        mode="hybrid",
        include_answer=True,
    )
    assert body["answer"]
    assert body["answer_backend"]
    assert "Priya" in body["answer"] or body["items"][0]["full_name"] in body["answer"]


def test_suggest_autocompletes_skills_and_candidates(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    response = client.get("/api/search/suggest?q=pyth", headers=recruiter_headers)
    assert response.status_code == 200
    body = response.json()
    assert any("python" in skill.lower() for skill in body["skills"])

    names = client.get("/api/search/suggest?q=priy", headers=recruiter_headers).json()
    assert any("Priya" in candidate["full_name"] for candidate in names["candidates"])
