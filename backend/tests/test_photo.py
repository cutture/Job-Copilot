"""A photo on the styled resume: off by default, one checked image, never sent to a model."""

import base64
import json
import warnings
import zipfile
from io import BytesIO
from typing import Any

import psycopg
from docx import Document
from fastapi.testclient import TestClient
from PIL import Image

from job_copilot import worker
from job_copilot.photo import photo_in_resume
from tests.conftest import TEST_DB, FakeProvider
from tests.test_application_pack import apply, rated_match, run_worker
from tests.test_my_sections import ready_pack, write_sections
from tests.test_profile import make_docx, upload

# Text an uploaded photo carries in its metadata, which must never be kept.
HIDDEN = "Taken at 1 Example Street"


def image(kind: str = "PNG", size: tuple[int, int] = (300, 360)) -> bytes:
    picture = Image.new("RGB", size, (180, 120, 90))
    out = BytesIO()
    if kind == "JPEG":
        exif = Image.Exif()
        exif[0x010E] = HIDDEN  # ImageDescription
        picture.save(out, kind, exif=exif)
    else:
        picture.save(out, kind)
    return out.getvalue()


def docx_with_photo(photo: bytes) -> bytes:
    document = Document()
    document.add_paragraph("Sam Rivera")
    document.add_picture(BytesIO(photo))
    document.add_paragraph("Python Developer at Example Co")
    out = BytesIO()
    document.save(out)
    return out.getvalue()


def switch(client: TestClient, on: bool) -> None:
    profile = client.get("/api/profile").json()
    assert client.put("/api/profile", json={**profile, "show_photo": on}).status_code == 200


def upload_resume_with_photo(client: TestClient, provider: FakeProvider, photo: bytes) -> None:
    provider.text = json.dumps({"sections": [], "items": ["Python Developer at Example Co"]})
    assert upload(client, "resume.docx", docx_with_photo(photo)).status_code == 201  # type: ignore[attr-defined]
    worker.run_once()


def stored_photo(client: TestClient) -> Any:
    return client.get("/api/profile/photo")


def profile(client: TestClient) -> Any:
    return client.get("/api/profile").json()


def test_a_resumes_own_photo_is_used_without_asking(
    client: TestClient, provider: FakeProvider
) -> None:
    upload_resume_with_photo(client, provider, image())

    assert (profile(client)["has_photo"], profile(client)["photo_from_resume"]) == (True, True)
    assert stored_photo(client).status_code == 200
    # There's nothing to add while the resume's own photo is used.
    refused = client.post("/api/profile/photo", files={"file": ("me.png", image())})
    assert refused.status_code == 409


