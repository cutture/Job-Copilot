# Job sources: Pune, India and regional gaps

Research for ticket #7, "Decide: sources for v1". Follows [job-sources-alternatives.md](https://github.com/cutture/Job-Copilot/blob/research/job-sources-alternatives/research/job-sources-alternatives.md). Checked 2026-11-01. Terms change, so re-read them before building an adapter. This is a reading of published terms, not legal advice.

## Answer

- **No source is CLEAR for Pune office jobs.** The only sources that pass are SILENT: the employer boards, and Adzuna if a keyed call confirms its India API.
- **No Indian job board passes.** Naukri, foundit, Shine, Instahyre, Hirist, iimjobs, Cutshort and Internshala all have wording that could bar this use, and I found no job-seeker API from any of them.
- **Employer boards can filter Pune roles,** but the location is in different fields on each platform, so an adapter must check several. Ashby is the easy one to get wrong: `location` can say "India" with Pune only in the address.
- **The watchlist is the real work.** These boards only cover employers you name. I found some with Pune roles (below), but no API lists them all.
- **No new official source passes for Australia or South East Asia.** SEEK and JobStreet are RISK. I found no official public EURES API.

## Verdicts

- **CLEAR:** terms expressly permit this use.
- **SILENT:** nothing found bars it. This does not mean safe.
- **RISK:** wording could bar it, so it is excluded.
- **Not verified:** the page could not be read, so no verdict is given.

The use tested is the whole one: a self-hosted tool fetches postings for one person and sends the text to a third-party LLM provider. A person submits by hand.

Quotes come from downloaded page text. Long terms were keyword-searched for automation, API, reuse and AI wording, not read end to end, so a restriction in other words could be missed. "No API found" means my searches and the URLs I tried found none.

## 1. Office jobs in Pune or India

### Passing

