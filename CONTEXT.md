# Job Copilot

A self-hosted job-search assistant for employment and remote freelance work. It finds and rates jobs, prepares application documents backed by Evidence, and tracks progress, while a person reviews everything and submits every application.

## Language

### Finding jobs

**Job Posting**:
A job advertised by an employer, typed as employment or freelance. Contract postings count as freelance.
_Avoid_: Job, listing, ad, vacancy

**Source**:
Where a Job Posting came from, such as an employer's job board, a job feed, or the Manual Source.
_Avoid_: Provider, board, site

**Search Window**:
The maximum age, 15 days from the search date, of a posting a search can add.
_Avoid_: Date range, freshness limit

**Watchlist**:
The employers a person has chosen to follow by adding their careers page.
_Avoid_: Target list, favourites

**Manual Source**:
The Source for Job Posting text a person pastes in from an employer's own career page.
_Avoid_: Import, manual upload

**Filter**:
The step that decides from posting text and search preferences alone whether a Job Posting is worth rating. It never sees personal data.
_Avoid_: Screening, Match scoring

**Filtered Posting**:
A Job Posting that Filter set aside, which stays viewable with the reason.
_Avoid_: Rejected posting

**Nearby**:
A label on a Job Posting in the same state or region as a place the person chose, rather than in that place.
_Avoid_: Close match

**Location Preference**:
The work arrangements and places a person wants, which Filter uses. It is separate from where the person lives.
_Avoid_: Location, places

### The person

**Profile**:
Everything a person has told Job Copilot about themselves: their Evidence, facts about them, and what they're looking for.
_Avoid_: Account, user data

**Evidence**:
An item from the resume, public GitHub or a Profile entry that a factual claim can trace back to.
_Avoid_: Proof, source, facts

**Confirmed Evidence**:
Evidence the person has checked: a resume item they confirmed or corrected, or one they wrote themselves. Only Confirmed Evidence can support a Claim or a Requirement Result.
_Avoid_: Approved, verified, accepted Evidence

**Self-reported**:
Evidence that the person wrote themselves as a Profile entry, which counts as Evidence and is shown as self-reported.
_Avoid_: Unverified, manual Evidence

### Rating

**Match**:
A Job Posting that passed Filter, along with its rating against a person's Evidence.
_Avoid_: Result, recommendation, job

**Requirement**:
Something a Job Posting asks for, classed as a Hard Blocker, must-have or nice-to-have and backed by a quote from the posting.
_Avoid_: Criterion, qualification

**Hard Blocker**:
A Requirement that can rule someone out regardless of skills, such as location, work authorization, a required language or clearance.
_Avoid_: Dealbreaker, knockout

**Requirement Result**:
The judgement on one Requirement: Met, Partial, Missing or Unknown. Unknown is treated like Missing.
_Avoid_: Verdict, score

**Interview Likelihood**:
A High, Medium or Low estimate of how well a person's Evidence covers what a Job Posting asks for. It doesn't predict the employer's decision.
_Avoid_: Match score, fit score, probability

**Band**:
One of the three Interview Likelihood levels: High, Medium or Low.
_Avoid_: Tier, grade

**Rescore**:
Judging a Match again against the current Profile, at the person's request. It is never automatic.
_Avoid_: Refresh, re-rank

### Applying

**Apply**:
The person's action on a Match that starts an Application and its Application Pack. It never submits anything.
_Avoid_: Submit, auto-apply

**Application**:
A person's pursuit of one Job Posting, starting when they click Apply.
_Avoid_: Submission, job application record

**Application Pack**:
The tailored resume, cover letter and form answers prepared for one Application. Each regeneration makes a new version.
_Avoid_: Documents, package, bundle

**Proposal**:
A freelance pitch and bid, which v1 does not generate.
_Avoid_: Cover letter, bid

**Submitted**:
The status a person sets after sending an application themselves on the employer's site.
_Avoid_: Applied, sent

**Change Request**:
A person's instruction to regenerate an Application Pack differently. It can't add a fact without verification.
_Avoid_: Prompt, edit, feedback

### Claims

**Claim**:
A factual statement about the person in an Application Pack.
_Avoid_: Statement, bullet

**Verification**:
The separate step that checks each Claim against Evidence and removes those it can't support.
_Avoid_: Fact check, validation

**Reworded Claim**:
A Claim that restates something in the Evidence in different words, which is allowed.
_Avoid_: Paraphrase, stretched claim

**Stretched Claim**:
A Claim based on something real in the Evidence but inflated beyond it, such as "led a team" from "member of a team".
_Avoid_: Exaggeration, invented claim

**Invented Claim**:
A Claim about something not mentioned anywhere in the resume or Profile.
_Avoid_: Hallucination, stretched claim, false claim

**Removed Claim**:
A Claim that Verification took out and listed for the person with a reason.
_Avoid_: Rejected claim, deleted claim

**Keep Anyway**:
A person's explicit, recorded decision to keep a Removed Claim after a warning. It never counts as support from Evidence.
_Avoid_: Override, force, approve

### Outcomes and measurement

**Outcome**:
What a person reports happened after Submitted: Interview, Offer, Rejected or No response. It is self-reported, and employer messages are never read.
_Avoid_: Reply, result, status

**Check-in**:
A prompt asking whether a person heard back, shown on the dashboard after 14 days with no Outcome, and sent by email only if they opt in.
_Avoid_: Notification, follow-up

**Funnel**:
The stages Matches → Apply clicks → Submitted → Interview → Offer, with the rate between each.
_Avoid_: Pipeline

**Eval Run**:
One execution of the eval set against the models in use, with its stored results.
_Avoid_: Test run, benchmark

**Eval Case**:
One invented test scenario with labelled expected results. It never contains real personal data.
_Avoid_: Golden, fixture, test

**Hard Failure**:
An eval result that must never happen, such as an Invented Claim reaching a final Application Pack.
_Avoid_: Critical bug, blocker

**Tracked Score**:
An eval measure watched for trends and judged against a target, which isn't a Hard Failure when missed.
_Avoid_: Soft failure, KPI

**Challenger**:
A model evaluated against the one currently used for a step, which replaces it only with the owner's approval.
_Avoid_: Candidate, alternative

**Fallback List**:
The ordered models a step may use when its usual model is unavailable, limited by what data the step handles.
_Avoid_: Backup chain, failover

**Retrospective**:
A written review of eval results, failures, fixes, costs and totals, containing no personal or employer details.
_Avoid_: Postmortem, report
