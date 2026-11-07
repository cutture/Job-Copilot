"""The keyword coverage score: direct tests of the pure function, and the page that shows it."""

from typing import Any

from fastapi.testclient import TestClient

from job_copilot.coverage import keyword_coverage
from tests.conftest import FakeProvider
from tests.test_my_sections import ready_pack


def result(text: str, outcome: str, *evidence_ids: int, kind: str = "must_have") -> dict[str, Any]:
    return {
        "requirement": text,
        "kind": kind,
        "result": outcome,
        "evidence_ids": list(evidence_ids),
    }


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
    assert [(r.requirement, r.in_resume) for r in coverage.requirements] == [
        ("Python", True),
        ("Retrieval", False),
        ("Kubernetes", False),
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
    assert not any(r.in_resume for r in coverage.requirements)


def test_hard_blockers_are_not_keywords() -> None:
    coverage = keyword_coverage(
        [result("Based in the EU", "met", kind="hard_blocker"), result("Python", "met", 1)],
        cited={1},
    )

    assert coverage is not None
    assert coverage.score == 100
    assert [r.requirement for r in coverage.requirements] == ["Python"]


def test_with_nothing_to_count_there_is_no_score() -> None:
    assert keyword_coverage([], set()) is None
    assert keyword_coverage([result("Remote", "met", kind="hard_blocker")], set()) is None


def test_the_final_documents_show_the_score_and_what_it_counts(
    client: TestClient, provider: FakeProvider
) -> None:
    # Three must-haves met by the Retrieval Evidence, which the resume cites, and a
    # nice-to-have that's missing.
    pack = ready_pack(client, provider)

    coverage = pack["coverage"]
    assert coverage["score"] == 75
    assert [(r["requirement"], r["in_resume"]) for r in coverage["requirements"]] == [
        ("Skill 0", True),
        ("Skill 1", True),
        ("Skill 2", True),
        ("Terraform", False),
    ]
