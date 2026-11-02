# Job sources: what the terms actually allow

Research for ticket #7, "Decide: sources for v1". Follows [research/job-sources.md](https://github.com/cutture/Job-Copilot/blob/research/job-sources/research/job-sources.md). Checked 2026-11-01. Terms change, so re-read them before building an adapter. This is a reading of published terms, not legal advice.

## Answer

- **Four sources have terms that expressly cover this use, including LLM processing:** Jobicy, USAJOBS, Arbetsförmedlingen (Sweden) and 4dayweek.io. A fifth, Canada's Job Bank dataset, has a clear licence but is a monthly file, so it fits poorly. Only Jobicy and 4dayweek are global remote sources.
- **No freelance marketplace passes.** I found no marketplace with a documented, permitted API. Those whose terms I could read either ban automated access or show no API. The only clear route to contract work is the contract postings in Jobicy and 4dayweek.
- **Greenhouse, Ashby and Lever are SILENT, not safe.** I found no terms aimed at third-party readers, and none that grant anything either. Under the owner's "any chance" rule, this needs an owner decision, or written confirmation from the vendors.
- **Several sources recommended earlier now fall to RISK:** Himalayas, Remotive, We Work Remotely and Hacker News. Their wording could bar this use.

## How verdicts work

The test covers the whole use: a self-hosted tool fetches postings for one person and sends the text to a third-party LLM provider to score them and draft material.

- **CLEAR:** the terms expressly allow this use, by naming AI use or by granting rights broad enough to cover it.
- **SILENT:** nothing found against it, and no express permission. This does not mean safe.
- **RISK:** wording could bar it.
- **Not verified:** the relevant page could not be read, so no verdict is given.

Quotes were taken from downloaded page text unless marked. Where a page was paraphrased by a fetch tool rather than read directly, no quote is given.

**One limit applies to every source:** posting text usually belongs to the employer, and an aggregator can only license what it holds. 4dayweek says this outright. Only the public-sector sources below have terms that deal with it, and they do so by excluding third-party or restricted content. None of the sources' terms say anything about the LLM provider's own handling of the text, which is a separate choice: pick a provider setting that does not train on inputs.

## CLEAR

