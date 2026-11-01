# Research: autofill on application forms

Ticket: #5. Checked 2026-11-01. Nothing was filled in or submitted, and no extension was run. "Observed" means a plain GET of one public page, which shows the initial HTML only and is a sample of one per vendor.

## Answer

- **A fill-only extension looks feasible on Greenhouse, Lever and Ashby.** All three have hosted forms on known hosts, so a content script can reach them, including inside employer-page embeds.
- **Build order: Greenhouse, then Lever, then Ashby.** Leave Workday, SmartRecruiters and Workable on copy buttons for now.
- **Bot checks are the main risk.** All three pages reference a bot-check service. Stay out of the check and leave Submit to the person. Whether fast filling lowers a person's score is unknown, and only a real-browser test can show it.
- **Terms:** the vendor terms I could read bind employers, not applicants, and none addresses an applicant's fill-only extension. That is silence, not permission. This is not legal advice.

## Comparison

| | Greenhouse | Lever | Ashby | Workday |
|---|---|---|---|---|
| Hosted form | `job-boards.greenhouse.io` | `jobs.lever.co/.../apply` | `jobs.ashbyhq.com/.../application` | Per-employer tenant, e.g. `*.myworkdayjobs.com` |
| Fields in initial HTML (observed) | Yes: 1 form, 22 inputs | Yes: 1 form, named fields | No: 0 forms, 0 inputs | Not checked on an apply page |
| Public question schema | Yes | No custom questions | Not confirmed | Not checked |
| Bot check | reCAPTCHA, email code | hCaptcha (observed) | Spam protection, reCAPTCHA key (observed) | Not checked |
| Employer embed | Iframe | Not checked | Iframe | Embed Mode exists |
| Account needed | Not for the sampled form | Not for the sampled form | Not for the sampled form | Employer can require one |

## Form structure

