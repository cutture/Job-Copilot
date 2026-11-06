"""The ATS parsing check: read a DOCX the way an applicant tracking system does.

An ATS reads the body text in order and often drops tables, text boxes, headers and footers. A
file passes when it has none of those and every expected line comes back intact and in order.
Lines are compared as words, so punctuation and a tab before right-aligned dates don't count.
"""

import re
import zipfile
from io import BytesIO

WORD = re.compile(r"\w+")
SKIPPED = {
    "<w:tbl>": "It has a table, which an ATS may skip or scramble",
    "<w:txbxContent>": "It has a text box, which an ATS may skip",
}
HEADER_FOOTER = "It has text in a header or footer, which an ATS may skip"


def _words(text: str) -> list[str]:
    return [word.casefold() for word in WORD.findall(text)]


def _body_words(document_xml: str) -> list[str]:
    paragraphs = re.findall(r"<w:p[ >].*?</w:p>", document_xml, re.DOTALL)
    # A tab, as before right-aligned dates, reads as a space.
    spaced = (p.replace("<w:tab/>", "<w:t> </w:t>") for p in paragraphs)
    texts = ("".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", p)) for p in spaced)
    return [word for text in texts for word in _words(_unescape(text))]


def _unescape(text: str) -> str:
    return (
        text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&")
    )


def problems(content: bytes, lines: list[str]) -> list[str]:
    """Why an ATS would misread the file, or nothing when it reads cleanly."""
    with zipfile.ZipFile(BytesIO(content)) as archive:
        body = archive.read("word/document.xml").decode("utf-8")
        edges = [
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if re.match(r"word/(header|footer)\d*\.xml$", name)
        ]
    found = [message for tag, message in SKIPPED.items() if tag in body]
    if any(re.search(r"<w:t(?: [^>]*)?>[^<]*\w", xml) for xml in edges):
        found.append(HEADER_FOOTER)
    words, position = _body_words(body), 0
    for line in lines:
        wanted = _words(line)
        at = next(
            (
                i
                for i in range(position, len(words) - len(wanted) + 1)
                if words[i : i + len(wanted)] == wanted
            ),
            None,
        )
        if at is None:
            found.append(f"“{line}” doesn't read back")
            continue
        position = at + len(wanted)
    return found