| Source | Access and cost | Limits | Wording that matters | LLM addressed? | Conditions to build in |
|---|---|---|---|---|---|
| [Jobicy](https://jobicy.com/jobs-rss-feed) | No key. Free. Optional commercial key costs $0.01 per job for direct ATS links | Up to 100 a request; last 7 days; polling "must not exceed once per hour" | "The Jobicy API is designed for websites, applications, newsletters, research tools, AI products, and other services"; "Most integrations, including job boards, newsletters, career tools, AI assistants, and internal applications, can use the public API without a separate agreement."; "You can store, cache, process, and redistribute job data as needed." | **Yes.** Names AI products and AI assistants, allows "summaries" and allows processing and redistribution | "Clearly credit Jobicy as the original source when displaying listings."; "Apply links provided by our free API must continue to direct users to the original job pages on Jobicy." |
| [USAJOBS](https://developer.usajobs.gov/guides/terms-of-service) | Key by [application](https://developer.usajobs.gov/guides/authentication). No price shown | [500 a page, 10,000 a query](https://developer.usajobs.gov/guides/rate-limiting) | "Public Data may be copied, stored, reformatted, adapted, analyzed, published, redistributed, and used for lawful commercial or noncommercial purposes. Prior OPM approval is not required."; "API Consumers and downstream users may modify, summarize, analyze, or combine Public Data" | **Not by name.** The grant is broad enough to cover it | Do not imply government endorsement. Excludes content "separately identified in accompanying metadata or notice" as restricted, so honour that metadata. Announcements may contain agency contact names. US federal roles only, so low fit |
| [Arbetsförmedlingen job ads](https://data.arbetsformedlingen.se/dataset/job-ads/) (Sweden: JobSearch, JobStream) | One unauthenticated JobSearch call succeeded. No cost found | Not verified | Dataset page: "Licens: Creative Commons CC0", listed seven times. I did not map each listing to its service | **Not by name.** CC0 waives copyright and related rights where the publisher holds them | CC0 cannot clear other people's privacy rights, and ads may name contacts. Swedish-market ads, so low fit unless the user targets Sweden |
| [4dayweek.io](https://4dayweek.io/developers) | No key. Free | 60 requests a minute per IP; new listings can take up to 48 hours | "[...] licence to use, display and incorporate the results returned by our documented public API and MCP endpoint (each a \"Result\") in your own product or service, including in responses generated by an AI assistant" ([terms](https://4dayweek.io/terms)) | **Yes** | Credit and link; "do not use the Results to build, train or populate a competing job board or a substantially similar database"; delete stored copies within 30 days if revoked. **Carve-out:** "Nothing here grants rights in any third-party content a Result contains, including an employer's own trade marks, logos or job-description text". Reduced-hours employers only |
| [Canada Job Bank open data](https://open.canada.ca/data/en/dataset/ea639e28-c0fc-48bf-b5dd-b8899bd43072) | Free CSV download | Monthly files of past postings, not live search | [OGL Canada](https://open.canada.ca/en/open-government-licence-canada): "Copy, modify, publish, translate, adapt, distribute or otherwise use the Information in any medium, mode or format for any lawful purpose." | **Not by name.** "any lawful purpose" covers it | Attribution required. Excludes "Personal Information" and "third party rights the Information Provider is not authorized to license". Partly contributed by outside job boards. Not useful for finding open roles |

## SILENT: no express permission, not to be treated as safe

| Source | Access and cost | Limits | Wording that matters | LLM addressed? |
|---|---|---|---|---|
| [NAV Norway](https://navikt.github.io/pam-stilling-feed/) | Free. Public token "for experiments", or a private token after written agreement to the terms | Not verified | [Terms](https://arbeidsplassen.nav.no/vilkar-api) (Norwegian): "Konsumenter av APIet har rett til å republisere og vise mottekne jobbannonsar på sine tenester, og/eller bruke dei til statistiske/analytiske formål." In English: consumers may republish and display ads and/or use them for statistical or analytical purposes. Remove inactive ads; apply links go to the source; the consumer is a separate data controller for personal data in ads | No. Broad, but scoring and drafting are not named. Norway only |
| [Adzuna](https://developer.adzuna.com/docs/terms_of_service) | Free key at once; paid plans for higher personal volume | Shown in the account | "The Adzuna API may be used for: Personal job search" is an express grant for fetching. "The free tier is intended for evaluating the API." "Any other use, including commercial analysis, resale of data, and sales prospecting or lead generation, requires our written agreement." | No. Also incorporates general [Terms and Conditions](https://www.adzuna.co.uk/terms-and-conditions.html), which returned 403, so not verified. Ongoing use may need a paid plan |
| [Greenhouse](https://docs.greenhouse.io/job-board.html) | No auth for GET. Free. Per-employer token | None published | "Job Board data is publicly available, so authentication is not required for any GET endpoints." The [legal page](https://www.greenhouse.com/legal) lists a customer MSA and no developer or website terms | No. MSA only keyword-searched, and it binds customers. Each employer's own terms not checked |
| [Ashby](https://developers.ashbyhq.com/docs/public-job-posting-api) | No auth described. Per-employer name | None published | Docs describe customers populating their own careers page (read through a fetch tool, so not quoted). [Terms](https://www.ashbyhq.com/terms) are "by and between Ashby, Inc. [...] and the corporation, LLC, partnership, sole proprietorship, or other business entity entering into this Agreement" | No |
| [Lever](https://github.com/lever/postings-api) | No auth described for GET. Per-employer name | Published only for application POSTs | Docs: "These jobs may be scraped by third parties." This warns customers and is not a licence. [Terms](https://www.lever.co/terms-of-service/) "govern a customer's acquisition and use" | No |
| [Workable](https://help.workable.com/hc/en-us/articles/115012771647) | Public endpoints shown without auth, in a guide to your own careers page | None published | [Terms](https://www.workable.com/terms) are for customers. Their AI clauses cover Workable's own features | No |
| [Recruitee](https://docs.recruitee.com/reference/offers) | No auth on the careers-site endpoint. Per-employer subdomain | None published | [Tellent terms](https://tellent.com/terms-and-conditions) are keyword-searched only and address subscribers | No |
| [Remote OK](https://remoteok.com/api) | No key. Free | None published | In the API response: "Please link back (with follow, and without nofollow!) to the URL on Remote OK and mention Remote OK as a source [...] If you do not we'll have to suspend API access." [Terms](https://remoteok.com/legal) keyword search found nothing on scraping or API use | No. A private self-hosted tool has no public site to carry a followed link, so this condition may be impossible to meet |
| [Reed](https://www.reed.co.uk/developers/jobseeker) | Key. Price not stated | 100 results a request | [Site terms](https://www.reed.co.uk/terms-and-conditions): "You may copy material on the Website for your own private or domestic purposes, but no copying for any commercial or business use is permitted." API-specific terms not found | No. UK only |
| [Guru](https://www.guru.com/terms-of-service) | No API found | n/a | Keyword search found no scraping ban, only a bar on software "intended to damage or interfere" | No. No documented route, so unusable in practice |

## RISK: wording could bar this use

| Source | Access and cost | Wording that matters | LLM addressed? |
|---|---|---|---|
| [Himalayas](https://himalayas.app/terms) | No key; free key available; 60 requests a minute without one | "Do not pass them on to third parties, such as other job boards, aggregators, job search engines, Google Jobs or LinkedIn Jobs" and "Show the jobs only on sites and apps you operate." | Partly. [Docs](https://himalayas.app/docs/remote-jobs-api) say the API is for "AI tools", and clause 30A allows an AI "Personal Agent", but only as an exception to clauses 30 and 93. Clause 113(c) still reads onto an LLM provider. **The closest call in this table, and a one-line email could settle it** |
| [Remotive](https://remotive.com/terms-of-use) | No key; free; max 4 fetches a day advised | "Copy, reproduce, redistribute, publish, or make available to any third party any job listings" and, in the [API notes](https://github.com/remotive-com/remote-jobs-api), "Please do not submit Remotive jobs to third Party websites" | Only Remotive's own integrations (section 2e) |
| [We Work Remotely](https://weworkremotely.com/api-terms-and-guidelines) | Token-based API, 1,000 requests a day; public [RSS](https://weworkremotely.com/remote-job-rss-feed) | "do not use the API, or any We Work Remotely data, to build the following: [...] A job advertising or job search service"; "Scraping, copying, saving, or storing our data is strictly prohibited". The RSS page says "Anyone can use the feed", but the "any We Work Remotely data" wording reaches it | No |
| [The Muse](https://www.themuse.com/developers/api/v2/terms) | Registered key; 3,600 requests an hour, 500 without | Licence is "solely" for listed purposes, including "to the extent needed to format and display Muse Content through the Apps"; you will not "copy, alter or create derivative works of the API or Platform" or "clone Muse Content" | No |
| [Arbeitnow](https://www.arbeitnow.com/terms) | No key; free | "personal, non-commercial transitory viewing only"; you may not "modify or copy the materials" or "transfer the materials to another person". Section 11 adds a link-back duty for the API without lifting these | No |
| [Hacker News](https://github.com/HackerNews/API) | No key; repo is MIT; "currently no rate limit" | [YC terms](https://www.ycombinator.com/legal/): "you agree not to modify, copy, frame, scrape, rent, lease, loan, sell, distribute or create derivative works"; "you will not engage in or use any data mining, robots, scraping or similar data gathering or extraction methods". The MIT licence covers the repo, not the comments | No |
| [Foorilla](https://foorilla.com/terms/) | [API page](https://foorilla.com/api/) unreadable | "Use automation, bots, or scrapers without permission"; "You may not copy, modify, redistribute, or commercially exploit any material" | No |
| [Jooble](https://jooble.org/info/terms) | Key by form; [API page](https://jooble.org/api/about) returned 403 | "You may not use any web spiders, bots, indexers, robots, crawlers, harvesters, or any other automatic process"; API terms not verified | No |
| [JSearch](https://www.openwebninja.com/terms) | Key; [200 requests a month free, $25 for 10,000](https://www.openwebninja.com/api/jsearch) | "You are solely responsible for ensuring that your use [...] complies with [...] any terms that apply to the original source of such data". It serves LinkedIn and Indeed listings, so it fails for the same reason as JobsPipe | No |
| Remotewx ([README](https://github.com/remotewx/api)) | Free | "Please do not submit our jobs to third Party websites"; "Our free API is only dedicated to indie developers" | No |
| [SmartRecruiters](https://www.smartrecruiters.com/legal/terms-of-use/) | [Posting API docs](https://developers.smartrecruiters.com/docs/posting-api) describe keys; the unauthenticated route was not verified | Candidate terms bar you to "Use automatic means to access content or data from other users;". Whether postings count as such is unclear | No |
| [Bundesagentur für Arbeit](https://github.com/bundesAPI/jobsuche-api) (Germany) | Community docs with a shared client ID | The community docs state that the agency offers no official API: "bietet die Bundesagentur für Arbeit dafür bis heute keine offizielle API an". Agency terms not read | No |

### Freelance marketplaces and networks in RISK

All have no documented job API that I could find, and terms that bar automated reading.

| Source | Wording |
|---|---|
| [Contra](https://contra.com/terms) | Bars access "using any engine, software, tool, agent, device or mechanism (including spiders, robots, crawlers, data mining tools or the like)" other than Contra's or ordinary browsers and search engines |
| [Toptal](https://www.toptal.com/tos) | "You agree not to access the Site or Content by any means other than through the interface that is provided by Toptal" |
| [PeoplePerHour](https://www.peopleperhour.com/static/terms-of-website-use) | "harvest or scrape any Content from the services" is barred |
| [Workana](https://www.workana.com/en/terms) | "Utilizar un robot, araña web, procesos manuales y/o automáticos o dispositivos para realizar minería de datos" is barred |
| [Arc.dev](https://arc.dev/terms) | You will not "duplicate, license, sublicense, publish, broadcast, transmit, distribute, perform, display, sell, rebrand, or otherwise transfer information from the Platform" |
| [Algora](https://algora.io/terms) | Bars "any robot, spider, or other automatic device, process, or means to access Service for any purpose" |

Scrapers sold for freelancermap and Workana exist on Apify. They are not a permitted route.

## Contract work through CLEAR sources

One sample on 2026-11-01, using the sources' own fields:

- **Jobicy:** 7 of 100 listings had `jobType` Contract. Its filter also offers Freelance and Contract options.
- **4dayweek:** 7 of 100 listings had `contract_type` contract, out of 28,523 total.

These are contract jobs, not marketplace gigs, and the volume is small.

## Ranked lists

Ranked by fit for a global remote job search, then by how directly the terms speak to this use.

**CLEAR**

1. Jobicy
2. 4dayweek.io, noting the job-description carve-out
3. Arbetsförmedlingen, for Sweden
4. USAJOBS, for US federal roles
5. Canada Job Bank, as historical data only

**SILENT, not safe**

1. Greenhouse, Ashby and Lever: best fit, and written confirmation would be needed to meet the owner's rule
2. Adzuna: express personal-job-search grant, general terms unread
3. NAV Norway
4. Workable, Recruitee
5. Reed
6. Remote OK: link condition may be impossible
7. Guru: no route exists

**RISK**

Listed from closest call to clearest bar:

1. Himalayas
2. SmartRecruiters
3. Bundesagentur für Arbeit: no official grant
4. The Muse
5. Remotive, We Work Remotely, Arbeitnow, Hacker News, Foorilla, Jooble, Remotewx
6. JSearch
7. Contra, Toptal, PeoplePerHour, Workana, Arc.dev, Algora

## Consequences for the decision

- **Strict reading of the owner's rule:** v1 ships Jobicy and 4dayweek, plus USAJOBS or Arbetsförmedlingen if the user's market fits. That is a thin set, with no employer watchlist.
- **The largest gain is a decision on the ATS APIs.** Greenhouse, Ashby and Lever are direct employer sources, but no document grants what the owner's rule asks for. Asking each vendor in writing is the only way to move them to CLEAR.
- **Worth one email each:** Himalayas, on whether an LLM provider acting for the user counts as a third party, and Adzuna, for the general terms and whether long-term use fits the free tier.
- **Adapter rules for CLEAR sources:** credit and link per source, keep Jobicy Apply links on Jobicy, poll Jobicy at most hourly, and be able to delete 4dayweek copies within 30 days.

## Not verified

No verdict is given for these:

- **Pages blocked or errored (403, 429):** Adzuna general terms, Jooble API page, CareerOneStop API and terms, Malt terms, freelancermap API, Truelancer terms, Personio terms.
- **No readable text returned:** Teamtailor API docs, France Travail API and terms, Get on Board API docs, Fiverr terms (shell page only), Contra's developer page.
- **Sign-in wall:** Findwork developer docs. Its terms URL returned 404.
- **Terms not found at the URLs tried (404), or no API confirmed:**
  - Authentic Jobs: `/api/` returned 404, and `/feed/` showed blog posts. Its terms had no scraping clause on keyword search.
  - EURES: its legal notice says "Re-use is authorised, provided that ELA is acknowledged as the source of the material", but I found no public job API.
  - Working Nomads: an undocumented endpoint answers, but no terms were found.
  - Careerjet: its API is for publisher accounts, and its terms were not found.
  - Others with terms not found: Hubstaff Talent, Gun.io, Superteam Earn, Finland's Työmarkkinatori.
  - Twine: its terms page had no relevant wording, and no API was found.
- **Upwork, Freelancer.com, Indeed, LinkedIn and JobsPipe** were excluded by the owner and not re-checked.
- **Failed searches are not proof.** "No API found" means my searches and the URLs I tried found none.
- **Keyword searches:** long terms were searched for scraping, automation, API and AI wording rather than read end to end, except where quoted in full context. A restriction using other words could be missed.
- **Rate limits:** "none published" means I found none, not that none are enforced.
- **Samples:** the live counts come from one call each.
