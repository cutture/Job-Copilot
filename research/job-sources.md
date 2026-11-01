# Job and freelance sources

Research for ticket #2. Checked 2026-11-01. Limits, prices and terms change, so re-check them before building an adapter. This is a reading of published terms, not legal advice.

## Answer

- **Best first sources for employment:** the public job board APIs of Greenhouse, Ashby and Lever, polled for a watchlist of target employers. They need no key or cost, and they lead straight to the employer. Add Himalayas, Remotive, Remote OK, Jobicy and We Work Remotely for remote discovery, then Adzuna as a key each user brings.
- **Breadth, including Indeed and LinkedIn:** there is no job-seeker search API from either company that I could find. JobsPipe is the practical route, on a key each user brings, with an open question about its collection (see [Open questions](#open-questions)).
- **Freelance:** Upwork is the only major marketplace with a documented route for personal use, and it needs an approved key per user. Freelancer.com's API answers without a key, but its terms require express written permission for automated access, so get that first.
- **Self-hosting works well; a hosted version does not inherit it.** Adzuna and Upwork both limit their ordinary access to personal or internal use, so a hosted product would need separate agreements.
- **No source can be proven best at landing work.** The evidence is employer-side and vendor-published. Job Copilot's own funnel, split by source, is the evidence worth trusting.

## Recommended v1 order

1. Greenhouse, Ashby and Lever watchlist.
2. Himalayas and Remotive.
3. Upwork, if the key request is approved.
4. Remote OK, Jobicy, We Work Remotely, Adzuna and Hacker News as cheap additions.
5. JobsPipe, optional and off by default until the open question is settled.

## Employment sources with permitted access

"BYO" means each self-hosting user can get their own access. Live counts come from one probe on 2026-11-01, keyword-matching `genai`, `gen ai`, `generative ai`, `llm`, `rag`, `langchain`, `langgraph`, `prompt engineer` or `ai engineer` unless stated. Matches in a description can be incidental, so treat them as rough signals only.

| Source | Access and BYO | Cost | Limits | Terms that shape the design | Remote and GenAI coverage |
|---|---|---|---|---|---|
| [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html) | No auth for GET; a per-employer `board_token` is needed | Free | None published | Published as public data; third-party reuse terms not found | Anthropic's board returned 675 jobs |
| [Ashby posting API](https://developers.ashbyhq.com/docs/public-job-posting-api) | No auth described; per-employer board name | Free (no cost stated) | None published | Docs address an organisation's own board; third-party polling isn't addressed | OpenAI's board returned 810 jobs, 543 flagged `isRemote` |
| [Lever Postings API](https://github.com/lever/postings-api) | No auth described for GET; per-employer site name | Free (no cost stated) | Published only for application POSTs | Same gap as Ashby | Not measured: my one guessed slug returned 0, which says nothing about coverage |
| [Himalayas](https://himalayas.app/docs/remote-jobs-api) | No key needed; free key recommended; BYO | Free | 60/min and 10,000/day with a key; data refreshed every 24 hours | Visible credit and link; Apply must use `applicationLink`; [no passing jobs to third parties, remove expired jobs](https://himalayas.app/terms) | Remote only. `llm` search reported 4,513 results, which looks like loose matching, so it needs a quality check |
| [Remotive](https://github.com/remotive-com/remote-jobs-api) | No key; BYO | Free; private paid API on request | Max 4 fetches a day advised; over 2 requests/min blocked; [jobs delayed 24 hours](https://remotive.com/remote-jobs/api) | Credit and link back; no submitting to third-party sites; no using jobs to collect signups or emails, which matters for a hosted version | Remote only. `llm` 12; `ai engineer` 12 |
| [Remote OK](https://remoteok.com/api) | No key; BYO | Free | None published | Followed link back and credit; no logo | Remote only. 12 of 99 |
| [Jobicy](https://jobicy.com/jobs-rss-feed) | No key; BYO | Free; optional commercial key at $0.01 per job for direct ATS links | Up to 100 per request; last 7 days; sync at most hourly; 3-hour delay | Credit and link; free API Apply links stay on Jobicy | Remote focus. 11 of 100 |
| We Work Remotely RSS (`weworkremotely.com/remote-jobs.rss`) | No key; BYO | Free | Unknown | **Not verified:** its feed page returned 403 | Remote only. Feed returned 100 items; GenAI not measured |
| [Arbeitnow](https://www.arbeitnow.com/blog/job-board-api) | No key; BYO | Free; private endpoint paid | None published | No separate terms on that page | Europe focus, separate UK API. Page 1: 300 jobs, 14 remote, 17 keyword |
| [The Muse](https://www.themuse.com/developers/api/v2) | Key for use beyond testing; BYO | Cost not stated | 3,600/hour with key; 500/hour without | Linked terms not read | 703 remote software jobs; GenAI not measured |
| [Adzuna](https://developer.adzuna.com/overview) | Free key at once; BYO | [Free tier for evaluation; paid plans for more volume](https://developer.adzuna.com/docs/terms_of_service) | Shown in the account, not published | Personal job search is allowed, with a visible Adzuna label; any revenue or lead-generating product needs a licence; organisations get a 14-day trial | Not measured |
| [JobsPipe](https://jobspipe.dev/pricing) | Account key; BYO | 1,000 one-time free credits; paid from $19.60/month for 10,000 | 1 credit per job per month; free tier 2 req/s, 25 results a call, data up to 24h old | [Keep the link to the original; no bulk redistribution; no profiling people](https://jobspipe.dev/terms) | [Collects 14 of 44 listed sources, including Indeed and LinkedIn, but not Glassdoor or ZipRecruiter](https://jobspipe.dev/sources). Not measured |
| [Hacker News "Who is hiring?"](https://github.com/HackerNews/API) | No key found; BYO | Free | API repo says no current rate limit | [YC terms restrict commercial use and scraping of the site](https://www.ycombinator.com/legal/); personal use looks defensible, a hosted version needs asking | October 2026 thread had 390 comments; free text needs parsing |
| [Reed](https://www.reed.co.uk/developers/jobseeker) | Key; BYO | Not stated | 100 results a request | Terms not found | UK. Not measured |
| [USAJOBS](https://developer.usajobs.gov/guides/authentication) | Key by application; BYO | Not stated | [500 a page, 10,000 a query](https://developer.usajobs.gov/guides/rate-limiting) | Terms not read | US federal only, so low fit |
| [Jooble](https://jooble.org/api/about) | Key by form, which asks for name, position, phone and website; BYO likely | Not stated | Not stated | Not verified | Not measured |
| [JSearch](https://www.openwebninja.com/api/jsearch) | Vendor key; BYO | Not verified | Not verified | Not verified; resells Google for Jobs data including LinkedIn, Indeed and Glassdoor listings | Not measured |

## Major sources without job-seeker access

| Source | What I found |
|---|---|
| **Indeed** | [Job Sync API](https://docs.indeed.com/job-sync-api) is for ATS partners managing postings, not for job search. Third-party sources say the Publisher program closed to new publishers, with differing dates. Its [terms](https://www.indeed.com/legal) ban automating Indeed Apply outside its official tooling. |
| **LinkedIn** | [Job Posting API](https://learn.microsoft.com/en-gb/linkedin/talent/premium-job-posting) posts jobs and needs a partnership. Its [User Agreement](https://www.linkedin.com/legal/user-agreement) section 8.2 bans scraping tools and unauthorised bots. |
| **Wellfound** | [Terms](https://wellfound.com/terms) ban scraping and using content for commercial activity. No API found. Check it by hand. |
| **Glassdoor** | JobsPipe says the v1 partner API [stopped answering in August 2025](https://jobspipe.dev/sources). This comes from a competitor and is unconfirmed. |
| **ZipRecruiter, Careerjet, Google Cloud Talent, SerpApi** | Searched, but nothing usable came back. Not assessed. |

Do not scrape these sites or buy third-party scrapers for them. Apify listings exist for Wellfound, including one advertising a bot-protection bypass, and that sits badly with the terms above.

## Freelance sources

| Source | Access and BYO | Limits | Terms | Coverage |
|---|---|---|---|---|
| **Upwork** | [Request a key](https://support.upwork.com/hc/en-us/articles/115015857647-How-to-request-an-API-key-from-Upwork), describing the use; BYO, subject to approval | 40,000 requests/day | Personal and internal use only, commercial use unsupported; a key can be disabled for use beyond the request; [no scraping or proposal spam even with a key](https://support.upwork.com/hc/en-us/articles/43342677368467-Use-bots-and-other-automation-properly) | Remote by nature. Not measured. Job search query not confirmed |
| **Freelancer.com** | [Developer portal](https://developers.freelancer.com/); the project search answered without a key | Not found | [Section 33 bars automated access, expressly including the API, without express written permission; fines of up to US$3,000 a breach](https://www.freelancer.com/about/terms) | `llm` returned 19 active projects |
| **Fiverr, Toptal, PeoplePerHour, Guru, Contra** | No public API found. This is a failed search, not proof that none exists | n/a | [Fiverr's terms](https://www.fiverr.com/legal-portal/legal-terms/terms-of-service) returned 403 | Manual use only |

## What helps land work

All of this is employer-side data from vendors with an interest, and none of it is specific to GenAI or freelance work.

- [Ashby](https://www.ashbyhq.com/talent-trends-report/reports/inbound), nearly 250K hires from 2021 to mid-2025: inbound was 52% of hires in Q2 2025, referrals about 17-18%, sourced about 16%. The figures reflect Ashby's customers.
- [Breezy](https://breezy.hr/resources/hiring-reports/source-of-hire-report), 14.2M applications in 2025: Indeed accounted for 76% of hires made through Breezy, and referrals converted at 8%, about four times any major job board. Its customer base may differ from GenAI employers.
- **What this means for the design:** applying directly works, and referrals convert best. No API supplies referrals, so a person has to pursue them. Job Copilot could flag a known contact later, but that's outside this ticket.

Trustpilot snapshot. These scores mix employers, freelancers and job seekers, and several samples are tiny, so they say little about job outcomes.

| Source | Score | Reviews |
|---|---|---|
| [Freelancer.com](https://www.trustpilot.com/review/www.freelancer.com) | 4.4 | 20,224 |
| [Upwork](https://www.trustpilot.com/review/www.upwork.com) | 4.2 | 16,857 |
| [Himalayas](https://www.trustpilot.com/review/himalayas.app) | 3.2 | 7 |
| [We Work Remotely](https://www.trustpilot.com/review/weworkremotely.com) | 2.9 | 263 |
| [Remotive](https://www.trustpilot.com/review/remotive.com) | 2.7 | 4 |
| [Indeed](https://www.trustpilot.com/review/www.indeed.com) | 1.8 | 13,079 |

## Consequences for the spec

- **Adapters need per-source rules:** poll interval, credit text and link, apply link handling, and expiry removal.
- **Source keys belong to each user.** Self-hosted users bring their own keys, and terms should be recorded per source so a hosted version can see what it must license first.
- **Filter loosely, then score.** Keyword search quality varies, as the Himalayas result shows.
- **Store the source on every Job Posting and Application,** so the funnel can show which sources produce Interviews and Offers.
- **Autofill:** the planned Chrome extension must not automate Indeed Apply. Copy buttons are safe; review any extension behaviour against Indeed's terms.

## Open questions

1. **JobsPipe's Indeed and LinkedIn data.** JobsPipe says it collects [public postings without logins](https://jobspipe.dev/trust). LinkedIn's terms bar copying through data aggregators without consent. Whether that exposes a JobsPipe customer is a legal question I can't settle, and the owner should decide whether to enable it.
2. **Sending postings to LLM providers.** Himalayas and Remotive restrict passing jobs on to third parties, in terms aimed at job boards and aggregators. Neither API section addresses AI processing. Himalayas clause 30A covers AI assistants under its own conditions, which I did not read in full. Check before release, or ask them.
3. **Freelancer.com permission.** Someone needs to ask for written permission, and to learn whether it can apply per self-hosting user.

## Not verified

- **Upwork:** its pages returned 403 to my fetcher, so these details come from search excerpts of its help center. I did not read the API Terms or confirm the job search query and its scope. Approval odds are unknown.
- **Freelancer.com:** developer docs returned no readable content, so auth, rate limits and any cost are unconfirmed. I made one anonymous search request to confirm it responds, and an adapter should not rely on that.
- **Indeed's terms:** only about the first 100K of 349K characters were read, and that part did not mention scraping. The API terms were not read.
- **Publisher program closure:** rests on third-party sources, including a competitor.
- **Adzuna:** free tier size and country list were not published on the pages I could read.
- **We Work Remotely:** terms were not readable.
- **Jooble, JSearch, Foorilla (the former aijobs.net):** pricing, limits and terms could not be read. Foorilla links an API page whose listing was not readable, and it could be worth a manual look because of its AI focus.
- **Rate limits:** "none published" means I did not find any, not that none are enforced.
- **Live counts:** one moment, one keyword method. The remote flag was not checked for quality, and OpenAI's `isRemote` count in particular deserves a look.
