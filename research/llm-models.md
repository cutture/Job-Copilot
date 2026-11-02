# LLM models and costs

Answers [#3](https://github.com/cutture/Job-Copilot/issues/3). Sources were read on 2026-11-01. Prices and limits change often, so recheck them before relying on them.

## Short answer

- **Strength is unproven.** I found no benchmark for job-posting filtering or Application Packs, and ran no model. The candidates below are a shortlist for the DeepEval runs, not a ranking.
- **Filtering Job Postings:** evaluate Groq's free `gpt-oss` models, the Gemini free tier and Jev. Gemini free may train on what it receives and warns against sending personal data, so it could get posting text only. Jev isn't free, but costs about $0.25 a month in the example below.
- **Application Packs and verification:** Gemini free fails the map's no-training rule. Groq free is the clearest free option. Mistral Free only qualifies after opting out. Paid fallbacks are cheap: $10 buys about 6,250 packs on Claude Haiku 5.5 or about 310 on Claude Sonnet 5.5, using the assumptions below.
- **Claude subscription:** it does not simply cover API calls from a self-built app, which should use a Console API key. Max, Ultra and Team include monthly API credits that work with such a key. Free, Pro and Enterprise don't.
- **Jev:** it exists and is in early access. It fits scoring, classification and support checks, but can't write Application Packs. Treat "pairs with Claude" as a usage pattern: the TypeSafe pages I read don't name Claude as a partner.

## Free options

| Provider | Published free limits | Training on submitted data | Eligible for Application Packs under the map's rule? |
|---|---|---|---|
| **Gemini API**, free tier | Not published in the docs; [shown in AI Studio](https://ai.google.dev/gemini-api/docs/rate-limits). Flash and Flash-Lite models have a [free tier](https://ai.google.dev/gemini-api/docs/pricing). | **Yes.** [Terms](https://ai.google.dev/gemini-api/terms): content is used to improve products, humans may read it, and "Do not submit sensitive, confidential, or personal information". | **No** |
| **Groq** | [30 RPM, 1K RPD, 8K TPM, 200K TPD](https://console.groq.com/docs/rate-limits) for `openai/gpt-oss-120b` and `gpt-oss-20b`. **Plan unclear:** the page says the table shows Developer plan limits, and has a separate "Free Plan Limits" tab. | **No, unless the customer permits it.** [Services Agreement §4.2](https://console.groq.com/docs/legal/services-agreement). It doesn't name a free tier but covers anyone using the services. | **Yes, on production models.** Beta Services are treated differently (§3.6). Temporary logs may be [kept up to 30 days](https://console.groq.com/docs/your-data). |
| **Mistral**, Free mode | Numbers are [only in the Admin Panel](https://docs.mistral.ai/admin/billing-usage/usage-limits). | **Yes by default, with opt-out.** [Help center](https://help.mistral.ai/en/articles/347617-do-you-use-my-user-data-to-train-your-artificial-intelligence-models) and [opt-out control](https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training). The [inference page](https://mistral.ai/cloud/inference/) says API data isn't used for training, which conflicts. | **Only after opting out** and confirming the conflict with Mistral |
| **OpenRouter** `:free` models | [20 RPM; 50 per day, or 1,000 per day after buying at least 10 credits](https://openrouter.ai/docs/api/reference/limits). | **Depends on the provider.** [Separate settings for free and paid models](https://openrouter.ai/docs/guides/privacy/provider-logging) can exclude providers that train. | **Per provider, unverified.** The `data_policy` field was empty for the three endpoints I sampled. |

At an assumed 1,050 tokens per posting, Groq's 200K TPD allows about 190 postings a day, and 8K TPM about 7 a minute. That fits a daily batch.

## Low-cost paid options

Prices are per million tokens, standard tier.

| Model | Input | Output | Trains on API data? |
|---|---|---|---|
| [Jev 1.14](https://docs.typesafe.ai/models) (decisions only) | $0.042 | Free | [No](https://docs.typesafe.ai/models) |
| [gpt-5-nano](https://developers.openai.com/api/docs/pricing) | $0.05 | $0.40 | [No, unless you opt in](https://developers.openai.com/api/docs/guides/your-data) |
| [Claude Haiku 5.5](https://platform.claude.com/docs/en/about-claude/pricing) (prompts up to 100K tokens) | $0.10 | $0.50 | [No](https://www.anthropic.com/legal/commercial-terms) |
| [Gemini 2.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/pricing) | $0.10 | $0.40 | [No](https://ai.google.dev/gemini-api/docs/pricing) |
| [gpt-5-mini](https://developers.openai.com/api/docs/pricing) | $0.25 | $2.00 | [No, unless you opt in](https://developers.openai.com/api/docs/guides/your-data) |
| [Gemini 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/pricing) | $0.30 | $2.50 | [No](https://ai.google.dev/gemini-api/docs/pricing) |
| [Claude Sonnet 5.5](https://platform.claude.com/docs/en/about-claude/pricing) | $2.00 | $10.00 | [No](https://www.anthropic.com/legal/commercial-terms) |

Gemini paid logs are [kept for a limited time](https://ai.google.dev/gemini-api/terms) to detect policy violations. OpenAI abuse logs are [kept up to 30 days](https://developers.openai.com/api/docs/guides/your-data) by default.

### What the $10 cap buys

These are my own assumptions, not measurements. Replace them with token counts from real runs. [Claude 4.7 and later count about 30% more tokens](https://platform.claude.com/docs/en/about-claude/pricing) for the same text, so direct comparisons with Claude are slightly flattering to it here.

**Filtering:** 200 postings a day for 30 days, each 1,000 input and 50 output tokens.

| Model | Cost per month |
|---|---|
| Jev | $0.25 |
| gpt-5-nano | $0.42 |
| Gemini 2.5 Flash-Lite | $0.72 |
| Claude Haiku 5.5 | $0.75 |

**Application Pack plus verification:** 6,000 input and 2,000 output tokens in total.

| Model | Cost per pack | Packs for $10 |
|---|---|---|
| Gemini 2.5 Flash-Lite | $0.0014 | about 7,100 |
| Claude Haiku 5.5 | $0.0016 | about 6,250 |
| gpt-5-mini | $0.0055 | about 1,800 |
| Gemini 3.5 Flash-Lite | $0.0068 | about 1,470 |
| Claude Sonnet 5.5 | $0.032 | about 310 |

The cap isn't a tight constraint at these volumes, so model quality should drive the choice. Anthropic also supports a [self-set spend limit](https://platform.claude.com/docs/en/api/rate-limits), which returns HTTP 400 with `invalid_request_error` when reached. The fallback to free models can key off that.

## Reliability

No provider's evidence here predicts how the free tiers will behave under this project's load. Log 429s and failures from the first slice.

| Provider | What I found |
|---|---|
| Groq | [Status page](https://groqstatus.com/), self-reported, Aug to Nov 2026: API 100%, preview models 99.98%, no current incidents. It doesn't report free-plan throttling. |
| OpenRouter | [Public API](https://openrouter.ai/api/v1/models), one sample: 14 of 452 models were `:free`. One-day uptime was 99.93% to 100% on three sampled endpoints. [Free listings can end](https://openrouter.ai/models?max_price=0): one is marked as going away on November 30, 2026. |
| Claude API | [Status page](https://status.claude.com/) showed Operational. I couldn't retrieve an uptime figure. |
| Gemini API | Unverified. I found only [older Vertex incident history](https://status.cloud.google.com/products/Z0FZJAMvEB4j3NbCJs6B/history), which is a different surface from the free Gemini API. |
| Jev | No uptime data found. It's in [early access](https://typesafe.ai/), and the docs give [no deprecation schedule](https://docs.typesafe.ai/models). |

## Does a Claude subscription cover API calls?

Not as a general rule.

- **Billing:** ["the Claude API is billed separately"](https://support.claude.com/en/articles/9876003-i-have-a-paid-claude-subscription-pro-max-team-or-enterprise-plans-why-do-i-have-to-pay-separately-to-use-the-claude-api-and-console) from a paid chat subscription.
- **Authentication:** developers building products, including with the Agent SDK, [should use API key authentication](https://code.claude.com/docs/en/legal-and-compliance). Offering Claude.ai login in an app, or routing users' requests through plan credentials, isn't permitted. This also rules out subscription login for the later hosted version.
- **Monthly API credits:** [Max gets $100, Ultra $200, and Team $20 per Standard seat and $100 per Premium seat, pooled and capped at $500](https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-ultra-and-team-plans). Credits must be claimed by linking a Console organization, and they expire each billing cycle. Free, Pro and Enterprise aren't eligible.
- **For this project:** the map's direct API key design fits these rules. On an eligible plan, the credits could exceed the $10 cap. Check the plan's current credits, and don't assume they'll cover a hosted version for other users.

## What Jev is

**Confirmed from TypeSafe's own pages:**

- Jev is TypeSafe's [flagship and first System One model](https://docs.typesafe.ai/introduction). It takes state and typed questions and returns [typed answers with probabilities](https://docs.typesafe.ai/concepts/system-one), rather than generated text.
- It's offered [in early access](https://typesafe.ai/) through a [console-issued API key](https://docs.typesafe.ai/introduction/quickstart.md).
- [`jev-1.14.0` is the newest release](https://docs.typesafe.ai/models). The context limit is 64K tokens per request and 32K per question. A long-context header raises this to 262K, but requests are slower and less accurate.
- Output tokens are free. [Rate limits are per organization and shown in the console](https://docs.typesafe.ai/models).
- ["Jev is not trained on customer requests or responses."](https://help.typesafe.ai/articles/5974925716-how-is-submitted-data-used-or-retained) The [privacy policy](https://typesafe.ai/legal/privacy-policy) agrees. However, telemetry may be used to improve services, no fixed retention period is given, and [zero data retention is for enterprise customers](https://docs.typesafe.ai/legal).

**The Claude pairing:** System One pages mention [escalating to a person or a reasoning model](https://docs.typesafe.ai/concepts/system-one) without naming one. The pairing appears in third-party material I saw only as search snippets, such as [Pulumi's router](https://www.pulumi.com/blog/route-every-claude-code-message-to-the-right-model-with-jev/) and a [Towards Data Science walkthrough](https://towardsdatascience.com/how-to-build-a-cheap-yet-reliable-model-router-with-jev/).

**Fit with this project's steps:**

| Step | Fit | Why |
|---|---|---|
| Filter Job Postings, score Matches | Worth evaluating | TypeSafe lists [recruiting](https://docs.typesafe.ai/concepts/use-case-map.md), including matching candidates to roles. Choice and Score map well. |
| Link and classify Replies | Worth evaluating | No listed use case covers email replies. Support ticket and inbound message classification are the closest. |
| Verify claims against Evidence | Partial, as one layer | The [citation check cookbook](https://docs.typesafe.ai/cookbooks/citation_check.md) pairs string matching with Jev and sends low confidence to a person. It tested only eight citations, on an older model. |
| Write Application Packs or Proposals | **No** | System One models [don't write replies or produce code](https://docs.typesafe.ai/concepts/system-one). An LLM is still needed. |

**Limits that matter here**, from the [jev-1.13 weaknesses page](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md). No equivalent page is listed for 1.14.

- **Numbers and dates are unreliable.** Check salary, years of experience, posting dates and deadlines in code.
- **Extraction is weak.** Extract with regex or a generative model, then let Jev choose.
- **Irrelevant text lowers accuracy.** Trim postings before sending them.
- **Injected instructions can shift answers.** Job Postings are untrusted input, so add adversarial cases to the evals.
- **It leans toward the first option in a Choice.** Test with options reordered.

**Integration:** the [OpenRouter guide](https://openrouter.ai/docs/guides/community/jev) documents `state` and `questions` requests, not chat `messages`. Expect a Jev-specific adapter beside LiteLLM. I didn't confirm whether LiteLLM supports Jev directly.

**Vendor claims:** the ["193.6x Faster, 444.6x Cheaper"](https://typesafe.ai/) and "Zero Hallucinations" claims are TypeSafe's own. The homepage doesn't name the comparison LLMs or describe the workflow, so don't rely on them. Calibration is [measured across groups of predictions](https://docs.typesafe.ai/concepts/system-one) and doesn't guarantee any single answer.

## Not verified

- **Quality:** no model was run on this project's tasks, and no key was used.
- **Jev access:** whether signup is self-serve or waitlisted. One third-party source says waitlisted, and TypeSafe's quick start doesn't say. I found no free credits.
- **Jev terms:** I read the privacy policy and support pages, but not the Master Customer Agreement or Data Processing Agreement. The privacy policy's "last updated" date also disagrees with the page metadata.
- **Jev 1.14 on OpenRouter:** [its page](https://openrouter.ai/typesafe/jev-1.14) returned 404 when fetched, though the guide above lists the ID. The public model list I checked showed only `typesafe/jev-router`.
- **Free limits:** the actual numbers for Gemini and Mistral need a signed-in console. Groq's plan labelling needs checking the same way.
- **Terms:** which Groq models count as Beta Services, and whether OpenRouter's free endpoints train on data.
- **Regional rules:** [Gemini restricts unpaid use in some regions](https://ai.google.dev/gemini-api/terms), including when serving users in the EEA, Switzerland or the UK. Check this before a hosted version.
- **Secondary sources:** some Jev write-ups were seen only in search results and aren't relied on for any claim above except where marked.

## Suggested next step

Run one small DeepEval set over the shortlist, then pick by results:

- **Filtering:** Groq `gpt-oss-20b` and `gpt-oss-120b`, Gemini free with posting text only, and Jev.
- **Application Packs and verification:** Groq `gpt-oss-120b`, Claude Haiku 5.5, Gemini 2.5 Flash-Lite paid, and Claude Sonnet 5.5, with string matching plus Jev as an optional verification layer.