**Greenhouse**
- A public GET with `questions=true` returns the fields for a job. Types are `input_file`, `input_text`, `input_hidden`, `textarea`, `multi_value_single_select` and `multi_value_multi_select`. One question can span several fields, such as a resume upload or a pasted resume. Compliance and demographic questions come back separately. [Job Board API](https://docs.greenhouse.io/job-board.html)
- Observed on one GitLab job: `first_name`, `last_name`, `email` and `phone` are plain inputs with stable IDs. The resume is a visually hidden file input. At least one dropdown is a custom combobox (`select__input`) rather than a native `<select>`, so the schema type does not tell you the DOM control. [Sample form](https://job-boards.greenhouse.io/gitlab/jobs/8638232002)

**Lever**
- Observed: one server-rendered form with `resume`, `name`, `pronouns`, `email`, `phone` and `location` fields, plus custom answers named `cards[...]`. [Sample form](https://jobs.lever.co/spotify/2a55d6c9-c564-443a-be3e-a3851db5a93b/apply)
- The Postings API does not expose custom questions, so these must be read from the page. Lever recommends its hosted form as best practice for custom forms. [postings-api](https://github.com/lever/postings-api)

**Ashby**
- Observed: the initial HTML has no form or inputs, only embedded app data, so the form renders client-side. The extension must wait for it to appear. Field names were not seen. [Sample form](https://jobs.ashbyhq.com/ashby/7458d4e9-da2e-47bd-98cb-adfda43d42b2/application)
- The API's form definition has fields with a path such as `_systemfield_name`, a type and selectable values. It needs an authenticated key, which an applicant's extension will not have. [API reference](https://developers.ashbyhq.com/reference/applicationformsubmit)

**Others**
- **Workday:** employers can require a Candidate Home account for all applications. [Workday docs](https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/career-sites/gtv1538650489786.html) The one career page I sampled had no forms in its initial HTML. Its apply flow was not inspected.
- **SmartRecruiters:** has an Application API for building the process into another site, with screening questions fetched per job. [Docs](https://developers.smartrecruiters.com/docs/application-api-1) Its hosted form was not inspected.
- **Workable:** the only first-party source found was an old help article on its API. [Article](https://help.workable.com/hc/en-us/articles/115013356548-Workable-API-Documentation) Its form was not inspected.

## Obstacles

**Embedded frames**
- Greenhouse and Ashby both offer iframe embeds on employer sites. [Greenhouse](https://support.greenhouse.io/hc/en-us/articles/46365908766875) [Ashby](https://docs.ashbyhq.com/embedding-ashby-job-boards-in-an-external-careers-page)
- `all_frames` defaults to false, and when true each frame is checked against the URL rules on its own. [Chrome manifest docs](https://developer.chrome.com/docs/extensions/reference/manifest/content-scripts)
- My inference, not stated by Chrome and not tested: `all_frames: true` with matches on the vendor hosts reaches an embedded form with no permission on the employer's site.

**Custom forms**
- Employers can build their own forms on these APIs. [Greenhouse](https://docs.greenhouse.io/job-board.html) [Lever](https://github.com/lever/postings-api) Those pages sit on the employer's domain and will not match, so they fall back to copy buttons.

**Bot checks**
- **Greenhouse:** reCAPTCHA looks at activity such as mouse movement and typing patterns. Sensitivity is set per job board, and depending on score a person may have to enter an emailed code. [Greenhouse support](https://support.greenhouse.io/hc/en-us/articles/115005448066) The sampled page references reCAPTCHA Enterprise.
- **Lever:** the sampled page loads hCaptcha, and its script runs the check as part of the submit button flow. I found no Lever document describing this.
- **Ashby:** admins choose from four spam protection levels. Ashby warns that the stricter ones can cause real candidates problems submitting. Its signals are not published. [Ashby docs](https://docs.ashbyhq.com/job-board-application-spam-protection)
- **Scripted events are detectable:** events sent with `dispatchEvent()` have `isTrusted` set to false. [MDN](https://developer.mozilla.org/en-US/docs/Web/API/Event/isTrusted) I found nothing saying any of these vendors penalises that or penalises extensions.

**Filling controls**
- Content scripts share the page's DOM but run in an isolated world. [Chrome content scripts](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts) Plain inputs should be simple. Custom comboboxes and client-rendered forms will need event simulation, per vendor.
- Setting a file input from script is the least certain step. I could not confirm it from the HTML spec, so assume the person attaches the resume by hand until tested.

## Terms

| Source | Who it binds | Relevant content |
|---|---|---|
| [Greenhouse legal index](https://www.greenhouse.com/legal) | Customers; privacy documents for candidates | The index lists no website terms of use. The customer agreement was not read. |
| [Lever Terms of Service](https://www.lever.co/legal/terms-of-service) (updated 2023-08-25) | Customers | Candidates are not parties. No clause names bots or scraping. |
| [Ashby Terms](https://www.ashbyhq.com/resources/terms) | Customers | Applicants are not parties. Customers may not circumvent security features or overburden the service. |
| [Workday site terms](https://www.workday.com/en-us/legal/site-terms.html) | workday.com and pages that reference these terms | Bars data mining and robots for scraping. Does not mention career sites or applicants. |
| [Chrome Web Store policies](https://developer.chrome.com/docs/webstore/program-policies/policies) | The extension | See below. |

- Workday's [End User Agreement](https://www.workday.com/en-us/legal/end-user-agreement.html) bans automated scripts, but it defines its website as scoutrfp.com. It does not cover career sites.
- Chrome Web Store policy applies directly if the extension is published. It requires a single narrow purpose, only the data that purpose needs, a privacy policy, prominent disclosure and consent, and no obfuscated code. It also bars facilitating access by circumventing login restrictions, and sending messages for a user who cannot first confirm the content and recipients.
- Greenhouse's `boards.greenhouse.io/robots.txt` disallows `/embed/`, and `jobs.lever.co/robots.txt` reserves rights against AI training. Both address crawlers, not a person filling a form, but they matter if the app fetches or stores these pages server-side.

## Recommendations

1. **Greenhouse first:** real fields in the HTML and a public schema, so questions can be prepared before the page opens.
2. **Lever second:** a simple server-rendered form with readable field names. Custom questions come from the page.
3. **Ashby third:** needs waiting for client rendering, and Ashby warns about false rejections at strict settings.
4. **Copy buttons for everything else:** Workday's accounts and per-employer tenants make it the costliest, despite being common at large employers.

Suggested guardrails for the extension:
- Never call submit or click the submit button.
- Never touch a captcha or emailed-code step.
- Fill only when the person clicks, and leave anything uncertain empty.
- Leave demographic and compliance questions for the person, since they are not Evidence-backed facts.
- Match only listed vendor hosts rather than all sites, and keep the Profile out of page-readable storage.

The order rests on form structure, not usage data. Market figures conflict and come from vendors with their own samples: one has [Workday at 29.4% and Greenhouse at 22% of 800 top employers](https://resumegeni.com/research/ats-market-share-2026), another has [Ashby at 15.6% and Greenhouse at 5.2% of 600+ recruiting teams](https://www.pin.com/blog/ats-market-share-report). I saw these only as search excerpts. Counting the ATS behind the postings the app actually finds would settle the order better.

## Could not verify

- How any form behaves with a real extension. Nothing was run in a browser, so filling, event handling, combobox behaviour and bot-check scores are all untested.
- Whether autofill affects bot-check scores or triggers email codes or rejections.
- Whether a script can set the resume file input.
- The content scripts' reach into cross-origin iframes, beyond the inference above.
- Field names and fields on other jobs and employers. Each vendor was sampled once, and employers configure their forms.
- Lever's use of hCaptcha on other employers' forms, and Lever's iframe mode for application forms.
- Hosted forms for Workday, SmartRecruiters and Workable.
- Greenhouse's customer agreement, the reCAPTCHA and hCaptcha terms, and any individual employer's career-site terms.
- Whether any vendor applies its terms to applicants' tools. A lawyer should confirm before a hosted or public release.
