"""Dashboard metrics, reports and exports, skills KB and job requirements."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_and_system_info(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["graph_healthy"] is True
    assert body["skills_loaded"] > 50

    info = client.get("/api/system/info").json()
    assert info["ai"]["embedding_dim"] > 0
    assert info["graph"]["backend"]
    assert abs(sum(info["matching_weights"].values()) - 1.0) < 0.01


def test_dashboard_payload(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    response = client.get("/api/dashboard", headers=recruiter_headers)
    assert response.status_code == 200
    body = response.json()

    cards = body["cards"]
    assert cards["total_candidates"] >= 3
    assert cards["uploaded_resumes"] >= 3
    assert cards["average_experience_years"] > 0

    assert body["top_skills"]
    assert body["technology_distribution"]
    assert body["experience_distribution"]
    assert body["candidate_status"]
    assert body["hiring_trends"]
    assert body["recent_activity"]
    assert body["recent_uploads"]
    assert body["graph"]["node_count"] > 0

    top_skill_values = [item["value"] for item in body["top_skills"]]
    assert top_skill_values == sorted(top_skill_values, reverse=True)


def test_reports_contain_kpis_and_gaps(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    response = client.get(
        "/api/reports?months=6&gap_skills=Python&gap_skills=Kubernetes", headers=recruiter_headers
    )
    assert response.status_code == 200
    body = response.json()

    kpis = body["kpis"]
    assert kpis["total_candidates"] >= 3
    assert kpis["resumes_processed"] >= 3
    assert 0 <= kpis["parse_success_rate"] <= 100
    assert 0 <= kpis["taxonomy_coverage_percent"] <= 100
    assert kpis["skills_per_candidate"] > 0

    assert body["top_technologies"]
    assert body["top_skills"]
    assert body["pipeline"]
    assert body["period_start"]
    assert body["period_end"]
    assert body["insights"]
    assert "hired" in kpis
    assert kpis["unique_skills"] >= 0
    assert abs(sum(stage["percent"] for stage in body["pipeline"]) - 100) < 1.5
    assert {gap["skill"] for gap in body["skill_gaps"]} == {"Python", "Kubernetes"}


def test_report_exports(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    csv_export = client.get("/api/reports/export?format=csv", headers=recruiter_headers)
    assert csv_export.status_code == 200
    assert csv_export.headers["content-type"].startswith("text/csv")
    assert b"Recruitment Report" in csv_export.content
    assert b"Section,Metric" in csv_export.content

    pdf_export = client.get("/api/reports/export?format=pdf", headers=recruiter_headers)
    assert pdf_export.status_code == 200
    assert pdf_export.content.startswith(b"%PDF")

    excel_export = client.get("/api/reports/export?format=excel", headers=recruiter_headers)
    assert excel_export.status_code == 200
    assert excel_export.content[:2] == b"PK"  # xlsx is a zip container

    candidates_csv = client.get("/api/reports/candidates/export", headers=recruiter_headers)
    assert candidates_csv.status_code == 200
    assert b"candidate id,name,email" in candidates_csv.content.lower()


def test_skills_knowledge_base_endpoints(client: TestClient, recruiter_headers, uploaded_candidates) -> None:
    listing = client.get("/api/skills?limit=50", headers=recruiter_headers)
    assert listing.status_code == 200
    skills = listing.json()
    assert skills
    assert any(skill["name"] == "Python" for skill in skills)
    python = next(skill for skill in skills if skill["name"] == "Python")
    assert python["synonyms"]
    assert python["related_skills"]
    assert python["candidate_count"] >= 2

    filtered = client.get("/api/skills?search=kuber", headers=recruiter_headers).json()
    assert any("kubernetes" in skill["name"].lower() for skill in filtered)

    categories = client.get("/api/skills/categories", headers=recruiter_headers).json()
    assert len(categories) > 5
    assert all(category["skill_count"] > 0 for category in categories)

    stats = client.get("/api/skills/stats", headers=recruiter_headers).json()
    assert stats["taxonomy_size"] > 50
    assert stats["candidate_skill_links"] > 0
    assert 0 <= stats["coverage_percent"] <= 100


def test_skill_import_is_admin_only(client: TestClient, recruiter_headers, admin_headers) -> None:
    assert client.post("/api/skills/import", headers=recruiter_headers).status_code == 403

    response = client.post("/api/skills/import?generate_embeddings=false", headers=admin_headers)
    assert response.status_code == 200
    report = response.json()
    assert report["skills_created"] == 0
    assert report["rows_read"] > 50


def test_skills_csv_export_and_upload_round_trip(client: TestClient, recruiter_headers, admin_headers) -> None:
    assert client.get("/api/skills/export", headers=recruiter_headers).status_code == 403

    exported = client.get("/api/skills/export", headers=admin_headers)
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "skills-knowledge-base.csv" in exported.headers.get("content-disposition", "")
    text = exported.content.decode("utf-8-sig")
    header = text.splitlines()[0]
    assert header == (
        "skill_id,skill_name,category,parent_skill,related_skills,"
        "technology_stack,job_role,experience_level,skill_synonyms,skill_description"
    )
    assert "Python" in text
    assert "SK001" in text

    payload = (
        "skill_id,skill_name,category,parent_skill,related_skills,"
        "technology_stack,job_role,experience_level,skill_synonyms,skill_description\n"
        "SK998,SkillAnalyser CSV Test Skill,API Technology,,GraphQL,Backend,"
        "Backend Developer,intermediate,CSV Test Skill,Unique skill used to verify CSV upload creates rows.\n"
        "SK999,GraphQL,API Technology,,NodeJS,Backend,"
        "Backend Developer,intermediate,GQL;Graph QL,Query language for APIs.\n"
    )
    uploaded = client.post(
        "/api/skills/import/upload?generate_embeddings=false",
        headers=admin_headers,
        files={"file": ("skills.csv", payload.encode("utf-8"), "text/csv")},
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["skills_created"] >= 1
    assert body["skills_updated"] >= 1

    listing = client.get("/api/skills?search=SkillAnalyser CSV Test", headers=admin_headers).json()
    created = next(skill for skill in listing if skill["name"] == "SkillAnalyser CSV Test Skill")
    assert created["external_id"] == "SK998"

    graphql = next(
        skill
        for skill in client.get("/api/skills?search=graphql", headers=admin_headers).json()
        if skill["name"] == "GraphQL"
    )
    assert graphql["external_id"] == "SK999"

    python = client.get("/api/skills?search=python", headers=admin_headers).json()
    assert any(skill["name"] == "Python" for skill in python)


def test_skills_csv_upload_rejects_wrong_format(client: TestClient, admin_headers) -> None:
    before = client.get("/api/skills/stats", headers=admin_headers).json()["taxonomy_size"]

    def upload(name: str, content: bytes, content_type: str = "text/csv"):
        return client.post(
            "/api/skills/import/upload?generate_embeddings=false",
            headers=admin_headers,
            files={"file": (name, content, content_type)},
        )

    cases = [
        ("skills.xlsx", b"PK\x03\x04not-an-excel-file"),
        ("skills.csv", b"%PDF-1.4\n%wrong"),
        ("skills.csv", b""),
        ("skills.csv", b"name,email,phone\nAda,ada@example.com,1\n"),
        ("notes.txt", b"skill_id,skill_name,category\nSK1,Python,Language\n"),
        ("skills.csv", b"skill_id,skill_name,category\n"),
        ("skills.csv", b'{"skill_name": "Python"}\n'),
    ]
    for name, content in cases:
        response = upload(name, content)
        assert response.status_code in {415, 422}, (name, response.status_code, response.text)
        payload = response.json()
        assert payload["error"]["message"]
        assert "skill" in payload["error"]["message"].lower() or "csv" in payload["error"]["message"].lower() or "empty" in payload["error"]["message"].lower() or "format" in payload["error"]["message"].lower()

    after = client.get("/api/skills/stats", headers=admin_headers).json()["taxonomy_size"]
    assert after == before


def test_job_requirement_crud(client: TestClient, recruiter_headers) -> None:
    payload = {
        "title": "Backend Engineer (Python)",
        "department": "Engineering",
        "location": "Bengaluru",
        "description": "Own our FastAPI services and PostgreSQL data model.",
        "min_experience_years": 4,
        "required_skills": ["Python", "FastAPI", "PostgreSQL"],
        "preferred_skills": ["Docker", "AWS"],
        "preferred_certifications": ["AWS Certified Developer"],
    }
    created = client.post("/api/job-requirements", json=payload, headers=recruiter_headers)
    assert created.status_code == 201, created.text
    requirement = created.json()
    assert requirement["required_skills"] == ["Python", "FastAPI", "PostgreSQL"]

    listed = client.get("/api/job-requirements", headers=recruiter_headers).json()
    assert any(item["id"] == requirement["id"] for item in listed)

    updated = client.put(
        f"/api/job-requirements/{requirement['id']}",
        json={**payload, "min_experience_years": 6},
        headers=recruiter_headers,
    ).json()
    assert updated["min_experience_years"] == 6

    deleted = client.delete(f"/api/job-requirements/{requirement['id']}", headers=recruiter_headers)
    assert deleted.status_code == 200
    assert client.get(f"/api/job-requirements/{requirement['id']}", headers=recruiter_headers).status_code == 404


def test_matching_from_a_job_requirement(
    client: TestClient, recruiter_headers, uploaded_candidates
) -> None:
    requirement = client.post(
        "/api/job-requirements",
        json={
            "title": "ML Engineer (NLP)",
            "description": "Transformers, PyTorch and retrieval systems.",
            "min_experience_years": 3,
            "required_skills": ["Python", "PyTorch", "Natural Language Processing"],
            "preferred_skills": ["Hugging Face Transformers"],
        },
        headers=recruiter_headers,
    ).json()

    response = client.post(
        "/api/skill-match",
        json={"job_requirement_id": requirement["id"], "top_k": 5},
        headers=recruiter_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["criteria"]["required_skills"]
    assert body["results"][0]["full_name"] == "Sara Khan"
