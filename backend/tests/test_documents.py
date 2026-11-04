"""The document renderer, checked by opening the files it writes."""

from io import BytesIO

from docx import Document

from job_copilot.applications import Claim, CoverLetter, EvidenceRef, Resume, Role
from job_copilot.documents import cover_letter_docx, filename, resume_docx

SOURCE = [EvidenceRef(text="Resume line the Claim came from", origin="self_reported")]


def claim(text: str) -> Claim:
    return Claim(text=text, evidence=SOURCE)


def opened(content: bytes) -> list[str]:
    return [p.text for p in Document(BytesIO(content)).paragraphs]


def test_the_resume_is_one_column_ordered_skills_experience_education() -> None:
    resume = Resume(
        skills=[claim("Python"), claim("FastAPI")],
        experience=[
            Role(heading=claim("Python Developer, Example Co"), lines=[claim("Shipped systems")])
        ],
        education=[claim("BSc Computer Science")],
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
