"""The person's photo for the styled resume: found in their resume or uploaded, then checked.

It is never sent to a model. Only one is kept, re-encoded so nothing but the picture remains:
no metadata such as where it was taken, and nothing hidden in the file.
"""

import io
import zipfile

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

MAX_PHOTO_BYTES = 5_000_000
# Decoding a huge image can exhaust memory, so anything bigger is refused before it's decoded.
MAX_PHOTO_PIXELS = 40_000_000
# Small and round in the file, so a small square is enough.
PHOTO_SIDE = 400
# Icons and logos in a resume are smaller than this; a photo isn't.
MIN_PHOTO_SIDE = 64
NOT_AN_IMAGE = "This file isn't an image we can use. Upload a JPEG or PNG photo."
Image.MAX_IMAGE_PIXELS = MAX_PHOTO_PIXELS


def checked_photo(content: bytes) -> bytes:
    """The photo as a small square JPEG, or ValueError if it isn't a usable image."""
    try:
        with Image.open(io.BytesIO(content)) as opened:
            if opened.format not in ("JPEG", "PNG"):
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


def photo_in_resume(filename: str, content: bytes) -> bytes | None:
    """The largest picture in a DOCX or PDF resume that's big enough to be a photo, if any."""
    found: list[bytes] = []
    try:
        if filename.lower().endswith(".docx"):
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                found = [
                    archive.read(item)
                    for item in archive.infolist()
                    if item.filename.startswith("word/media/") and item.file_size <= MAX_PHOTO_BYTES
                ]
        else:
            page = PdfReader(io.BytesIO(content)).pages[0]
            found = [
                picture.data for picture in page.images if len(picture.data) <= MAX_PHOTO_BYTES
            ]
    except Exception:
        # A resume whose pictures can't be read still uploads; it just gives no photo.
        return None

    def side(data: bytes) -> int:
        try:
            with Image.open(io.BytesIO(data)) as opened:
                return min(opened.size)
        except Exception:
            return 0

    photos = [data for data in found if side(data) >= MIN_PHOTO_SIDE]
    return max(photos, key=len) if photos else None
