"""The ATS parsing check: read a DOCX or PDF the way an applicant tracking system does.

An ATS reads the body text in order and often drops tables, text boxes, headers and footers. A
DOCX passes when it has none of those and every expected line comes back intact, in order and
within one paragraph. A PDF passes when its extracted text gives back every expected line, in
order. Lines are compared as words, so punctuation, and the tab or line break before
right-aligned dates or where a line wraps, don't count.
"""

import html
import re
import zipfile
from io import BytesIO

from pypdf import PdfReader

WORD = re.compile(r"\w+")
# ponytail: a PDF is read with pypdf, whose two readings stand in for an ATS's; a line needn't
# stay in one paragraph, as a PDF has none. Check with pdftotext too if an ATS ever misreads one.
# ponytail: the file is read with patterns, not an XML parser, and hidden text, footnotes and
# frames aren't checked; the renderer writes none of them. Parse with xml.etree if files from
# elsewhere are ever checked.
SKIPPED = {
    r"<w:tbl[ >]": "It has a table, which an ATS may skip or scramble",
    r"<w:txbxContent[ >]": "It has a text box, which an ATS may skip",
}
HEADER_FOOTER = "It has text in a header or footer, which an ATS may skip"
TEXT = re.compile(r"<w:t(?: [^>]*)?>([^<]*)</w:t>")
# A tab or line break reads as a space between the words on either side.
SPACES = re.compile(r"<w:(?:tab|br|cr)(?: [^>]*)?/>")


def _words(text: str) -> list[str]:
    return [word.casefold() for word in WORD.findall(text)]


def _paragraphs(document_xml: str) -> list[list[str]]:
    """Each body paragraph's words, in reading order."""
    paragraphs = re.findall(r"<w:p[ >].*?</w:p>", document_xml, re.DOTALL)
    spaced = (SPACES.sub("<w:t> </w:t>", p) for p in paragraphs)
    return [_words(html.unescape("".join(TEXT.findall(p)))) for p in spaced]


def _find(words: list[str], wanted: list[str], start: int) -> int | None:
    last = len(words) - len(wanted)
    return next((i for i in range(start, last + 1) if words[i : i + len(wanted)] == wanted), None)


def problems(content: bytes, lines: list[str]) -> list[str]:
    """Why an ATS would misread the file, or nothing when it reads cleanly."""
    with zipfile.ZipFile(BytesIO(content)) as archive:
        body = archive.read("word/document.xml").decode("utf-8")
        headers_and_footers = [
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if re.match(r"word/(header|footer)\d*\.xml$", name)
        ]
    found = [message for pattern, message in SKIPPED.items() if re.search(pattern, body)]
    if any(re.search(r"<w:t(?: [^>]*)?>[^<]*\w", xml) for xml in headers_and_footers):
        found.append(HEADER_FOOTER)
    paragraphs = _paragraphs(body)
    # Where reading has got to: a paragraph, and a word within it.
    at_paragraph, at_word = 0, 0
    for line in lines:
        wanted = _words(line)
        for index in range(at_paragraph, len(paragraphs)):
            start = at_word if index == at_paragraph else 0
            match = _find(paragraphs[index], wanted, start)
            if match is not None:
                at_paragraph, at_word = index, match + len(wanted)
                break
        else:
            found.append(f"“{line}” doesn't read back")
    return found


def pdf_problems(content: bytes, lines: list[str]) -> list[str]:
    """Why an ATS would misread the PDF, or nothing when its text reads back cleanly.

    It's read twice, in the order the text was drawn and by its position on the page, as ATS
    tools do one or the other; every line must read back in order both ways.
    """
    pages = PdfReader(BytesIO(content)).pages
    found: list[str] = []
    for mode in ("plain", "layout"):
        words = _words(" ".join(page.extract_text(extraction_mode=mode) for page in pages))
        at = 0
        for line in lines:
            wanted = _words(line)
            match = _find(words, wanted, at)
            if match is None:
                problem = f"“{line}” doesn't read back"
                if problem not in found:
                    found.append(problem)
            else:
                at = match + len(wanted)
    return found
