"""The ATS parsing check, against files built to read well and files built to break it."""

import zipfile
from io import BytesIO

from docx import Document

from job_copilot.ats import problems

LINES = ["Sam Rivera", "sam@example.com", "Python", "Python Developer, Example Co, 2021 to 2024"]


def docx(*paragraphs: str, table: bool = False, header: str = "") -> bytes:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    if table:
        document.add_table(rows=1, cols=1).cell(0, 0).text = "Kept in a table"
    if header:
        document.sections[0].header.paragraphs[0].text = header
    out = BytesIO()
    document.save(out)
    return out.getvalue()


def test_a_file_that_reads_in_order_passes() -> None:
    content = docx(
        "Sam Rivera",
        "sam@example.com",
        "Skills",
        "Python",
        "Python Developer, Example Co\t2021 to 2024",
    )

    assert problems(content, LINES) == []


def test_a_missing_or_reordered_line_is_refused() -> None:
    missing = docx("Sam Rivera", "sam@example.com", "Python")
    reordered = docx(
        "sam@example.com", "Sam Rivera", "Python", "Python Developer, Example Co 2021 to 2024"
    )

    assert problems(missing, LINES) == [
        "“Python Developer, Example Co, 2021 to 2024” doesn't read back"
    ]
    assert problems(reordered, LINES) == ["“sam@example.com” doesn't read back"]


def test_tables_and_headers_are_refused_even_when_the_text_reads() -> None:
    content = docx(*LINES, table=True, header="Sam Rivera")

    assert problems(content, LINES) == [
        "It has a table, which an ATS may skip or scramble",
        "It has text in a header or footer, which an ATS may skip",
    ]


def test_a_text_box_is_refused() -> None:
    source = docx("Sam Rivera")
    out = BytesIO()
    with zipfile.ZipFile(BytesIO(source)) as original, zipfile.ZipFile(out, "w") as changed:
        for item in original.infolist():
            data = original.read(item)
            if item.filename == "word/document.xml":
                # A text box, as Word writes it inside a drawing.
                data = data.replace(
                    b"<w:t>Sam Rivera</w:t>",
                    b"<w:t>Sam Rivera</w:t><w:txbxContent><w:p><w:r><w:t>Boxed</w:t></w:r>"
                    b"</w:p></w:txbxContent>",
                )
            changed.writestr(item, data)

    assert "It has a text box, which an ATS may skip" in problems(out.getvalue(), ["Sam Rivera"])