| Source | Access and cost | Limits | Wording that matters | Verdict |
|---|---|---|---|---|
| Greenhouse, Ashby, Lever, Workable, Recruitee boards | No key for reads, free, one board per employer | None published | See [earlier findings](https://github.com/cutture/Job-Copilot/blob/research/job-sources-alternatives/research/job-sources-alternatives.md). No terms aimed at third-party readers | SILENT |
| [Adzuna](https://developer.adzuna.com/docs/terms_of_service) | Free key at once, no payment details. Paid plans for higher personal volume | Shown in the account. Free tier "intended for evaluating the API" | See below | SILENT, India API unconfirmed |

### Adzuna in detail

**General terms now read, from archived copies only.** The live pages for [UK](https://www.adzuna.co.uk/terms-and-conditions.html) and [India](https://www.adzuna.in/terms-and-conditions.html) still return 403. I read Internet Archive captures from [2 October 2026](https://web.archive.org/web/20261002191352/https://www.adzuna.co.uk/terms-and-conditions.html) and [16 October 2026](https://web.archive.org/web/20261016040539/https://www.adzuna.in/terms-and-conditions.html). Confirm against the live page by hand.

- The API terms grant the use: "The Adzuna API may be used for: Personal job search".
- The General Terms section has no scraping, automation or AI clause. The scraping wording elsewhere in the document is in the Partner Terms and an email-harvesting rule, which do not read onto this use.
- **The closest wording:** "This website contains material which is owned by or licensed to us. This material includes, but is not limited to, the design, layout, look, appearance and graphics. Reproduction is prohibited other than in accordance with the copyright notice". I could not find that notice on the page. I read this as being about the website rather than API results, because the API terms say users "are encouraged to publish Adzuna listings". **This is a judgement call for the owner.** Neither document mentions an LLM provider.
- **Clause to ask about:** "An API user agrees to direct all queries via Adzuna. Any attempt to contact a third party, even where they provide listings content, will be considered a breach". It sits under Confidentiality and does not mention applying for a job. Whether applying to an employer found through Adzuna could be caught is unclear.
- **Other conditions:** on termination, "immediately remove all insertion codes and data acquired from Adzuna from all pages of its web sites". Multiple accounts count as misuse.

**India coverage, partly confirmed:**

- [adzuna.in](https://web.archive.org/web/20261015044029/https://www.adzuna.in/) exists and advertises "500,000+" jobs. A [January 2026 capture](https://web.archive.org/web/20260102072714/https://www.adzuna.in/pune) showed 13,953 Pune jobs. These are archived site counts, not API counts.
- **Official docs do not list API countries.** [Search docs](https://developer.adzuna.com/docs/search) show only the UK example. A [third-party client](https://glama.ai/mcp/servers/@folathecoder/adzuna-job-search-mcp/blob/2a1dccf28f89db8e9b261456bd103b5108fd6ded/server.py) lists `in`.
- A keyless call returned HTTP 400 for `in`, `gb` and an invalid `zz`, so it proves nothing. One call with a free key would settle it.
- **Fit limit:** "we currently only provide a snipped of the job description in the response". The LLM would score a snippet, and the full posting sits behind a link the tool must not scrape.

### Excluded or unverified

| Source | Access and cost | Wording that matters | Verdict |
|---|---|---|---|
| [Naukri](https://www.naukri.com/termsconditions) | No job-seeker API found | [January 2025 capture](https://web.archive.org/web/20250119170343/https://www.naukri.com/termsconditions): "Extracting data from Naukri.com using any automated process such as spiders, crawlers etc. or through any manual process for a purpose which has not been authorised in writing." The live page could not be read | RISK, from archive |
| [foundit](https://www.foundit.in/info/terms-of-use) | No API found | "copying, misusing, transmitting or crawling any data [...] for any Purpose other than that being a bonafide Purpose"; "limited license to access and make personal use" | RISK |
| [Shine](https://www.shine.com/termsandconditions) | No API found | "Automated harvesting (crawling, scraping, spidering, bulk download, data extraction) is prohibited without our prior written consent." | RISK |
| [Instahyre](https://www.instahyre.com/terms/) | No API found | [January 2026 capture](https://web.archive.org/web/20260102230548/https://www.instahyre.com/terms/): "access, navigate, search, copy, monitor, download, harvest or scrape or otherwise extract in any manner, any Content". Live page returned 403 | RISK, from archive |
| [Hirist](https://www.hirist.tech/terms) | No API found | "Using content from hirist.tech for derivative works with a commercial motive without prior written consent [...] is strictly prohibited."; "uses technological means to exclude Robots etc from crawling the website" | RISK |
| [iimjobs](https://www.iimjobs.com/terms) | No API found | "iimjobs.com uses technological means to exclude Robots etc from crawling the website and scraping content." | RISK |
| [Cutshort](https://cutshort.io/terms) | API exists, for hiring customers | "API and MCP access may be used by the customer for its own genuine hiring requirements"; "You may not use any automated process or service to access and/or use the Service" | RISK |
| [Internshala](https://internshala.com/terms/) | No API found | "You are expressly prohibited from using automated systems, software, bots, spiders, scripts, or manual processes to access, extract, scrape, crawl, data mine, reproduce, redistribute, or copy any content [...] for purposes including but not limited to, developing, training, fine-tuning, validating, or enhancing machine learning models, large language models (LLMs)". Aimed at building AI, but "not limited to" leaves it open | RISK |
| [Hasjob](https://hasjob.co/feed) (Hasgeek) | Official Atom feed, free, no key. One read returned 18 entries, with Pune on 4 lines of text | [Hasgeek terms](https://hasgeek.com/about/policy/terms) bar use "to spam, phish, pharm, pretext, spider, crawl, or scrape". Hasjob invites people to "Subscribe to the feed", and I found no feed terms (`hasjob.co/terms` returned 404). The closest call in this table | RISK |
| [Careerjet](https://www.careerjet.com/partners/api/) | Publisher key. Cost not stated | "Each publisher website requires a unique API key"; `user_ip` and `user_agent` of the triggering user are required. [Publisher page](https://www.careerjet.com/partners/publishers): "Monetize your web traffic", which a private tool has none of. Publisher terms not found | Not verified, poor fit |
| [TimesJobs](https://www.timesjobs.com/) | No API found | Three guessed terms URLs returned 404, and the homepage returned no readable text | Not verified |
| [National Career Service](https://www.ncs.gov.in/) | No public API found | `/terms&condition`, `/disclaimer` and `/sitemap` all returned the homepage, which says "Website contents are managed by Ministry of Labour & Employment, Government of India." Terms unread | Not verified |
| [data.gov.in](https://www.data.gov.in/catalog/national-career-service-ncs) | Open data portal | The NCS catalogue page reads "No Result Found...". No postings dataset found | No source found |

No Wellfound-free alternative passes. Those I found are in the table: Instahyre, Cutshort and Hasjob.

## 2. Filtering Pune roles on employer boards

**Yes, all five expose usable fields.** One read-only call per board on 2026-11-01. Pune was seen in real data on four platforms. Workable's fields look right, but neither sampled board had a Pune role.

| Platform | Boards sampled | Fields | What I saw | Filter rule |
|---|---|---|---|---|
| Greenhouse | [SonicWall](https://boards-api.greenhouse.io/v1/boards/sonicwall/jobs), [Showpad](https://boards-api.greenhouse.io/v1/boards/showpad/jobs?content=true) | `location.name`. `offices[]` only with `content=true`. No workplace field seen | SonicWall: 20 of 48 Pune, as "Pune, Maharashtra, India", a trailing-space variant and "... - Remote". Showpad: 6 of 23 as bare "Pune" | Case-insensitive match, trimmed. Treat "Remote" in the text as remote |
| Lever | [Entrata](https://api.lever.co/v0/postings/entrata?mode=json), [Mindtickle](https://api.lever.co/v0/postings/mindtickle?mode=json) | `categories.location`, `categories.allLocations`, `country`, `workplaceType` | Entrata: 3 of 28 Pune, one each hybrid, onsite and remote. Mindtickle: 16 of 19 had Pune in one of the two fields, and some of those had Bengaluru as `location` | **Check `allLocations` too.** The cleanest of the five, because of `workplaceType` |
| Ashby | [Blitzy](https://api.ashbyhq.com/posting-api/job-board/blitzy), [Sardine](https://api.ashbyhq.com/posting-api/job-board/sardine) | `location`, `secondaryLocations`, `address.postalAddress`, `isRemote`, `workplaceType` | Blitzy: 5 of 38 Pune. The one inspected had `location` "India", Pune only in `addressLocality`, and `workplaceType` OnSite. Sardine: 1 role had Pune only in the description | **Check the address too.** City-limited remote roles may appear only in the text, so let the LLM catch those |
| Workable | [Tiger Analytics](https://apply.workable.com/api/v1/widget/accounts/tiger-analytics?details=true), [Vestd](https://apply.workable.com/api/v1/widget/accounts/vestd?details=true) | `city`, `state`, `country`, `locations[].countryCode`, `telecommuting` | Tiger: 4 of 245 India, and the one inspected had an empty `city`. No Pune seen. Vestd: 0 of 2 | Keep India rows with no city for review. **Pune matching unproven** |
| Recruitee | [Gusti Leder](https://gustileder.recruitee.com/api/offers/), [Metyis](https://metyisag.recruitee.com/api/offers/) | `city`, `state_name`, `country_code`, `locations[]`, `on_site`, `hybrid`, `remote` | Gusti Leder: 1 Pune, 6 `IN` of 75. Metyis: 0 Pune, 7 `IN` of 71. `country` is localised ("Indien") | Use `country_code`, never `country`. Check `locations[]` |

Employers with Pune roles, as a starting watchlist. Fit for the owner's roles was not assessed:

- **Seen in the samples above:** SonicWall, Showpad, Entrata, Mindtickle, Blitzy, Gusti Leder.
- **Search results only, possibly stale:** Zocdoc, Zinnia, Energy Exemplar, Madison Logic, Lynx Analytics, Goken, Brillio, Kingfish Group, Hevo Data.

Large Pune employers can use their own sites, such as [Citi](https://jobs.citi.com/location/pune-jobs/287/1269750-1264418-1259229/4). Those are outside these APIs, and I read no terms for them.

## 3. Australia, South East Asia, Europe and Canada

| Source | Region | Access and cost | Wording that matters | Verdict |
|---|---|---|---|---|
| [SEEK](https://au.seek.com/terms) and [SEEK API](https://developer.seek.com/introduction) | Australia, NZ | API by integration request, for recruitment software. Cost not stated | "This documentation is targeted at developers integrating their recruitment software with SEEK."; "you must not use, or assist anyone to use, any automated process, script, tool, bot, scraper" except through an interface provided "for such use" | RISK, no job-seeker API |
| [JobStreet](https://my.jobstreet.com/terms) | Malaysia, Indonesia, Philippines and others | Same SEEK API | "You may not use data mining, robots, screen scraping, or similar automated data gathering, extraction or publication tools" and the same automated-access clause | RISK, no job-seeker API |
| [EURES](https://eures.europa.eu/eures-legal-notice_en) | Europe | No official public API found. Third-party scraper listings describe an endpoint, which is not a documented route | "Re-use is authorised, provided that ELA is acknowledged as the source of the material." Individual documents may carry "specific conditions" | No permitted route found |
| [Workforce Australia](https://www.workforceaustralia.gov.au/individuals/coaching/how-to/about/terms) | Australia | No API found | CC BY 4.0, "Except where otherwise indicated: content supplied by third parties". Job ads may count as third-party content | No permitted route found |
| [data.gov.au](https://data.gov.au/data/dataset?q=job+vacancies) | Australia | Open data search lists an Internet Vacancy Index | An index rather than postings, going by its name. Licence not read | Not verified, likely not useful |
| [MyCareersFuture](https://www.mycareersfuture.gov.sg/terms-of-use) | Singapore | No official API docs found. A [third-party project](https://glama.ai/mcp/servers/@gabrielchua/mcf-mcp/blob/592e676aef1aee8cacbbd2c3fccd8c26c2944b70/mycareersfuture_server_python/main.py) calls an endpoint | Terms page returned no readable text | Not verified |
| [France Travail](https://francetravail.io/data/api/offres-emploi) | France | API portal page | Page returned no readable text | Not verified |
| [APSJobs](https://www.apsjobs.gov.au/s/terms-and-conditions) | Australian government roles | No API found | Page returned no readable text | Not verified |

Canada adds nothing new. Job Bank remains CLEAR but holds monthly past postings, per the earlier findings.

## What passes per region

Regional volume was not measured, so this shows only which sources are allowed. Adzuna countries come from its site selector, not API docs: UK, Australia, Austria, Belgium, Brazil, Canada, France, Germany, India, Italy, Mexico, Netherlands, New Zealand, Poland, Singapore, South Africa, Spain, Switzerland, US.

| Region | CLEAR | SILENT |
|---|---|---|
| Pune office | None | Employer boards, Adzuna |
| Remote, India | Jobicy, 4dayweek | Employer boards, Adzuna |
| Remote, Europe | Jobicy, 4dayweek, Arbetsförmedlingen (Sweden) | Employer boards, Adzuna, NAV (Norway), Reed (UK) |
| Remote, Australia | Jobicy, 4dayweek | Employer boards, Adzuna |
| Remote, USA | Jobicy, 4dayweek, USAJOBS (federal only) | Employer boards, Adzuna |
| Remote, Canada | Jobicy, 4dayweek, Job Bank (past postings, poor fit) | Employer boards, Adzuna |
| Remote, South East Asia | Jobicy, 4dayweek | Employer boards, Adzuna (Singapore site only) |
| Remote, worldwide | Jobicy, 4dayweek | Employer boards |

- **Adzuna:** API support per country was not confirmed, and every row rests on the same API terms.
- **Language:** not tested. Arbetsförmedlingen and NAV are national services, so English coverage may be low.
- **Every source:** posting text usually belongs to the employer, so an aggregator can only license what it holds. 4dayweek says so outright.

## Worth one email or one call

1. **Adzuna:** make one keyed call to `/jobs/in/search/1` with `where=Pune`. Then ask about sending snippets to an LLM provider, the "contact a third party" clause, and long-term use on the free tier.
2. **Greenhouse, Ashby, Lever:** written confirmation is the only way to move them from SILENT to CLEAR.
3. **Hasgeek:** ask whether polling the Hasjob feed counts as crawling.

## Not verified

- **Adzuna:** live general terms (archived copies read), the copyright notice, API support for `in`, and free-tier size.
- **Naukri and Instahyre:** live terms unreadable, so these verdicts rest on captures from January 2025 and January 2026.
- **Unreadable:** TimesJobs, National Career Service, MyCareersFuture, France Travail and APSJobs. Internet Archive lookups for the first three found nothing or were temporarily offline.
- **Careerjet:** publisher terms not found.
- **Workable:** no Pune role seen, so matching is unproven on real data.
- **Probes:** single calls on one day. Counts will change, and Pune was matched by substring, not checked by hand.
- **Employers:** each employer's own site terms were not read.