def test_without_a_photo_in_the_resume_there_is_none_until_the_person_adds_one(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.text = json.dumps({"sections": [], "items": ["Python Developer at Example Co"]})
    upload(client, "resume.docx", make_docx(["Sam Rivera", "Python"]))
    worker.run_once()

    assert (profile(client)["show_photo"], profile(client)["has_photo"]) == (False, False)
    assert stored_photo(client).status_code == 404

    added = client.post("/api/profile/photo", files={"file": ("me.png", image())})

    assert added.status_code == 200
    assert (added.json()["show_photo"], added.json()["has_photo"]) == (True, True)
    assert added.json()["photo_from_resume"] is False


def test_a_new_resume_without_a_photo_drops_the_old_resumes_but_keeps_one_the_person_added(
    client: TestClient, provider: FakeProvider
) -> None:
    upload_resume_with_photo(client, provider, image())
    provider.text = json.dumps({"sections": [], "items": ["Python Developer at Example Co"]})
    upload(client, "resume.docx", make_docx(["Sam Rivera", "Python"]))

    assert profile(client)["has_photo"] is False

    client.post("/api/profile/photo", files={"file": ("me.png", image())})
    upload(client, "resume.docx", make_docx(["Sam Rivera", "Python"]))

    assert profile(client)["has_photo"] is True


def test_a_resumes_photo_never_reaches_the_model(
    client: TestClient, provider: FakeProvider
) -> None:
    posting_id, ids = rated_match(client, provider)
    photo = image()
    upload_resume_with_photo(client, provider, photo)
    write_sections(provider, ids)

    application = apply(client, posting_id)
    run_worker()

    kept = stored_photo(client)
    assert kept.headers["content-type"] == "image/jpeg"
    pack = client.get(f"/api/applications/{application['id']}").json()["pack"]
    assert pack["status"] == "ready"
    # Neither photo, nor any JPEG or PNG at all, is in what the resume reading or the Pack sent.
    sent = json.dumps(provider.received)
    for data in (photo, kept.content):
        assert base64.b64encode(data).decode() not in sent
    assert not any(start in sent for start in ("/9j/", "iVBORw0KGgo", "data:image"))


def test_a_resumes_photo_is_its_biggest_portrait_not_a_logo_or_banner() -> None:
    document = Document()
    for size in [(48, 48), (900, 200), (200, 240)]:
        document.add_picture(BytesIO(image(size=size)))
    out = BytesIO()
    document.save(out)

    found = photo_in_resume(out.getvalue())

    assert found is not None
    assert Image.open(BytesIO(found)).size == (200, 240)


def test_a_separate_upload_replaces_the_photo_as_one_small_image_without_its_metadata(
    client: TestClient,
) -> None:
    assert client.post("/api/profile/photo", files={"file": ("a.png", image())}).status_code == 200

    replaced = client.post(
        "/api/profile/photo", files={"file": ("b.jpg", image("JPEG", (1200, 900)))}
    )

    assert replaced.status_code == 200
    content = stored_photo(client).content
    assert HIDDEN.encode() not in content
    kept = Image.open(BytesIO(content))
    assert kept.size[0] == kept.size[1] <= 400
    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute("SELECT count(*) FROM profiles WHERE photo IS NOT NULL").fetchone() == (
            1,
        )


def test_a_file_that_isnt_an_image_or_is_too_big_is_refused(client: TestClient) -> None:
    not_image = client.post("/api/profile/photo", files={"file": ("me.png", b"<svg>not</svg>")})
    too_big = client.post("/api/profile/photo", files={"file": ("me.png", b"\0" * 5_000_001)})

    assert not_image.status_code == 422
    assert "isn't an image" in not_image.json()["detail"]
    assert too_big.status_code == 413
    assert stored_photo(client).status_code == 404


def test_unticking_add_a_photo_deletes_the_persons_photo_but_not_the_resumes(
    client: TestClient, provider: FakeProvider
) -> None:
    client.post("/api/profile/photo", files={"file": ("me.png", image())})

    switch(client, False)

    assert stored_photo(client).status_code == 404
    upload_resume_with_photo(client, provider, image())
    switch(client, False)
    assert stored_photo(client).status_code == 200


def test_the_photo_is_in_the_styled_resume_only_and_it_still_passes_the_ats_check(
    client: TestClient, provider: FakeProvider
) -> None:
    pack = ready_pack(client, provider)
    client.post("/api/profile/photo", files={"file": ("me.png", image())})
    base = f"/api/applications/{pack['id']}"
    client.put(f"{base}/review", json={"reviewed": True})

    def pictures(path: str, pair: str) -> int:
        response = client.get(f"{base}/{path}", params={"pair": pair})
        assert response.status_code == 200, response.text
        return len(Document(BytesIO(response.content)).inline_shapes)

    assert pictures("resume.docx", "styled") == 1
    assert pictures("resume.docx", "plain") == 0
    assert pictures("cover-letter.docx", "styled") == 0
    assert client.get(base).json()["has_photo"] is True


def test_delete_everything_removes_the_photo(client: TestClient) -> None:
    client.post("/api/profile/photo", files={"file": ("me.png", image())})

    client.post("/api/delete-everything", json={"confirm": "DELETE"})

    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute("SELECT count(*) FROM profiles WHERE photo IS NOT NULL").fetchone() == (
            0,
        )


def test_a_photo_is_found_in_a_pdf_resume_too() -> None:
    pdf = BytesIO()
    Image.new("RGB", (300, 300), (10, 20, 30)).save(pdf, "PDF")

    found = photo_in_resume(pdf.getvalue())

    assert found is not None
    assert Image.open(BytesIO(found)).size == (300, 300)


def test_a_resume_with_two_pictures_under_one_name_gives_no_photo() -> None:
    out = BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # zipfile warns about the duplicate, as it should.
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr("word/media/image1.png", image(size=(64, 64)))
            archive.writestr("word/media/image1.png", image(size=(300, 360)))

    assert photo_in_resume(out.getvalue()) is None
