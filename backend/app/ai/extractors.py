"""Rule-based (spaCy-assisted) resume entity extraction.

The extractor is intentionally deterministic: every field is derived from
regex/heuristic rules so results are reproducible and explainable. When spaCy is
installed its NER output is used to reinforce person/organization detection.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterable
from datetime import date

from app.ai import nlp
from app.ai.text_utils import clean_text, normalize_key, title_case, truncate
from app.core.constants import SkillSource
from app.schemas.parsed import (
    ParsedCertification,
    ParsedEducation,
    ParsedExperience,
    ParsedPersonal,
    ParsedProject,
    ParsedResume,
    SkillMention,
)

# --------------------------------------------------------------------------- regexes
EMAIL_RE = re.compile(r"[\w!#$%&'*+/=?^_`{|}~.-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(
    r"(?:(?<![\d\w])(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{3,5}[\s.-]?\d{3,4}(?:[\s.-]?\d{2,4})?(?![\d\w]))"
)
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/(?:in|pub|profile)/[\w\-%./]+", re.I)
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w\-.]+", re.I)
URL_RE = re.compile(r"(?:https?://|www\.)[\w\-./%?=&#+~:]+", re.I)

MONTHS = {name.lower(): index for index, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): index for index, name in enumerate(calendar.month_abbr) if name})
MONTHS.update({"sept": 9})

_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))
_DATE_TOKEN = rf"(?:(?:{_MONTH_ALT})[a-z]*\.?[\s,-]*\d{{4}}|\d{{1,2}}[/-]\d{{4}}|\d{{4}}[/-]\d{{1,2}}|\d{{4}})"
_PRESENT = r"(?:present|current|now|till\s+date|to\s+date|ongoing|date)"
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE_TOKEN})\s*(?:-|--|\u2013|\u2014|to|until|through)\s*(?P<end>{_DATE_TOKEN}|{_PRESENT})",
    re.IGNORECASE,
)
SINGLE_DATE_RE = re.compile(_DATE_TOKEN, re.IGNORECASE)
YEAR_RE = re.compile(r"(19[7-9]\d|20[0-4]\d)")

TOTAL_EXPERIENCE_RE = re.compile(
    r"(?:total\s+(?:of\s+)?)?(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)(?:\s*(?:\d{1,2}\s*months?)?)?"
    r"(?:\s*(?:of|in|as)?\s*(?:relevant\s+|professional\s+|overall\s+|total\s+|industry\s+)?"
    r"(?:work\s+)?experience)",
    re.IGNORECASE,
)
SKILL_YEARS_RE = re.compile(r"^(?P<name>[^()\[\]]+?)\s*[\(\[]\s*(?P<years>\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)", re.I)

COMPANY_TOKENS = (
    "inc", "inc.", "llc", "ltd", "ltd.", "limited", "pvt", "pvt.", "private", "plc", "gmbh",
    "corp", "corp.", "corporation", "co.", "company", "technologies", "technology", "tech",
    "solutions", "systems", "software", "services", "labs", "consulting", "group", "holdings",
    "infotech", "industries", "enterprises", "sa", "ag", "bv", "srl", "llp",
)
TITLE_TOKENS = (
    "engineer", "developer", "programmer", "manager", "analyst", "architect", "consultant",
    "intern", "trainee", "lead", "designer", "scientist", "administrator", "devops", "sre",
    "specialist", "director", "head", "officer", "president", "founder", "cto", "ceo", "vp",
    "associate", "executive", "coordinator", "recruiter", "tester", "qa", "support", "researcher",
    "fullstack", "full-stack", "frontend", "backend", "principal", "senior", "junior", "staff",
)
DEGREE_PATTERNS = (
    (r"\bph\.?\s?d\b|\bdoctorate\b", "PhD"),
    (r"\bm\.?\s?tech\b|\bmaster of technology\b", "M.Tech"),
    (r"\bm\.?\s?e\b(?![a-z])", "M.E."),
    (r"\bm\.?\s?sc\b|\bmaster of science\b|\bms\b(?=\s+in)", "M.Sc"),
    (r"\bmca\b", "MCA"),
    (r"\bm\.?\s?b\.?\s?a\b", "MBA"),
    (r"\bm\.?\s?com\b", "M.Com"),
    (r"\bm\.?\s?a\b(?![a-z])", "M.A."),
    (r"\bmaster'?s?\b", "Master's"),
    (r"\bb\.?\s?tech\b|\bbachelor of technology\b", "B.Tech"),
    (r"\bb\.?\s?e\b(?![a-z])", "B.E."),
    (r"\bb\.?\s?sc\b|\bbachelor of science\b", "B.Sc"),
    (r"\bbca\b", "BCA"),
    (r"\bb\.?\s?com\b", "B.Com"),
    (r"\bb\.?\s?a\b(?![a-z])", "B.A."),
    (r"\bbachelor'?s?\b", "Bachelor's"),
    (r"\bdiploma\b", "Diploma"),
    (r"\bhigh school\b|\bhsc\b|\bsslc\b|\b12th\b", "High School"),
)
DEGREE_RANK = {
    "PhD": 6, "M.Tech": 5, "M.E.": 5, "M.Sc": 5, "MCA": 5, "MBA": 5, "M.Com": 5, "M.A.": 5,
    "Master's": 5, "B.Tech": 4, "B.E.": 4, "B.Sc": 4, "BCA": 4, "B.Com": 4, "B.A.": 4,
    "Bachelor's": 4, "Diploma": 2, "High School": 1,
}
INSTITUTION_TOKENS = ("university", "college", "institute", "school", "academy", "iit", "nit", "iiit", "polytechnic")
KNOWN_LANGUAGES = {
    "english", "hindi", "tamil", "telugu", "kannada", "malayalam", "marathi", "gujarati", "bengali",
    "punjabi", "urdu", "odia", "assamese", "spanish", "french", "german", "mandarin", "chinese",
    "japanese", "korean", "portuguese", "russian", "arabic", "italian", "dutch", "swedish", "polish",
    "turkish", "vietnamese", "thai", "indonesian", "hebrew", "greek", "danish", "norwegian", "finnish",
}
#: Level suffixes that follow a dash in certification names and are not issuers.
CERT_LEVELS = {
    "associate", "professional", "specialty", "expert", "foundational", "practitioner",
    "fundamentals", "advanced", "core", "basic", "beginner", "level i", "level ii",
}
CERT_HINT_RE = re.compile(
    r"\b(certified|certification|certificate|credential|aws|azure|gcp|google cloud|pmp|scrum|cissp|"
    r"comptia|oracle|cisco|kubernetes|cka|ckad|terraform|salesforce|tableau|databricks|snowflake|"
    r"itil|six sigma|prince2|togaf)\b",
    re.IGNORECASE,
)

SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("contact", re.compile(r"^(contact(\s+(information|details))?|personal\s+(details|information)|profile\s+details)\b", re.I)),
    ("summary", re.compile(r"^(professional\s+)?(summary|profile|objective|about\s+me|career\s+objective|overview|synopsis)\b", re.I)),
    ("experience", re.compile(r"^(work\s+|professional\s+|employment\s+|industry\s+|relevant\s+)?(experience|history|employment|career\s+history|work\s+summary)\b", re.I)),
    ("education", re.compile(r"^(education(al)?(\s+(qualification|background|details|history))?|academics?|academic\s+(background|qualification|details))\b", re.I)),
    ("skills", re.compile(r"^((technical|core|key|professional|it|primary|secondary|soft)\s+)?(skills?|competenc(y|ies)|skill\s+set|technical\s+expertise|technologies|tech\s+stack|areas?\s+of\s+expertise)\b", re.I)),
    ("projects", re.compile(r"^((key|academic|personal|major|selected|notable)\s+)?projects?(\s+(undertaken|handled|details|experience))?\b", re.I)),
    ("certifications", re.compile(r"^(certificat(e|es|ions?)|licen[cs]es?|credentials|training(s)?\s*(and\s*certifications?)?|courses?\s*(and\s*certifications?)?)\b", re.I)),
    ("languages", re.compile(r"^(languages?(\s+known)?|linguistic\s+skills?)\b", re.I)),
    ("achievements", re.compile(r"^(achievements?|awards?|honors?|honours?|accomplishments?|recognitions?)\b", re.I)),
    ("publications", re.compile(r"^(publications?|papers?|patents?|research)\b", re.I)),
    ("interests", re.compile(r"^(interests?|hobbies|extra[\s-]?curricular|activities)\b", re.I)),
    ("references", re.compile(r"^(references?|referees?)\b", re.I)),
    ("declaration", re.compile(r"^(declaration|personal\s+declaration)\b", re.I)),
]


# ------------------------------------------------------------------- section splitting
def _is_section_header(line: str) -> str | None:
    stripped = line.strip().strip(":").strip()
    if not stripped or len(stripped) > 60:
        return None
    words = stripped.split()
    if len(words) > 6:
        return None
    # A header is a short line that is not a sentence and not a bullet of content.
    if stripped.endswith((".", ",", ";")) and not stripped.endswith("..."):
        return None
    for name, pattern in SECTION_PATTERNS:
        if pattern.match(stripped):
            looks_like_header = (
                stripped.isupper()
                or line.strip().endswith(":")
                or len(words) <= 4
                or stripped.istitle()
            )
            if looks_like_header:
                return name
    return None


def segment_sections(text: str) -> dict[str, str]:
    """Split resume text into canonical sections keyed by name."""
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in text.split("\n"):
        section = _is_section_header(line)
        if section:
            current = section
            sections.setdefault(current, [])
            # Some resumes write "Skills: Python, Java" on the header line itself.
            inline = line.split(":", 1)[1].strip() if ":" in line else ""
            if inline:
                sections[current].append(inline)
            continue
        sections.setdefault(current, []).append(line)
    return {
        name: clean_text("\n".join(lines))
        for name, lines in sections.items()
        if any(line.strip() for line in lines)
    }


# ------------------------------------------------------------------- personal details
def _guess_name(text: str, sections: dict[str, str]) -> str | None:
    header = sections.get("header") or text[:600]
    for raw_line in header.split("\n")[:8]:
        line = raw_line.strip(" |,-\u2013")
        if not line or len(line) > 60:
            continue
        if EMAIL_RE.search(line) or URL_RE.search(line) or "@" in line:
            continue
        if any(char.isdigit() for char in line):
            continue
        words = [word for word in re.split(r"[\s.]+", line) if word]
        if not 1 < len(words) <= 5:
            continue
        if any(token in line.lower() for token in ("resume", "curriculum", "vitae", "cv")):
            continue
        alpha_words = [word for word in words if re.fullmatch(r"[A-Za-z'\-]+", word)]
        if len(alpha_words) < len(words):
            continue
        if line.isupper() or all(word[0].isupper() for word in alpha_words):
            return title_case(line) if line.isupper() else line

    for entity, _label in nlp.entities(text[:1200], {"PERSON"}):
        if 1 < len(entity.split()) <= 4:
            return entity
    return None


def _guess_location(text: str) -> tuple[str | None, str | None, str | None]:
    """Return (address, city, country) from the resume header, best effort."""
    head = text[:900]
    for entity, _label in nlp.entities(head, {"GPE", "LOC"}):
        cleaned = entity.strip(" ,")
        if 2 <= len(cleaned) <= 40:
            return cleaned, cleaned, None

    pattern = re.compile(r"(?:address|location|based\s+in|city)\s*[:\-]\s*(.+)", re.I)
    match = pattern.search(head)
    if match:
        address = match.group(1).strip()[:200]
        city = address.split(",")[0].strip() or None
        country = address.split(",")[-1].strip() if "," in address else None
        return address, city, country

    for line in head.split("\n")[:8]:
        candidate = line.strip()
        if (
            4 < len(candidate) < 60
            and candidate.count(",") in (1, 2)
            and not EMAIL_RE.search(candidate)
            and not any(token in candidate.lower() for token in TITLE_TOKENS)
            and not any(char.isdigit() for char in candidate)
        ):
            parts = [part.strip() for part in candidate.split(",")]
            return candidate, parts[0] or None, parts[-1] if len(parts) > 1 else None
    return None, None, None


def extract_personal(text: str, sections: dict[str, str]) -> ParsedPersonal:
    emails = EMAIL_RE.findall(text)
    phones = [match.group(0).strip() for match in PHONE_RE.finditer(text.replace("\n", " "))]
    phones = [phone for phone in phones if 7 <= len(re.sub(r"\D", "", phone)) <= 15]

    linkedin = LINKEDIN_RE.search(text)
    github = GITHUB_RE.search(text)
    portfolio = None
    for url in URL_RE.findall(text):
        lowered = url.lower()
        if "linkedin" in lowered or "github" in lowered or lowered.endswith((".png", ".jpg")):
            continue
        portfolio = url if url.lower().startswith("http") else f"https://{url}"
        break

    address, city, country = _guess_location(text)
    headline = None
    header = sections.get("header", "")
    for line in header.split("\n")[1:6]:
        candidate = line.strip(" |,-\u2013")
        if 5 < len(candidate) <= 90 and any(token in candidate.lower() for token in TITLE_TOKENS):
            headline = candidate
            break

    def _normalize_url(value: str | None) -> str | None:
        if not value:
            return None
        return value if value.lower().startswith("http") else f"https://{value}"

    return ParsedPersonal(
        full_name=_guess_name(text, sections),
        email=emails[0].rstrip(".").lower() if emails else None,
        phone=phones[0] if phones else None,
        address=address,
        city=city,
        country=country,
        linkedin_url=_normalize_url(linkedin.group(0) if linkedin else None),
        github_url=_normalize_url(github.group(0) if github else None),
        portfolio_url=portfolio,
        headline=headline,
    )


# ------------------------------------------------------------------------ date parsing
def parse_partial_date(value: str | None, *, end_of_period: bool = False) -> date | None:
    if not value:
        return None
    text = value.strip().lower().rstrip(".,")
    if re.fullmatch(_PRESENT, text, re.IGNORECASE):
        return None

    month_match = re.search(rf"({_MONTH_ALT})[a-z]*", text)
    year_match = YEAR_RE.search(text)
    if not year_match:
        return None
    year = int(year_match.group(0))

    month: int | None = None
    if month_match:
        month = MONTHS.get(month_match.group(1)[:3]) or MONTHS.get(month_match.group(1))
    else:
        numeric = re.match(r"^(\d{1,2})[/-](\d{4})$", text)
        if numeric:
            month = int(numeric.group(1))
        else:
            numeric = re.match(r"^(\d{4})[/-](\d{1,2})$", text)
            if numeric:
                month = int(numeric.group(2))

    if month is None:
        month = 12 if end_of_period else 1
    month = min(max(month, 1), 12)
    day = calendar.monthrange(year, month)[1] if end_of_period else 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _month_diff(start: date, end: date) -> int:
    return max(0, (end.year - start.year) * 12 + (end.month - start.month) + 1)


def _merge_ranges(ranges: list[tuple[date, date]]) -> float:
    """Total years covered by possibly overlapping employment ranges."""
    if not ranges:
        return 0.0
    ordered = sorted(ranges)
    merged: list[tuple[date, date]] = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    months = sum(_month_diff(start, end) for start, end in merged)
    return round(months / 12, 1)


# -------------------------------------------------------------------------- experience
def _split_blocks(section_text: str) -> list[list[str]]:
    """Group section lines into entries: a new entry starts at a date range or a header line."""
    lines = [line for line in section_text.split("\n") if line.strip()]
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        starts_entry = bool(DATE_RANGE_RE.search(line)) or _looks_like_entry_header(line)
        if starts_entry and current and (any(DATE_RANGE_RE.search(item) for item in current) or len(current) > 1):
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _looks_like_entry_header(line: str) -> bool:
    lowered = line.lower()
    if len(line) > 130:
        return False
    has_separator = any(sep in line for sep in (" at ", " | ", " - ", " \u2013 ", ", "))
    has_title = any(token in lowered for token in TITLE_TOKENS)
    has_company = any(f" {token}" in f" {lowered}" for token in COMPANY_TOKENS)
    return has_separator and (has_title or has_company)


def _clean_company_name(value: str) -> tuple[str, str | None]:
    """``Brightline Analytics, Gurugram ()`` -> ``('Brightline Analytics', 'Gurugram')``."""
    value = re.sub(r"\(\s*\)", " ", value)
    value = re.sub(r"\s{2,}", " ", value).strip(" .,|-\u2013")
    parts = [part.strip() for part in value.split(",") if part.strip()]
    location = None
    if len(parts) > 1:
        tail = parts[-1]
        tail_lower = f" {tail.lower()} "
        is_corporate = any(f" {token} " in tail_lower or tail.lower().endswith(token) for token in COMPANY_TOKENS)
        if len(tail.split()) <= 3 and not is_corporate and not any(char.isdigit() for char in tail):
            location = tail
            value = ", ".join(parts[:-1])
    return value.strip(" .,|-\u2013"), location


def _split_title_company(header: str) -> tuple[str | None, str | None]:
    header = header.strip(" .;|")
    header = re.sub(DATE_RANGE_RE, "", header)
    header = re.sub(r"\(\s*\)", " ", header).strip(" ,|-\u2013")
    parts: list[str] = []
    for separator in (" at ", " @ ", " | ", " \u2013 ", " \u2014 ", " - ", ", "):
        if separator in header:
            parts = [part.strip(" ,|-") for part in header.split(separator) if part.strip(" ,|-")]
            break
    if not parts:
        parts = [header]

    def score_company(text: str) -> int:
        lowered = f" {text.lower()} "
        return sum(2 for token in COMPANY_TOKENS if f" {token} " in lowered or lowered.rstrip().endswith(f" {token}"))

    def score_title(text: str) -> int:
        lowered = text.lower()
        return sum(2 for token in TITLE_TOKENS if token in lowered)

    if len(parts) == 1:
        only = parts[0]
        if score_title(only) > score_company(only):
            return only, None
        return None, only

    best_title, best_company = None, None
    ranked = sorted(parts[:3], key=lambda part: score_title(part) - score_company(part), reverse=True)
    best_title = ranked[0]
    remaining = [part for part in parts[:3] if part != best_title]
    if remaining:
        best_company = sorted(remaining, key=score_company, reverse=True)[0]
    return best_title, best_company


def extract_experiences(section_text: str) -> list[ParsedExperience]:
    experiences: list[ParsedExperience] = []
    for block in _split_blocks(section_text):
        joined = "\n".join(block)
        range_match = DATE_RANGE_RE.search(joined)
        header_line = block[0]

        start_date = end_date = None
        is_current = False
        if range_match:
            start_date = parse_partial_date(range_match.group("start"))
            end_raw = range_match.group("end")
            if re.fullmatch(_PRESENT, end_raw.strip(), re.IGNORECASE):
                is_current = True
            else:
                end_date = parse_partial_date(end_raw, end_of_period=True)

        title, company = _split_title_company(header_line)
        if not company and len(block) > 1:
            _, company = _split_title_company(block[1])
        if not company:
            for entity, _ in nlp.entities(joined[:600], {"ORG"}):
                company = entity
                break
        if not company and not title:
            continue

        location = None
        if company:
            company, location = _clean_company_name(company)
        if not location:
            location_match = re.search(
                r"([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?,\s*(?:[A-Z]{2}|[A-Z][a-zA-Z]+))", joined[:300]
            )
            if location_match:
                location = location_match.group(1)

        description_lines = [line for line in block[1:] if not DATE_RANGE_RE.fullmatch(line.strip())]
        description = clean_text("\n".join(description_lines)) or None

        technologies: list[str] = []
        tech_match = re.search(
            r"(?:technolog(?:y|ies)|tech\s*stack|environment|tools?|skills?\s*used)\s*[:\-]\s*(.+)",
            joined,
            re.IGNORECASE,
        )
        if tech_match:
            technologies = _split_inline_list(tech_match.group(1))

        duration = None
        if start_date:
            duration = _month_diff(start_date, end_date or date.today())

        experiences.append(
            ParsedExperience(
                company_name=(company or "Unknown").strip(" .,|")[:250],
                job_title=(title or None) and title.strip(" .,|")[:250],
                location=location,
                start_date=start_date,
                end_date=end_date,
                is_current=is_current,
                duration_months=duration,
                description=truncate(description or "", 4000) or None,
                technologies=technologies,
            )
        )
    return experiences


# --------------------------------------------------------------------------- education
def _detect_degree(text: str) -> str | None:
    lowered = text.lower()
    for pattern, label in DEGREE_PATTERNS:
        if re.search(pattern, lowered):
            return label
    return None


def extract_educations(section_text: str) -> list[ParsedEducation]:
    educations: list[ParsedEducation] = []
    for block in _split_blocks(section_text) or []:
        joined = " \n".join(block)
        degree = _detect_degree(joined)
        institution = None
        for line in block:
            if not any(token in line.lower() for token in INSTITUTION_TOKENS):
                continue
            cleaned = re.sub(DATE_RANGE_RE, "", line).strip(" ,|-\u2013")
            # "B.Tech, Computer Science, Anna University, 2018" -> keep only the institution part.
            segments = [segment.strip() for segment in cleaned.split(",") if segment.strip()]
            named = [
                segment for segment in segments if any(token in segment.lower() for token in INSTITUTION_TOKENS)
            ]
            institution = (named[0] if named else cleaned)[:250]
            break
        if not institution:
            for entity, _ in nlp.entities(joined[:400], {"ORG"}):
                institution = entity
                break
        years = [int(year) for year in YEAR_RE.findall(joined)]
        if not degree and not institution and not years:
            continue

        field = None
        field_match = re.search(
            r"(?:in|of)\s+([A-Za-z&/ ]{3,60}?)(?:\s*(?:from|at|,|\||\(|\d{4}|$))", joined, re.IGNORECASE
        )
        if field_match and degree:
            candidate = field_match.group(1).strip(" ,.")
            if 2 < len(candidate) <= 60 and not any(token in candidate.lower() for token in INSTITUTION_TOKENS):
                field = title_case(candidate)

        grade = None
        grade_match = re.search(r"(?:cgpa|gpa|percentage|marks|grade)\s*[:\-]?\s*([\d.]+\s*%?(?:/\s*\d+)?)", joined, re.I)
        if grade_match:
            grade = grade_match.group(1).strip()

        educations.append(
            ParsedEducation(
                degree=degree or (block[0].strip()[:200] if block else None),
                field_of_study=field,
                institution=institution,
                start_year=min(years) if len(years) > 1 else None,
                graduation_year=max(years) if years else None,
                grade=grade,
                description=None,
            )
        )
    return educations


# ---------------------------------------------------------------------------- projects
def extract_projects(section_text: str) -> list[ParsedProject]:
    projects: list[ParsedProject] = []
    blocks = [block for block in re.split(r"\n(?=\S)", section_text) if block.strip()]
    for block in blocks:
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        name_line = lines[0].strip(" .:-\u2013|")
        name = re.sub(DATE_RANGE_RE, "", name_line).strip(" .:-\u2013|")
        if not name or len(name) > 160:
            name = truncate(name or "Project", 120)

        technologies: list[str] = []
        tech_match = re.search(
            r"(?:technolog(?:y|ies)|tech\s*stack|tools?|stack|built\s+with|environment)\s*[:\-]\s*(.+)",
            block,
            re.IGNORECASE,
        )
        if tech_match:
            technologies = _split_inline_list(tech_match.group(1))

        role = None
        role_match = re.search(r"(?:role|position)\s*[:\-]\s*(.+)", block, re.IGNORECASE)
        if role_match:
            role = role_match.group(1).strip()[:120]

        url_match = URL_RE.search(block)
        description = clean_text("\n".join(lines[1:])) or None
        projects.append(
            ParsedProject(
                name=name,
                role=role,
                description=truncate(description or "", 2500) or None,
                technologies=technologies,
                url=url_match.group(0) if url_match else None,
            )
        )
    return projects


# ---------------------------------------------------------------------- certifications
def extract_certifications(section_text: str, full_text: str) -> list[ParsedCertification]:
    found: dict[str, ParsedCertification] = {}

    def add(raw: str) -> None:
        name = raw.strip(" .,;:-\u2013|\u2022")
        year_match = YEAR_RE.search(name)
        # Trailing years ("... - Associate, 2024") belong on issue_date, not in the name.
        name = re.sub(r"[\s,;|\u2013-]*\(?\b(?:19|20)\d{2}\)?\s*$", "", name).strip(" .,;:-\u2013|")
        if not (4 <= len(name) <= 160):
            return
        if not CERT_HINT_RE.search(name) and section_text == "":
            return
        key = normalize_key(name)
        if key in found:
            return
        issuer = None
        issuer_match = re.search(r"(?:by|from|issued\s+by|-)\s+([A-Z][\w&.\- ]{2,60})$", name)
        if issuer_match and issuer_match.group(1).strip().lower() not in CERT_LEVELS:
            issuer = issuer_match.group(1).strip()
        for vendor in ("AWS", "Amazon Web Services", "Microsoft", "Google", "Oracle", "Cisco", "PMI", "Scrum Alliance",
                       "CompTIA", "Salesforce", "Databricks", "Snowflake", "Red Hat", "Linux Foundation", "Azure"):
            if vendor.lower() in name.lower():
                issuer = issuer or vendor
                break
        issue_date = date(int(year_match.group(0)), 1, 1) if year_match else None
        credential_match = re.search(r"(?:credential(?:\s+id)?|id)\s*[:\-]?\s*([\w-]{4,})", name, re.IGNORECASE)
        found[key] = ParsedCertification(
            name=re.sub(r"\s*\(\d{4}\)\s*", " ", name).strip(),
            issuer=issuer,
            credential_id=credential_match.group(1) if credential_match else None,
            issue_date=issue_date,
        )

    for line in section_text.split("\n"):
        for part in re.split(r"\s{2,}|\s*\|\s*|;", line):
            if part.strip():
                add(part)

    # Certifications are often mentioned outside a dedicated section.
    for line in full_text.split("\n"):
        if CERT_HINT_RE.search(line) and re.search(r"certifi", line, re.IGNORECASE):
            add(line)

    return list(found.values())[:40]


# --------------------------------------------------------------------------- languages
def extract_languages(section_text: str, full_text: str) -> list[str]:
    languages: list[str] = []
    source = section_text or ""
    for token in re.split(r"[,;|/\n]", source):
        candidate = re.sub(r"\((.*?)\)", "", token).strip(" .:-\u2022")
        candidate = re.sub(r"\b(native|fluent|professional|basic|beginner|intermediate|advanced|proficiency|proficient|read|write|speak|mother tongue)\b", "", candidate, flags=re.I)
        candidate = candidate.strip(" .:-\u2022")
        if candidate.lower() in KNOWN_LANGUAGES:
            languages.append(title_case(candidate))
    if not languages:
        lowered = full_text.lower()
        for language in KNOWN_LANGUAGES:
            if re.search(rf"\b{re.escape(language)}\b", lowered) and language != "english":
                continue
        if re.search(r"\benglish\b", lowered):
            languages.append("English")
    return list(dict.fromkeys(languages))


# ------------------------------------------------------------------------ skill phrases
def _split_inline_list(value: str) -> list[str]:
    parts = re.split(r"[,;|/\u2022\u00b7]|\s{3,}|\s+and\s+", value)
    cleaned: list[str] = []
    for part in parts:
        item = part.strip(" .:-\u2013()[]")
        if not item or len(item) > 60:
            continue
        if item.lower() in {"etc", "etc.", "others", "and"}:
            continue
        cleaned.append(item)
    return list(dict.fromkeys(cleaned))


def extract_skill_mentions(sections: dict[str, str], full_text: str) -> list[SkillMention]:
    """Collect explicit skill phrases from skills/tech lines with their provenance."""
    mentions: dict[str, SkillMention] = {}

    def add(raw: str, source: str, evidence: str, confidence: float, years: float | None = None) -> None:
        raw = raw.strip(" .:-\u2013|")
        if not raw or len(raw) < 2 or len(raw) > 60:
            return
        if raw.lower() in {"skills", "technologies", "tools", "other", "others", "languages"}:
            return
        key = normalize_key(raw)
        if not key:
            return
        existing = mentions.get(key)
        if existing:
            existing.mention_count += 1
            existing.confidence = max(existing.confidence, confidence)
            if years and not existing.years_experience:
                existing.years_experience = years
            return
        mentions[key] = SkillMention(
            raw_text=raw,
            source=source,
            evidence=truncate(evidence, 300),
            confidence=confidence,
            years_experience=years,
        )

    skills_section = sections.get("skills", "")
    for line in skills_section.split("\n"):
        if not line.strip():
            continue
        payload = line.split(":", 1)[1] if ":" in line and len(line.split(":", 1)[0]) < 45 else line
        for item in _split_inline_list(payload):
            years = None
            years_match = SKILL_YEARS_RE.match(item)
            name = item
            if years_match:
                name = years_match.group("name").strip()
                years = float(years_match.group("years"))
            add(name, SkillSource.RESUME_SKILLS_SECTION.value, line, 0.95, years)

    for key, source in (
        ("experience", SkillSource.RESUME_EXPERIENCE.value),
        ("projects", SkillSource.RESUME_PROJECT.value),
    ):
        section = sections.get(key, "")
        for match in re.finditer(
            r"(?:technolog(?:y|ies)|tech\s*stack|tools?|stack|environment|skills?\s*used|built\s+with)\s*[:\-]\s*(.+)",
            section,
            re.IGNORECASE,
        ):
            for item in _split_inline_list(match.group(1)):
                add(item, source, match.group(0), 0.85)

    # "5+ years of Python" style statements give per-skill experience hints.
    for match in re.finditer(
        r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:hands[\s-]?on\s+)?(?:experience\s+)?(?:in|with|on|using)?\s+([A-Za-z0-9+#.\s]{2,40})",
        full_text,
        re.IGNORECASE,
    ):
        for item in _split_inline_list(match.group(2)):
            add(item, SkillSource.RESUME_EXPERIENCE.value, match.group(0), 0.8, float(match.group(1)))

    return list(mentions.values())


# ------------------------------------------------------------------- total experience
def estimate_total_experience(text: str, experiences: Iterable[ParsedExperience]) -> float:
    explicit: list[float] = []
    for match in TOTAL_EXPERIENCE_RE.finditer(text[:4000]):
        try:
            value = float(match.group(1))
        except (TypeError, ValueError):
            continue
        if 0 < value <= 45:
            explicit.append(value)

    ranges: list[tuple[date, date]] = []
    for experience in experiences:
        if experience.start_date:
            ranges.append((experience.start_date, experience.end_date or date.today()))
    computed = _merge_ranges(ranges)

    if explicit and computed:
        # Trust the resume statement unless it wildly disagrees with the timeline.
        stated = max(explicit)
        return stated if abs(stated - computed) <= max(2.0, computed * 0.5) else computed
    if explicit:
        return max(explicit)
    return computed


# ----------------------------------------------------------------------------- driver
def parse_resume_text(text: str) -> ParsedResume:
    """Run the full rule-based extraction pipeline over cleaned resume text."""
    text = clean_text(text)
    sections = segment_sections(text)
    warnings: list[str] = []

    personal = extract_personal(text, sections)
    experiences = extract_experiences(sections.get("experience", ""))
    educations = extract_educations(sections.get("education", ""))
    projects = extract_projects(sections.get("projects", ""))
    certifications = extract_certifications(sections.get("certifications", ""), text)
    languages = extract_languages(sections.get("languages", ""), text)
    skill_mentions = extract_skill_mentions(sections, text)

    if not sections.get("skills"):
        warnings.append("No dedicated skills section found - skills inferred from the full text.")
    if not experiences:
        warnings.append("No work experience entries could be segmented.")

    total_experience = estimate_total_experience(text, experiences)
    current = next((exp for exp in experiences if exp.is_current), experiences[0] if experiences else None)
    highest_degree = None
    degrees = [education.degree for education in educations if education.degree]
    if degrees:
        highest_degree = max(
            (degree for degree in degrees),
            key=lambda degree: DEGREE_RANK.get(_detect_degree(degree) or "", 0),
        )
        highest_degree = _detect_degree(highest_degree) or highest_degree

    summary_section = sections.get("summary") or ""
    summary = truncate(summary_section, 1200) or None

    return ParsedResume(
        personal=personal,
        summary=summary,
        total_experience_years=total_experience,
        current_title=(current.job_title if current else None) or personal.headline,
        current_company=current.company_name if current else None,
        highest_degree=highest_degree,
        experiences=experiences,
        educations=educations,
        projects=projects,
        certifications=certifications,
        languages=languages,
        skill_mentions=skill_mentions,
        sections={name: truncate(value, 6000) for name, value in sections.items()},
        warnings=warnings,
        extraction_backend="spacy+rules" if nlp.is_available() else "rules",
    )
