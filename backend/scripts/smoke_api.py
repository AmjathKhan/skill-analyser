"""End-to-end smoke test against a running API.

    python scripts/smoke_api.py http://127.0.0.1:8000

Logs in as the bootstrap admin and exercises every major endpoint so a deployment
can be verified without opening the UI.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
EMAIL = sys.argv[2] if len(sys.argv) > 2 else "admin@skillanalyser.ai"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "Admin@123456"

failures: list[str] = []


def call(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: Any | None = None,
    raw: bool = False,
) -> Any:
    url = f"{BASE}/api{path}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read()
    return payload if raw else json.loads(payload)


def check(label: str, fn) -> Any:
    try:
        result = fn()
    except urllib.error.HTTPError as exc:
        failures.append(f"{label}: HTTP {exc.code} {exc.read()[:200]!r}")
        print(f"  FAIL  {label}: HTTP {exc.code}")
        return None
    except Exception as exc:
        failures.append(f"{label}: {exc}")
        print(f"  FAIL  {label}: {exc}")
        return None
    print(f"  ok    {label}")
    return result


def main() -> int:
    print(f"Smoke testing {BASE}")

    health = check("GET /health", lambda: call("GET", "/health"))
    if health:
        print(
            f"        graph={health['graph_backend']} vectors={health['vector_backend']} "
            f"skills={health['skills_loaded']} llm={health['llm_backend']}"
        )

    tokens = check(
        "POST /login",
        lambda: call("POST", "/login", body={"email": EMAIL, "password": PASSWORD}),
    )
    if not tokens:
        print("\nCannot continue without a session.")
        return 1
    token = tokens["access_token"]

    check("GET /me", lambda: call("GET", "/me", token=token))

    dashboard = check("GET /dashboard", lambda: call("GET", "/dashboard", token=token))
    if dashboard:
        cards = dashboard["cards"]
        print(f"        {cards['total_candidates']} candidates / {cards['uploaded_resumes']} resumes")

    candidates = check("GET /candidates", lambda: call("GET", "/candidates?page_size=5", token=token))
    candidate_id = candidates["items"][0]["id"] if candidates and candidates["items"] else None

    if candidate_id:
        check(f"GET /candidate/{candidate_id}", lambda: call("GET", f"/candidate/{candidate_id}", token=token))
        check(
            f"GET /candidate/{candidate_id}/similar",
            lambda: call("GET", f"/candidate/{candidate_id}/similar?limit=3", token=token),
        )
        check(
            f"GET /graph/candidate/{candidate_id}",
            lambda: call("GET", f"/graph/candidate/{candidate_id}?depth=2", token=token),
        )

    match = check(
        "POST /skill-match",
        lambda: call(
            "POST",
            "/skill-match",
            token=token,
            body={
                "required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
                "preferred_skills": ["AWS", "Kubernetes"],
                "min_experience_years": 3,
                "top_k": 5,
            },
        ),
    )
    if match and match["results"]:
        top = match["results"][0]
        print(f"        top: {top['full_name']} {top['overall_score']}% ({top['recommendation']})")

    search = check(
        "POST /search",
        lambda: call(
            "POST",
            "/search",
            token=token,
            body={
                "query": "Python developer with 5 years experience in Kubernetes",
                "mode": "hybrid",
                "include_answer": True,
            },
        ),
    )
    if search:
        print(f"        {search['total']} hits, skills parsed: {search['interpreted_skills']}")

    check("GET /search/suggest", lambda: call("GET", "/search/suggest?q=pyt", token=token))
    check("GET /graph/stats", lambda: call("GET", "/graph/stats", token=token))
    check("GET /graph/overview", lambda: call("GET", "/graph/overview?limit=80", token=token))
    check("GET /graph/skills", lambda: call("GET", "/graph/skills?limit=20", token=token))
    check("GET /skills", lambda: call("GET", "/skills?limit=20", token=token))
    check("GET /skills/categories", lambda: call("GET", "/skills/categories", token=token))
    check("GET /job-requirements", lambda: call("GET", "/job-requirements", token=token))
    check("GET /resumes", lambda: call("GET", "/resumes?page_size=5", token=token))
    check("GET /reports", lambda: call("GET", "/reports?months=6", token=token))
    check(
        "GET /reports/export?format=csv",
        lambda: call("GET", "/reports/export?format=csv", token=token, raw=True),
    )
    check(
        "GET /reports/export?format=pdf",
        lambda: call("GET", "/reports/export?format=pdf", token=token, raw=True),
    )
    check("GET /users", lambda: call("GET", "/users", token=token))
    check("GET /users/audit/logs", lambda: call("GET", "/users/audit/logs?page_size=5", token=token))
    check("POST /logout", lambda: call("POST", "/logout", token=token, body={"all_sessions": False}))

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
