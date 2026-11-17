"""The PDF renderer: the same two pairs as the DOCX files, drawn from the same saved documents.

Like the DOCX renderer it takes only verified Claims, and writes only their text, the name and
contact line, and on the styled resume the round photo: no Evidence, labels or Removed Claims.
Text is drawn in reading order, so an ATS reads it back as the DOCX reads; the styled resume's
two Skills columns fill across each row for the same reason. Every file passes the ATS check
before it can be downloaded.
"""

from io import BytesIO
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image, ImageDraw

from job_copilot.applications import Claim, CoverLetter, Resume
from job_copilot.documents import ACCENTS, paragraph_text, split_dates, summary_text
from job_copilot.profile import AccentColour

FONTS = Path(__file__).parent / "fonts"
# Carlito is metric-compatible with Calibri, which the DOCX files use, under the SIL OFL.
FONT = "Carlito"
DARK = (0x33, 0x33, 0x33)
# Letter size, in points, as the DOCX files use.
PAGE = "Letter"
PHOTO_SIZE = 54  # Three quarters of an inch, as on the styled DOCX resume.
PHOTO_GAP = 8
BULLET = "•"


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return (int(hex_colour[:2], 16), int(hex_colour[2:4], 16), int(hex_colour[4:], 16))


class _Page(FPDF):
    def __init__(self, name: str | None, title: str, margins: tuple[float, float]) -> None:
        super().__init__(unit="pt", format=PAGE)
        self.add_font(FONT, "", FONTS / "Carlito-Regular.ttf")
        self.add_font(FONT, "B", FONTS / "Carlito-Bold.ttf")
        side, top = margins
        self.set_margins(side, top, side)
        self.set_auto_page_break(True, top)
        # Only the person and the document: nothing about the app or the library.
        self.set_author(name or "")
        self.set_title(title)
        self.set_creator("")
        self.set_producer("")
        self.add_page()
        self.set_text_color(*DARK)

    def para(self, text: str, size: float, bold: bool = False, after: float = 2) -> None:
        """A paragraph of text, wrapped to the page."""
        self.set_font(FONT, "B" if bold else "", size)
        self.multi_cell(0, size * 1.25, text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(after)

    def bullet(self, text: str, size: float, indent: float = 14) -> None:
        self.set_font(FONT, "", size)
        self.cell(indent, size * 1.25, BULLET)
        self.multi_cell(0, size * 1.25, text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def content(self) -> bytes:
        return bytes(self.output())


# --- The plain pair ----------------------------------------------------------------------

PLAIN_MARGINS = (72.0, 72.0)


def _plain_header(page: _Page, name: str | None, contact: str | None) -> None:
    if name:
        page.para(name, 11, bold=True)
    if contact:
        page.para(contact, 11, after=6)


def resume_pdf(resume: Resume, name: str | None, contact: str | None) -> bytes:
    page = _Page(name, "Resume", PLAIN_MARGINS)
    _plain_header(page, name, contact)
    for section in resume.sections:
        page.ln(4)
        page.para(section.heading, 13, bold=True)
        if section.kind == "summary":
            page.para(summary_text(section), 11)
        elif section.kind == "skills":
            if section.claims:
                page.para(", ".join(skill.text for skill in section.claims), 11)
            for group in section.groups:
                page.para(f"{group.heading.text}: " + ", ".join(s.text for s in group.claims), 11)
        else:
            for claim in section.claims:
                page.para(claim.text, 11)
        for role in section.roles:
            page.para(role.heading.text, 11, bold=True)
            for line in role.lines:
                page.bullet(line.text, 11)
    return page.content()


def cover_letter_pdf(letter: CoverLetter, name: str | None, contact: str | None) -> bytes:
    page = _Page(name, "Cover letter", PLAIN_MARGINS)
    _plain_header(page, name, contact)
    for paragraph in letter.paragraphs:
        page.para(paragraph_text(paragraph), 11, after=8)
    if name:
        page.para(name, 11)
    return page.content()


# --- The styled pair ---------------------------------------------------------------------

STYLED_MARGINS = (54.0, 43.2)


def round_photo(photo: bytes) -> bytes:
    """The photo cropped to a centred circle, as a PNG with the corners left clear."""
    with Image.open(BytesIO(photo)) as image:
        square = min(image.size)
        left, top = (image.width - square) // 2, (image.height - square) // 2
        cropped = image.convert("RGBA").crop((left, top, left + square, top + square))
    mask = Image.new("L", cropped.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, square - 1, square - 1), fill=255)
    cropped.putalpha(mask)
    out = BytesIO()
    cropped.save(out, "PNG")
    return out.getvalue()


def _styled_header(
    page: _Page,
    name: str | None,
    contact: str | None,
    accent: AccentColour,
    photo: bytes | None = None,
) -> None:
    colour = _rgb(ACCENTS[accent][0])
    first, _, surname = (name or "").rpartition(" ")
    page.set_font(FONT, "B", 24)
    width = page.get_string_width(f"{first} " if first else "") + page.get_string_width(surname)
    # The round photo sits beside the name, the pair centred together, as on the DOCX.
    beside = PHOTO_SIZE + PHOTO_GAP if photo else 0
    x = (page.w - beside - width) / 2
    top = page.get_y()
    line = max(30.0, PHOTO_SIZE if photo else 0)
    if photo:
        page.image(BytesIO(round_photo(photo)), x=x, y=top, w=PHOTO_SIZE, h=PHOTO_SIZE)
    if name:
        page.set_xy(x + beside, top + (line - 30) / 2)
        if first:
            page.cell(page.get_string_width(f"{first} "), 30, f"{first} ")
        page.set_text_color(*colour)
        page.cell(page.get_string_width(surname), 30, surname)
        page.set_text_color(*DARK)
    if name or photo:
        page.set_y(top + line + 2)
    if contact:
        page.set_font(FONT, "", 10)
        page.multi_cell(0, 13, contact, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        _rule(page, colour)
    page.ln(4)


def _rule(page: _Page, colour: tuple[int, int, int]) -> None:
    page.set_draw_color(*colour)
    page.set_line_width(0.75)
    y = page.get_y() + 1
    page.line(page.l_margin, y, page.w - page.r_margin, y)
    page.set_y(y + 2)


def _heading(page: _Page, text: str, accent: AccentColour) -> None:
    colour, band = ACCENTS[accent]
    page.ln(8)
    page.set_font(FONT, "B", 11)
    page.set_fill_color(*_rgb(band))
    page.set_text_color(*_rgb(colour))
    page.cell(0, 16, text.upper(), align="C", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    page.set_text_color(*DARK)
    _rule(page, _rgb(colour))
    page.ln(2)


def _skill_columns(page: _Page, skills: list[Claim]) -> None:
    """Skills in two columns, filled across each row so they read in order."""
    half = (page.w - page.l_margin - page.r_margin) / 2
    page.set_font(FONT, "", 10.5)
    for start in range(0, len(skills), 2):
        top = page.get_y()
        bottoms = []
        for column, skill in enumerate(skills[start : start + 2]):
            page.set_xy(page.l_margin + column * half, top)
            page.cell(14, 13, BULLET)
            page.multi_cell(
                half - 18, 13, skill.text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT
            )
            bottoms.append(page.get_y())
        page.set_y(max(bottoms) + 1)


def styled_resume_pdf(
    resume: Resume,
    name: str | None,
    contact: str | None,
    accent: AccentColour,
    photo: bytes | None = None,
) -> bytes:
    page = _Page(name, "Resume", STYLED_MARGINS)
    _styled_header(page, name, contact, accent, photo)
    for section in resume.sections:
        _heading(page, section.heading, accent)
        if section.kind == "summary":
            page.para(summary_text(section), 10.5)
        elif section.kind == "skills":
            if section.claims:
                _skill_columns(page, section.claims)
            for group in section.groups:
                page.para(group.heading.text, 10.5, bold=True, after=1)
                _skill_columns(page, group.claims)
        else:
            for claim in section.claims:
                page.para(claim.text, 10.5)
        for role in section.roles:
            title, dates = split_dates(role.heading.text)
            page.ln(4)
            page.set_font(FONT, "B", 10.5)
            if dates:
                # The dates at the right margin, on the title's line, after it in reading order.
                top = page.get_y()
                page.set_font(FONT, "", 10)
                room = page.get_string_width(dates) + 6
                page.set_font(FONT, "B", 10.5)
                page.multi_cell(
                    page.w - page.l_margin - page.r_margin - room,
                    13,
                    f"{title} ",
                    align="L",
                    new_x=XPos.LMARGIN,
                    new_y=YPos.NEXT,
                )
                below = page.get_y()
                page.set_xy(page.w - page.r_margin - room, top)
                page.set_font(FONT, "", 10)
                page.cell(room, 13, dates, align="R")
                page.set_y(below)
            else:
                page.para(title, 10.5, bold=True, after=0)
            for bullet in role.lines:
                page.bullet(bullet.text, 10.5)
    return page.content()


def styled_cover_letter_pdf(
    letter: CoverLetter, name: str | None, contact: str | None, accent: AccentColour
) -> bytes:
    page = _Page(name, "Cover letter", STYLED_MARGINS)
    _styled_header(page, name, contact, accent)
    page.ln(8)
    for paragraph in letter.paragraphs:
        page.para(paragraph_text(paragraph), 10.5, after=8)
    if name:
        page.para(name, 10.5)
    return page.content()
