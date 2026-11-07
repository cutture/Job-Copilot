"""The keyword coverage score: direct tests of the pure function, and the page that shows it."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from job_copilot import gateway
from job_copilot.coverage import keyword_coverage
from job_copilot.rating import RequirementView
from tests.conftest import FakeProvider
from tests.test_application_pack import apply, rated_match, run_worker
from tests.test_my_sections import ready_pack, write_sections


def result(text: str, outcome: Any, *evidence_ids: int, kind: Any = "must_have") -> RequirementView:
    return RequirementView(
        requirement=text,
        kind=kind,
        quote=None,
        result=outcome,
        evidence=[],
        gap=None,
        evidence_ids=list(evidence_ids),
    )


def test_a_requirement_counts_only_when_the_resume_cites_its_evidence() -> None:
    coverage = keyword_coverage(
        [
            result("Python", "met", 1),
            result("Retrieval", "met", 2),
            result("Kubernetes", "missing"),
            result("Terraform", "met", 3, kind="nice_to_have"),
        ],
        cited={1, 3},
    )

    assert coverage is not None
    assert coverage.score == 50
    assert [(r.requirement, r.in_resume) for r in coverage.counted] == [
        ("Python", True),
        ("Retrieval", False),
        ("Kubernetes", None),
        ("Terraform", True),
    ]


def test_a_partial_result_counts_half() -> None:
    coverage = keyword_coverage([result("Python", "partial", 1), result("SQL", "met", 2)], {1, 2})

    assert coverage is not None
    assert coverage.score == 75


def test_citing_evidence_never_covers_a_missing_or_unknown_result() -> None:
    coverage = keyword_coverage(
        [result("Python", "missing", 1), result("Go", "unknown", 1)], cited={1}
    )

    assert coverage is not None
    assert coverage.score == 0
    assert [r.in_resume for r in coverage.counted] == [None, None]


def test_a_result_resting_on_no_evidence_item_cant_be_traced_so_isnt_counted() -> None:
    # Such as a degree decided by the Profile's Education, or a Result rated before Evidence
    # IDs were kept.
    coverage = keyword_coverage(
        [result("A degree", "met"), result("Python", "met", 1), result("Go", "missing")],
        cited={1},
    )

    assert coverage is not None
    assert coverage.score == 50
    assert [r.requirement for r in coverage.counted] == ["Python", "Go"]


def test_hard_blockers_are_not_keywords() -> None:
    coverage = keyword_coverage(
        [result("Based in the EU", "met", kind="hard_blocker"), result("Python", "met", 1)],
        cited={1},
    )

    assert coverage is not None
    assert coverage.score == 100
    assert [r.requirement for r in coverage.counted] == ["Python"]


def test_with_nothing_to_count_there_is_no_score() -> None:
    assert keyword_coverage([], set()) is None
    assert keyword_coverage([result("Remote", "met", kind="hard_blocker")], set()) is None
    assert keyword_coverage([result("A degree", "met")], set()) is None


def test_the_final_documents_show_the_score_and_what_it_counts(
    client: TestClient, provider: FakeProvider
) -> None:
    # Three must-haves met by the Retrieval Evidence, which the resume cites, and a
    # nice-to-have that's missing.
    pack = ready_pack(client, provider)

    coverage = pack["coverage"]
    assert coverage["score"] == 75
    assert [(r["requirement"], r["in_resume"]) for r in coverage["counted"]] == [
        ("Skill 0", True),
        ("Skill 1", True),
        ("Skill 2", True),
        ("Terraform", None),
    ]


def test_a_submitted_resume_keeps_its_coverage_after_its_evidence_is_deleted(
    client: TestClient, provider: FakeProvider
) -> None:
    pack = ready_pack(client, provider)
    base = f"/api/applications/{pack['id']}"
    client.put(f"{base}/review", json={"reviewed": True})
    client.post(f"{base}/submitted")
    retrieval = next(
        ref["id"]
        for section in pack["resume"]["sections"]
        for group in section["groups"]
        for ref in group["claims"][0]["evidence"]
    )

    client.delete(f"/api/evidence/{retrieval}")

    # It counts what was sent.
    assert client.get(base).json()["pack"]["coverage"]["score"] == 75


def test_a_writer_answer_that_isnt_json_is_asked_for_again(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    posting_id, ids = rated_match(client, provider)
    write_sections(provider, ids)
    answer = gateway.call_provider
    broken = ['{"paragraphs": [{"sentences": [{"text": "I "love" Python"}]}]}']

    def once_unescaped(model: str, messages: list[dict[str, str]], max_tokens: int) -> Any:
        given = answer(model, messages, max_tokens)
        if json.loads(messages[-1]["content"]).get("task") == "cover_letter" and broken:
            return gateway.ProviderAnswer(broken.pop(), given.input_tokens, given.output_tokens)
        return given

    monkeypatch.setattr(gateway, "call_provider", once_unescaped)

    application = apply(client, posting_id)
    run_worker()

    pack = client.get(f"/api/applications/{application['id']}").json()["pack"]
    assert pack["status"] == "ready"
