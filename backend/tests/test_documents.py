"""The document renderer, checked by opening the files it writes."""

from io import BytesIO

from docx import Document

from job_copilot.applications import Claim, CoverLetter, EvidenceRef, Resume, Role, Section
from job_copilot.documents import cover_letter_docx, filename, resume_docx

SOURCE = [EvidenceRef(text="Resume line the Claim came from", origin="self_reported")]


def claim(text: str) -> Claim:
    return Claim(text=text, evidence=SOURCE)


def opened(content: bytes) -> list[str]:
    return [p.text for p in Document(BytesIO(content)).paragraphs]


def test_the_resume_is_one_column_ordered_skills_experience_education() -> None:
    resume = Resume(
        sections=[
            Section(kind="skills", heading="Skills", claims=[claim("Python"), claim("FastAPI")]),
            Section(
                kind="experience",
                heading="Experience",
                roles=[
                    Role(
                        heading=claim("Python Developer, Example Co"),
                        lines=[claim("Shipped systems")],
                    )
                ],
            ),
            Section(kind="education", heading="Education", claims=[claim("BSc Computer Science")]),
        ]
    )

    content = resume_docx(resume, "Sam Rivera", "sam@example.com")
    document = Document(BytesIO(content))

    assert opened(content) == [
        "Sam Rivera",
        "sam@example.com",
        "Skills",
        "Python, FastAPI",
        "Experience",
        "Python Developer, Example Co",
        "Shipped systems",
        "Education",
        "BSc Computer Science",
    ]
    assert not document.tables and not document.inline_shapes
    assert len(document.sections) == 1
    assert document.core_properties.created.year >= 2026
    # Evidence and its labels are for the app only.
    assert "Resume line the Claim came from" not in str(opened(content))
    assert document.core_properties.author == "Sam Rivera"


def test_sections_render_in_the_packs_order_with_their_own_headings() -> None:
    resume = Resume(
        sections=[
            Section(kind="education", heading="Education", claims=[claim("BSc Computer Science")]),
            Section(kind="skills", heading="Core Skills", claims=[claim("Python")]),
        ]
    )

    assert opened(resume_docx(resume, None, None)) == [
        "Education",
        "BSc Computer Science",
        "Core Skills",
        "Python",
    ]


def test_a_resume_saved_before_sections_reads_as_sections_and_drops_empty_ones() -> None:
    fixed = {"skills": [claim("Python").model_dump()], "experience": [], "education": []}

    resume = Resume.model_validate(fixed)

    assert [(s.kind, s.heading) for s in resume.sections] == [("skills", "Skills")]
    assert resume.sections[0].claims[0].text == "Python"


def test_the_cover_letter_is_its_paragraphs_signed_with_the_name() -> None:
    letter = CoverLetter(paragraphs=[[claim("Dear team,")], [claim("I build."), claim("Thanks.")]])

    assert opened(cover_letter_docx(letter, "Sam Rivera", None)) == [
        "Sam Rivera",
        "Dear team,",
        "I build. Thanks.",
        "Sam Rivera",
    ]


def test_files_are_named_name_role_employer() -> None:
    assert (
        filename("Sam Rivera", "Senior GenAI Engineer", "Northwind Labs", "Resume")
        == "Sam-Rivera-Senior-GenAI-Engineer-Northwind-Labs-Resume.docx"
    )
    assert filename(None, "AI/ML Engineer (Remote)", None, "Cover letter") == (
        "AI-ML-Engineer-Remote-Cover-letter.docx"
    )
    assert filename("José Núñez", "../../etc", None, "Resume") == "José-Núñez-etc-Resume.docx"
    # A title that already names the employer doesn't name it twice.
    assert filename("Sam", "ML Engineer, Northwind Labs", "Northwind Labs", "Resume") == (
        "Sam-ML-Engineer-Northwind-Labs-Resume.docx"
    )
