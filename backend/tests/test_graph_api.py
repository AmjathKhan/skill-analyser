"""Knowledge graph API: build, stats and visualization views."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_graph_stats(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    response = client.get("/api/graph/stats", headers=recruiter_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["backend"] in {"networkx", "neo4j"}
    assert body["healthy"] is True
    assert body["node_count"] > 100
    assert body["node_counts"]["Candidate"] >= 3
    assert body["relationship_counts"]["HAS_SKILL"] > 0


def test_rebuild_graph(client: TestClient, admin_headers, uploaded_candidates) -> None:
    response = client.post("/api/graph/build", json={"clear": True}, headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["nodes"] > 100
    assert body["edges"] > 100
    assert body["candidates"] >= 3
    assert body["duration_ms"] >= 0


def test_recruiter_cannot_rebuild_graph(client: TestClient, manager_headers) -> None:
    response = client.post("/api/graph/build", json={"clear": False}, headers=manager_headers)
    assert response.status_code == 403


def test_candidate_graph_view(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    candidate_id = uploaded_candidates[0]["candidate_id"]
    response = client.get(f"/api/graph/candidate/{candidate_id}?depth=2", headers=recruiter_headers)
    assert response.status_code == 200
    body = response.json()

    labels = {node["label"] for node in body["nodes"]}
    assert "Candidate" in labels and "Skill" in labels
    assert body["edges"]
    relations = {edge["relation"] for edge in body["edges"]}
    assert "HAS_SKILL" in relations
    node_keys = {node["id"] for node in body["nodes"]}
    assert all(edge["source"] in node_keys and edge["target"] in node_keys for edge in body["edges"])


def test_skill_graph_view(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    response = client.get("/api/graph/skill/Python?depth=2", headers=recruiter_headers)
    assert response.status_code == 200
    body = response.json()
    names = {node["name"] for node in body["nodes"]}
    assert "Python" in names
    assert len(names) > 3


def test_skills_graph_listing(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    response = client.get("/api/graph/skills?limit=25", headers=recruiter_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["skills"]
    assert body["total_skills"] >= len(body["skills"])
    assert body["categories"]
    top = body["skills"][0]
    assert {"skill", "category", "candidate_count", "related"} <= set(top)
    counts = [item["candidate_count"] for item in body["skills"]]
    assert counts == sorted(counts, reverse=True)


def test_graph_overview(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    response = client.get("/api/graph/overview?limit=120", headers=recruiter_headers)
    assert response.status_code == 200
    body = response.json()
    assert 0 < len(body["nodes"]) <= 120
    assert body["edges"]
