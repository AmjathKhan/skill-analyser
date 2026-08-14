"""Rule-based resume extraction tests (no AI extras required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.document_parser import extract_document
from app.ai.extractors import estimate_total_experience, parse_resume_text, segment_sections

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "sample_resumes"


@pytest.fixture(scope="module")
def parsed_fullstack():
    text = (SAMPLES / "priya_sharma_fullstack.txt").read_text(encoding="utf-8")
    return parse_resume_text(text)


def test_sections_are_detected(resume_text: str) -> None:
    sections = segment_sections(resume_text)
    keys = set(sections)
    assert {"experience", "education", "skills"} <= keys
    assert sections["education"].strip()


def test_personal_information(parsed_fullstack) -> None:
    personal = parsed_fullstack.personal
    assert personal.full_name == "Priya Sharma"
    assert personal.email == "priya.sharma@example.com"
    assert personal.phone and "98450" in personal.phone.replace(" ", "")
    assert personal.linkedin_url and "linkedin.com" in personal.linkedin_url
    assert personal.github_url and "github.com" in personal.github_url
    assert "Bengaluru" in " ".join(filter(None, [personal.city, personal.address or ""]))


def test_experience_extraction(parsed_fullstack) -> None:
    companies = {experience.company_name for experience in parsed_fullstack.experiences}
    assert any("Zentara" in company for company in companies if company)
    assert any(experience.is_current for experience in parsed_fullstack.experiences)
    current = next(experience for experience in parsed_fullstack.experiences if experience.is_current)
    assert current.job_title and "Engineer" in current.job_title


def test_education_extraction(parsed_fullstack) -> None:
    institutions = " ".join((item.institution or "") for item in parsed_fullstack.educations)
    degrees = " ".join((item.degree or "") for item in parsed_fullstack.educations)
    assert "Indian Institute of Technology" in institutions or "IIT" in institutions
    assert any(marker in degrees for marker in ("Master", "M.Tech", "Bachelor", "B.E"))
    assert any(item.graduation_year == 2016 for item in parsed_fullstack.educations)


def test_certifications_and_languages(parsed_fullstack) -> None:
    certifications = " ".join(item.name for item in parsed_fullstack.certifications)
    assert "AWS" in certifications
    assert {"English", "Hindi"} <= {language.title() for language in parsed_fullstack.languages}


def test_projects_extraction(parsed_fullstack) -> None:
    names = " ".join(project.name for project in parsed_fullstack.projects)
    assert "SkillGraph" in names or "Analytics" in names


def test_skill_mentions_include_core_stack(parsed_fullstack) -> None:
    mentions = {mention.raw_text.lower() for mention in parsed_fullstack.skill_mentions}
    for expected in ("python", "reactjs", "postgresql", "docker"):
        assert any(expected in mention.replace(" ", "") for mention in mentions), expected


def test_total_experience_is_reasonable(parsed_fullstack, resume_text: str) -> None:
    years = estimate_total_experience(resume_text, parsed_fullstack.experiences)
    assert 6 <= years <= 12
    assert 6 <= parsed_fullstack.total_experience_years <= 12


def test_extract_document_reads_txt(tmp_path: Path) -> None:
    path = tmp_path / "candidate.txt"
    path.write_text("Jane Doe\nPython developer\n", encoding="utf-8")
    content = extract_document(path)
    assert "Python developer" in content.text
    assert content.backend
    assert content.word_count >= 3


def test_extract_document_reads_generated_pdf(tmp_path: Path) -> None:
    reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    pdf_path = tmp_path / "candidate.pdf"
    pdf = reportlab_canvas.Canvas(str(pdf_path))
    pdf.drawString(72, 760, "Sanjay Kumar")
    pdf.drawString(72, 740, "Skills: Python, Kubernetes, PostgreSQL")
    pdf.save()

    content = extract_document(pdf_path)
    assert "Sanjay Kumar" in content.text
    assert "Kubernetes" in content.text
    assert content.page_count == 1


def test_extract_document_reads_generated_docx(tmp_path: Path) -> None:
    Document = pytest.importorskip("docx").Document
    path = tmp_path / "candidate.docx"
    document = Document()
    document.add_paragraph("Meera Nair")
    document.add_paragraph("meera.nair@example.com")
    document.add_heading("Technical Skills", level=2)
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Python"
    table.rows[0].cells[1].text = "FastAPI, PostgreSQL, Docker"
    document.add_heading("Experience", level=2)
    document.add_paragraph("Backend Engineer - Nimbus Labs (Jan 2021 - Present)")
    document.save(str(path))

    content = extract_document(path)
    assert "Meera Nair" in content.text
    assert "Python" in content.text
    assert "FastAPI" in content.text
    assert content.backend in {"python-docx", "docx-xml"}


def test_extract_document_sniffs_pdf_with_wrong_extension(tmp_path: Path) -> None:
    reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    pdf_path = tmp_path / "candidate.docx"
    pdf = reportlab_canvas.Canvas(str(pdf_path))
    pdf.drawString(72, 760, "Wrong Extension Candidate")
    pdf.drawString(72, 740, "Skills: Python")
    pdf.save()

    content = extract_document(pdf_path)
    assert "Wrong Extension Candidate" in content.text


def test_parse_resume_text_handles_empty_input() -> None:
    parsed = parse_resume_text("")
    assert parsed.personal.full_name is None
    assert parsed.experiences == []
