"""Verification asks once more about lines it skipped. Only the model provider is faked."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from job_copilot import applications, gateway
from tests.conftest import FakeProvider
from tests.test_application_pack import apply, rated_match, run_worker
from tests.test_my_sections import write_sections

# A summary line every run of write_sections drafts and Verification judges reworded.
SKIPPED_TEXT = "Python developer who ships retrieval systems."


def verification_skipping(
    monkeypatch: pytest.MonkeyPatch, provider: FakeProvider, times: int
) -> list[list[str]]:
    """Verification's answer leaves out the summary line `times` times; returns the IDs each
    Verification call was asked about."""
    asked: list[list[str]] = []
    answer = gateway.call_provider
    full = {s["id"]: s for s in json.loads(provider.tasks["verify"])["statements"]}

    def skipping(model: str, messages: list[dict[str, str]], max_tokens: int) -> Any:
        given = answer(model, messages, max_tokens)
        task = json.loads(messages[-1]["content"])
        if task.get("task") != "verify":
            return given
        ids = [s["id"] for s in task["statements"]]
        asked.append(ids)
        skip = "m0" if len(asked) <= times else None
        judged = [full[i] for i in ids if i in full and i != skip]
        text = json.dumps({"statements": judged})
        return gateway.ProviderAnswer(text, given.input_tokens, given.output_tokens)

    monkeypatch.setattr(gateway, "call_provider", skipping)
    return asked


def pack_with(client: TestClient, provider: FakeProvider, monkeypatch: Any, times: int) -> Any:
    posting_id, ids = rated_match(client, provider)
    write_sections(provider, ids)
    asked = verification_skipping(monkeypatch, provider, times)
    application = apply(client, posting_id)
    run_worker()
    pack = client.get(f"/api/applications/{application['id']}").json()["pack"]
    return pack, asked


def summary(pack: Any) -> list[str]:
    return [
        c["text"] for s in pack["resume"]["sections"] if s["kind"] == "summary" for c in s["claims"]
    ]


def test_a_line_verification_skips_is_asked_about_again_and_kept(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch, caplog: Any
) -> None:
    pack, asked = pack_with(client, provider, monkeypatch, times=1)

    assert SKIPPED_TEXT in summary(pack)
    # Asked again about only the skipped line, so nothing else is sent twice.
    assert asked[-1] == ["m0"]
    assert "Verification left 1 line unjudged: {'summary': 1}" in caplog.text
    assert SKIPPED_TEXT not in caplog.text


def test_a_line_still_skipped_after_asking_again_is_removed_as_unchecked(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch, caplog: Any
) -> None:
    pack, asked = pack_with(client, provider, monkeypatch, times=2)

    assert SKIPPED_TEXT not in summary(pack)
    removed = {r["text"]: r["kind"] for r in pack["removed_claims"]}
    assert removed[SKIPPED_TEXT] == "unchecked"
    assert "still unjudged after asking again: {'summary': 1}" in caplog.text


@pytest.mark.parametrize(
    ("claim_id", "kind"),
    [
        ("m0", "summary"),
        ("s3", "skills"),
        ("g1", "skills"),
        ("g1s2", "skills"),
        ("e0", "experience"),
        ("e2b1", "experience"),
        ("d0", "education"),
        ("q0", "qualifications"),
        ("a1", "affiliations"),
        ("t0", "certifications"),
        ("u0l1", "custom"),
        ("c1s0", "cover letter"),
        ("x9", "other"),
        ("e0x1", "other"),
        ("not an id", "other"),
    ],
)
def test_each_claim_id_names_where_its_line_is(claim_id: str, kind: str) -> None:
    assert applications.claim_kind(claim_id) == kind
