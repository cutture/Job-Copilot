"""The person's photo for the styled resume: found in their resume or uploaded, then checked.

It is never sent to a model. Only one is kept, re-encoded so nothing but the picture remains:
no metadata such as where it was taken, and nothing hidden in the file.
"""

import io
import zipfile

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

MAX_PHOTO_BYTES = 5_000_000
# Decoding a huge image can exhaust memory, so one with more pixels is refused before decoding.
MAX_PHOTO_PIXELS = 40_000_000
# Small and round in the file, so a small square is enough.
PHOTO_SIDE = 400
# Icons and logos in a resume are smaller than this; a photo isn't.
MIN_PHOTO_SIDE = 64
# A photo is roughly square or portrait; a wide banner or logo isn't.
PHOTO_SHAPES = (0.6, 1.6)
NOT_AN_IMAGE = "This file isn't an image we can use. Upload a JPEG or PNG photo."


def checked_photo(content: bytes) -> bytes:
    """The photo as a small square JPEG, or ValueError if it isn't a usable image."""
    try:
        with Image.open(io.BytesIO(content)) as opened:
            if opened.format not in ("JPEG", "PNG"):
                raise ValueError(NOT_AN_IMAGE)
            if opened.width * opened.height > MAX_PHOTO_PIXELS:
                raise ValueError(NOT_AN_IMAGE)
            opened.verify()
        # verify() leaves the image unusable, so it's opened again to decode it.
        with Image.open(io.BytesIO(content)) as opened:
            picture = opened.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
        raise ValueError(NOT_AN_IMAGE) from None
    side = min(picture.size)
    left, top = (picture.width - side) // 2, (picture.height - side) // 2
    square = picture.crop((left, top, left + side, top + side))
    square.thumbnail((PHOTO_SIDE, PHOTO_SIDE))
    out = io.BytesIO()
    # Saved from the decoded pixels alone, so no metadata carries over.
    square.save(out, "JPEG", quality=88)
    return out.getvalue()


def _looks_like_a_photo(size: tuple[int, int]) -> bool:
    width, height = size
    low, high = PHOTO_SHAPES
    return (
        min(size) >= MIN_PHOTO_SIDE
        and width * height <= MAX_PHOTO_PIXELS
        and low <= width / height <= high
    )


def photo_in_resume(content: bytes) -> bytes | None:
    """The picture in a DOCX or PDF resume most likely to be the person's photo, as PNG.

    ponytail: the biggest square-ish picture wins, so a large square logo can beat a small
    headshot; the person can upload the right photo instead.
    """
    found: list[Image.Image] = []
    try:
        if content.startswith(b"%PDF-"):
            # pypdf decodes each picture with its colours and encoding applied, under its own cap
            # on how much a stream may decompress to. A resume's photo is on its first page.
            for picture in PdfReader(io.BytesIO(content)).pages[0].images:
                if picture.image is not None and _looks_like_a_photo(picture.image.size):
                    found.append(picture.image)
        else:
            # read_resume has already checked how far the file unpacks.
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                for item in archive.infolist():
                    if not item.filename.startswith("word/media/") or (
                        item.file_size > MAX_PHOTO_BYTES
                    ):
                        continue
                    try:
                        with Image.open(io.BytesIO(archive.read(item))) as opened:
                            if _looks_like_a_photo(opened.size):
                                found.append(opened.convert("RGB"))
                    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
                        continue  # A drawing or icon format that isn't a photo.
    except Exception:
        # A resume whose pictures can't be read still uploads; it just gives no photo.
        return None
    if not found:
        return None
    best = max(found, key=lambda picture: picture.width * picture.height)
    out = io.BytesIO()
    best.convert("RGB").save(out, "PNG")
    return out.getvalue()
