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


@pytest.mark.parametrize(
    ("claim", "evidence", "unsupported"),
    [
        # A certification the posting asks for, which no Evidence names.
        (
            "AWS Certified Machine Learning Specialty",
            ["Built retrieval with Python"],
            "AWS Certified Machine Learning Specialty",
        ),
        (
            "I hold the AWS Certified Machine Learning Specialty.",
            ["Earned the AWS Certified Solutions Architect certification"],
            "AWS Certified Machine Learning Specialty",
        ),
        ("AWS Certified Solutions Architect", ["AWS Certified Solutions Architect, 2023"], None),
        # Case and punctuation don't matter; the credential's words do.
        ("aws certified solutions architect", ["AWS Certified Solutions Architect"], None),
        (
            "Master's in Computer Science",
            ["Education: BSc Computer Science"],
            "Master's in Computer Science",
        ),
        ("MSc Data Science", ["Education: BSc Computer Science"], "MSc Data Science"),
        ("BSc Computer Science", ["Education: BSc Computer Science, Example University"], None),
        ("PhD in Machine Learning", ["Wrote evaluation suites"], "PhD in Machine Learning"),
        ("Licensed Professional Engineer", ["Built APIs"], "Licensed Professional Engineer"),
        # A lead-in word or a list before the credential doesn't change which one it is.
        ("Earned AWS Certified Solutions Architect", ["AWS Certified Solutions Architect"], None),
        (
            "Holds the AWS Certified Solutions Architect",
            ["AWS Certified Solutions Architect"],
            None,
        ),
        ("Python, AWS Certified Solutions Architect", ["AWS Certified Solutions Architect"], None),
        (
            "Python, AWS Certified Machine Learning Specialty",
            ["AWS Certified Solutions Architect"],
            "AWS Certified Machine Learning Specialty",
        ),
        # The issuer's name counts, even when it isn't an acronym.
        (
            "Oracle Certified Professional",
            ["Microsoft Certified Professional"],
            "Oracle Certified Professional",
        ),
        (
            "Python, Oracle Certified Professional",
            ["Microsoft Certified Professional"],
            "Oracle Certified Professional",
        ),
        ("Oracle Certified Professional", ["Oracle Certified Professional, 2021"], None),
        ("Earned Oracle Certified Professional", ["Oracle Certified Professional, 2021"], None),
        # Degrees written out in full.
        (
            "Bachelor of Science in Physics",
            ["Education: BSc Computer Science"],
            "Bachelor of Science in Physics",
        ),
        ("Master of Science in AI", ["Built APIs"], "Master of Science in AI"),
        ("Bachelor of Science in Physics", ["Bachelor of Science in Physics, 2015"], None),
        # Words that only look like credentials aren't checked.
        ("Certified the release process for the team", ["Ran the release process"], None),
        ("Built APIs for a Masters programme website", ["Built APIs"], None),
    ],
)
def test_a_certification_licence_or_degree_must_be_named_by_its_evidence(
    claim: str, evidence: list[str], unsupported: str | None
) -> None:
    assert unsupported_detail(claim, evidence, TODAY) == unsupported
