"""Claim rules: the exact checks Verification makes in code."""

from datetime import date

import pytest

from job_copilot.claims import unsupported_detail, years_shown

TODAY = date(2026, 11, 4)


@pytest.mark.parametrize(
    ("evidence", "years"),
    [
        (["Python Developer, Example Co, Jan 2021 to present"], 5),
        (["Analyst, 2015 - 2018", "Engineer, Mar 2018 – Dec 2020"], 3),
        (["Built a retrieval pipeline"], 0),
        (["Engineer, 2019 until now"], 7),
    ],
)
def test_years_shown_is_the_longest_dated_range(evidence: list[str], years: int) -> None:
    assert years_shown(evidence, TODAY) == years


@pytest.mark.parametrize(
    ("claim", "evidence", "unsupported"),
    [
        ("Reduced support costs by 40%", ["Cut support costs by 40 percent"], None),
        ("Reduced support costs by 40%", ["Cut support costs"], "40%"),
        ("Served 1,200 customers", ["Served 1200 customers a day"], None),
        ("5 years of Python", ["Python Developer, Jan 2021 to present"], None),
        ("8+ years of Python", ["Python Developer, Jan 2021 to present"], "8+ years"),
        ("5 years of Python", ["Wrote Python for 5 years"], None),
        ("Python Developer, Jan 2021 to present", ["Python Developer, Jan 2021 to present"], None),
        ("Developer, Jan 2019 to present", ["Developer, Jan 2021 to present"], "2019"),
        ("Led a team of six engineers", ["Member of a team"], None),
        ("Built github.com/srivera/drafter-2", ["Built github.com/srivera/drafter-2"], None),
        ("See https://evil.example.com/x.", ["Built a pipeline"], "https://evil.example.com/x."),
        ("Write to me at sam@example.com.", ["Contact: sam@example.com"], None),
        ("Write to hr@example.com", ["Contact: sam@example.com"], "hr@example.com"),
        ("Apply at evil.example.com/form", ["Built a pipeline"], "evil.example.com/form"),
        ("Visit example.com.evil.test", ["See example.com"], "example.com.evil.test"),
        ("Built APIs with Node.js", ["Built APIs with Node.js"], None),
    ],
)
def test_every_number_link_and_email_in_a_claim_must_be_in_its_evidence(
    claim: str, evidence: list[str], unsupported: str | None
) -> None:
    assert unsupported_detail(claim, evidence, TODAY) == unsupported
