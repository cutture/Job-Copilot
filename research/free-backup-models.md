# Free backup models

Answers [#13](https://github.com/cutture/Job-Copilot/issues/13) and builds on [`research/llm-models.md`](https://github.com/cutture/Job-Copilot/blob/research/llm-models/research/llm-models.md). Sources were read on 2026-11-02. No key was used, no account was created and no model was run. Limits and terms change often, so recheck them before relying on them. This is a reading of published terms, not legal advice.

## Short answer

- **Only two free tiers pass for personal data:** Groq production models and Cloudflare Workers AI. Both host `gpt-oss-120b`, so one prompt can serve both.
- **Groq `gpt-oss-120b` is confirmed, with conditions.** Keep it on production models and turn on Zero Data Retention (ZDR). The 30-day logs are not the default for every request, and they can be switched off.
- **Everything else is for posting text and evals at most.** That includes Gemini free, Mistral Free and OpenRouter `:free`. This reverses the earlier "Mistral after opting out" position, because its terms allow training unless you act and don't cover preview models.
- **Some names aren't free backups at all.** DeepSeek's API lists no free tier. OpenAI's free tokens need a positive balance and an opt-in to sharing data. GitHub Models was retired on July 30, 2026.
- **Qwen's free quota is a trial:** 90 days and about 1M tokens per model. The training terms are good, but it won't last as a backup.
- **Open-weight models:** the host's terms decide, not the model maker's. Qwen and DeepSeek weights on Cloudflare send nothing to Alibaba or DeepSeek.

## Comparison

"Eligible" means the published terms clearly rule out training on the data and cover this tier. Unclear means not eligible. "Personal data" here is only a reading of that rule.

| Provider and model | Free limits | Trains on submitted data | Retention and location | Verdict |
|---|---|---|---|---|
| **Groq** production: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, Llama 3.3 70B, Llama 3.1 8B ([list](https://console.groq.com/docs/models)) | [30 RPM, 1K RPD, 8K TPM, 200K TPD](https://console.groq.com/docs/rate-limits) for gpt-oss. Llama limits aren't in the table. | **No,** unless you permit it. [Agreement §4.2](https://console.groq.com/docs/legal/services-agreement) | [None by default; logs up to 30 days only for faults or suspected abuse; can be switched off](https://console.groq.com/docs/your-data). Stored in the US; [processing may be elsewhere](https://console.groq.com/docs/legal/customer-data-processing-addendum). | **Personal data,** with ZDR on |
| **Groq** preview: `qwen/qwen3.8-27b`, MiniMax M2.7, Muse Spark Open and others | Same table for Qwen3.8 | Unclear: §4.2 bars training, but Beta Services are not Cloud Services | Preview fits the [§3.6](https://console.groq.com/docs/legal/services-agreement) definition of Beta Services, where the DPA doesn't apply | **Posting text and evals only** |
| **Cloudflare Workers AI**, `@cf/` hosted models, including `@cf/openai/gpt-oss-120b` | [10,000 Neurons a day](https://developers.cloudflare.com/workers-ai/platform/pricing/), [300 RPM](https://developers.cloudflare.com/workers-ai/platform/limits/). Workers Free stops at the limit. | **No.** [Data usage page](https://developers.cloudflare.com/workers-ai/platform/privacy/) and [service terms](https://www.cloudflare.com/service-specific-terms-developer-platform/) | [Not kept after the response](https://developers.cloudflare.com/workers-ai/platform/privacy/) for plain inference, except legal duties. Metadata is kept. Location not stated. | **Personal data,** no AI Gateway logging |
| **Gemini API** free, including Flash, Flash-Lite and Gemma 4 | [Not published; shown in AI Studio](https://ai.google.dev/gemini-api/docs/rate-limits) | **Yes,** and [humans may read it](https://ai.google.dev/gemini-api/terms). [Pricing table](https://ai.google.dev/gemini-api/docs/pricing) agrees. | No general period stated. Google says not to send personal information. | **Posting text and evals only** |
| **Mistral** Free mode | [Only in the Admin Panel](https://docs.mistral.ai/admin/billing-usage/usage-limits) | **Yes by default,** [opt-out exists](https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training) | No period in the pages read. [Opt-out doesn't cover Labs or Preview models](https://legal.mistral.ai/terms/commercial-terms-of-service). | **Posting text and evals only** |
| **OpenRouter** `:free` | [20 RPM; 50 a day, or 1,000 after buying 10 credits](https://openrouter.ai/docs/api/reference/limits) | **Varies by endpoint** (see below). [OpenRouter itself doesn't](https://openrouter.ai/privacy) unless you opt in. | [OpenRouter stores no prompts unless you opt in](https://openrouter.ai/docs/guides/privacy/data-collection), apart from CSAM review. Hosts vary. | **Posting text and evals only** |
| **Qwen**, Alibaba Model Studio | [About 1M tokens per model, 90 days, once](https://www.alibabacloud.com/help/en/model-studio/new-free-quota). Listed for [`qwen3.8-flash`, `qwen3.8-max`, `qwen3.8-27b` and others](https://www.alibabacloud.com/help/en/model-studio/model-pricing). | **No,** without separate consent. [Terms 4.48.1(e)](https://www.alibabacloud.com/help/en/legal/latest/alibaba-cloud-international-website-product-terms-of-service-v-3-8-0) | [Stored for legal reasons, no period given](https://www.alibabacloud.com/help/en/model-studio/privacy-notice). [ZDR marked as coming soon](https://www.alibabacloud.com/en/product/model-studio?_p_lc=1). Terms allow cross-border transfer. | **Posting text and evals only;** trial |
| **Cerebras** | [Trial only: $5 credit, 30 days, card required, no permanent free tier](https://inference-docs.cerebras.ai/support/rate-limits). 5 RPM, 1M TPD. | **No.** [Terms](https://www.cerebras.ai/terms-of-service) | [Not retained](https://www.cerebras.ai/privacy-policy), but that policy excludes data it handles as a processor. DPA unread. | **Posting text and evals only;** trial |
| **SambaNova** free | [20 RPM, 20 RPD, 200K TPD](https://docs.sambanova.ai/docs/en/models/rate-limits) | [DPA §4(b) says no](https://sambanova.ai/data-processing-agreement-sambanova), but neither it nor the [EULA](https://sambanova.ai/cloud-end-user-license-agreement) addresses the free tier | [Up to 30 days](https://sambanova.ai/data-processing-agreement-sambanova), against "no storage" marketing. Staff [left the tier question with legal](https://community.sambanova.ai/t/privacy-data-use-in-developer-tier/899). | **Posting text and evals only** |
| **NVIDIA NIM** API catalog | [Varies, shown in your account](https://forums.developer.nvidia.com/t/nvidia-nim-faq/300317). Trial, with [no production use](https://forums.developer.nvidia.com/t/nvidia-nim-faq/300317). | **Treat as yes.** [Trial terms §3.3](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf), excerpts only | §2.3 says not kept after the session; §2.4 allows security and abuse logging | **Posting text and evals only;** evals fit best |
| **Cohere** trial key | [1,000 calls a month, 20 RPM](https://docs.cohere.com/docs/rate-limits) | **Yes,** [after de-identifying](https://cohere.com/privacy). Says not to send personal information. | [Paid commitments exclude trial keys](https://cohere.com/enterprise-data-commitments) | **Posting text and evals only;** evals fit best |
| **OpenAI** | [A Free tier row exists with no model limits](https://developers.openai.com/api/docs/guides/rate-limits). [Free daily tokens need an opt-in and a positive balance](https://help.openai.com/en/articles/10306912-sharing-feedback-evals-and-api-data-with-openai) (search excerpt). | Paid default: [no](https://developers.openai.com/api/docs/guides/your-data). Free tokens: yes, that's the exchange. | Abuse logs up to 30 days | **Do not use** as a free backup. Paid API is a separate choice. |
| **DeepSeek** API | [None listed](https://api-docs.deepseek.com/quick_start/pricing). "Granted balance" is mentioned, not explained. | [Privacy policy lists training; opt-out by email](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html). [API terms are silent](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html). | Stored in China while the account exists. [PRC law and courts](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html). | **Do not use** |
| **GitHub Models** | [Retired July 30, 2026](https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models) | n/a | n/a | **Do not use** |

Consumer apps such as ChatGPT, the Gemini app, Le Chat, DeepSeek chat and Qwen chat are outside this table. Paid tiers are too, except where noted. Their terms differ: [Gemini paid doesn't train](https://ai.google.dev/gemini-api/terms), for example, while Gemini free does.

### Capacity

Same assumptions as the earlier file: a posting is 1,000 input and 50 output tokens, and a pack is 6,000 input and 2,000 output. These are my calculations.

| Free tier and model | Packs a day | Postings a day |
|---|---|---|
| Groq `gpt-oss-120b` or `gpt-oss-20b` | 25 | about 190 |
| Cloudflare `gpt-oss-120b` ([Neuron rates](https://developers.cloudflare.com/workers-ai/platform/pricing/)) | about 30 | about 280 |
| Cloudflare `gpt-oss-20b` | about 60 | about 510 |
| OpenRouter `:free`, no credits | n/a | 50 |

Groq's 8K TPM means about one pack a minute. A pack near that size leaves no margin, so split it into separate calls and test.

## Open questions from the earlier file

- **Which plan Groq's limits apply to:** the Free plan. The [page data](https://console.groq.com/docs/rate-limits) holds separate `freeRows` and `devRows`. 30 RPM, 1K RPD, 8K TPM, 200K TPD for `gpt-oss-120b` is free. Developer is 1K RPM, 500K RPD, 250K TPM. The "Developer plan" sentence describes the upgrade, and the rendered text misleads. Your own [limits page](https://console.groq.com/settings/limits) is final.
- **Which Groq models are Beta Services:** no page names them. The [models page](https://console.groq.com/docs/models) lists preview models, and §3.6 includes "preview" in its definition, so I treat all preview models as Beta. Groq can change labels, so check a model's status before listing it.
- **Mistral's conflict:** I read it as a general marketing line against a specific rule. The [inference page](https://mistral.ai/cloud/inference/) says API data isn't used for training, without separating plans. The [help center](https://help.mistral.ai/en/articles/347617-do-you-use-my-user-data-to-train-your-artificial-intelligence-models) says Free mode may train. [Commercial terms §4.2](https://legal.mistral.ai/terms/commercial-terms-of-service) except opt-out settings from the no-training promise. The [consumer terms](https://legal.mistral.ai/terms/row-consumer-terms) also say Studio and API access are for business customers, so an individual's position is unclear.
- **OpenRouter free endpoints:** the API field is empty, but model pages embed a `data_policy` for each endpoint. See below.

## Groq `gpt-oss-120b`: confirmed, with conditions

- **Training:** §4.2 bars training unless the customer permits it. Don't grant permission in the console.
- **Free tier:** the agreement doesn't say "free tier", but [§5.1 and §14.2](https://console.groq.com/docs/legal/services-agreement) treat fee-free services as Cloud Services. That reading brings in the DPA, though the [DPA](https://console.groq.com/docs/legal/customer-data-processing-addendum) doesn't say so itself.
- **Status:** `gpt-oss-120b` is [listed as production](https://console.groq.com/docs/models).
- **The 30-day logs:** narrower than "kept for 30 days". [Groq says](https://console.groq.com/docs/your-data) inference isn't retained by default, and logs happen only for faults or suspected abuse. All customers may turn on ZDR. §4.2 says "Eligible Customers", which is narrower, so confirm the toggle exists on a free account.
- **Keep off:** batch and fine-tuning, which store data.
- **Acceptable use:** the [policy](https://console.groq.com/docs/legal/ai-policy) restricts unsupervised automated decisions in employment that harm individuals. A candidate reviewing their own pack looks different from that, but this matters for a hosted version.
- **Liability:** free services carry a low cap and no indemnity, so don't expect a remedy.

## OpenRouter free endpoints

From the page source of each `:free` model, read once on 2026-11-02. These are OpenRouter's labels, not the hosts' terms. A [public model list](https://openrouter.ai/api/v1/models) showed 17 free entries out of 452, and I sampled the 10 below.

| Model | Host | Training | Retains prompts |
|---|---|---|---|
| `nemotron-3-ultra-550b-a55b`, `nemotron-3.5-lightning` | NVIDIA | Yes | Yes |
| `inkling`, `inkling-small` | Thinking Machines | Yes | Yes |
| `lfm-2.5-2.6b` | Liquid | Yes | Yes |
| `gemma-4-31b-it` | Google AI Studio | No | Yes, 55 days |
| `north-mini-code` | Cohere | No | Yes, 30 days |
| `flint-v1.0` | Recursive | No | Yes |
| `dots-3-note-preview` | AtlasCloud | No | Yes |
| `xing4.0-29b-a4b` | Phala | No | No; also on the [ZDR list](https://openrouter.ai/api/v1/endpoints/zdr) |

No endpoint is eligible for personal data. The labels aren't terms, the Google and Cohere labels sit awkwardly beside those companies' own free-tier rules, and [free listings can end](https://openrouter.ai/models?max_price=0). Phala is the only clean label, and I didn't read its terms.

For posting text, send [`provider.data_collection: "deny"` or `provider.zdr: true`](https://openrouter.ai/docs/guides/routing/provider-selection) if you want to avoid training hosts. It isn't required by the rule. Avoid the `openrouter/free` router, since it can change hosts.

## Does an open-weight copy change the answer?

Yes. The hosting provider receives the data, so its terms apply.

- **Qwen:** `@cf/qwen/qwen3-30b-a3b-fp8` and `@cf/qwen/qwen3.8-27b` on [Cloudflare](https://developers.cloudflare.com/workers-ai/models/) fall under Cloudflare's terms. Groq's Qwen3.8 is preview, so it isn't eligible.
- **DeepSeek:** Cloudflare lists DeepSeek models, and [SambaNova free](https://docs.sambanova.ai/docs/en/models/rate-limits) lists `DeepSeek-V3.1`. Neither relies on DeepSeek's API or China storage.
- **Check first:** the [Cloudflare limits page](https://developers.cloudflare.com/workers-ai/platform/limits/) says some models need Workers Paid, and each model page says which. The [`gpt-oss-120b` page](https://developers.cloudflare.com/workers-ai/models/gpt-oss-120b/) shows no such requirement.

Quality, licence fit and model behaviour are separate questions that this doesn't settle.

## Recommended fallback lists

Quality is unproven, so run these through the DeepEval set before fixing the order.

**1. Personal data** (Match scoring, Application Packs, verification), after the paid default:

1. Groq `openai/gpt-oss-120b`, ZDR on, batch and fine-tuning off.
2. Cloudflare `@cf/openai/gpt-oss-120b` on Workers Free, without AI Gateway logging. It [stops at the limit](https://developers.cloudflare.com/workers-ai/platform/pricing/) rather than billing. [LiteLLM supports it](https://docs.litellm.ai/docs/providers/cloudflare_workers) with a `cloudflare/` prefix.
3. If both are exhausted, stop and queue. Never fall through to a model on the lists below.

Enforce this with an allowlist in code that defaults to denying a route. Recheck a route when a provider changes its terms or a model changes status.

**2. Job Posting text** (Filter):

1. Groq `openai/gpt-oss-20b`.
2. Cloudflare `@cf/openai/gpt-oss-20b`.
3. Gemini free, Flash-Lite. Google says not to submit personal information, and postings can name recruiters, so strip names, emails and phone numbers first. [Unpaid use is restricted](https://ai.google.dev/gemini-api/terms) if clients are offered to users in the EEA, Switzerland or the UK, which matters for a hosted version.
4. OpenRouter `:free` with the settings above.
5. Mistral Free, if you want one more.

**3. Invented eval fixtures,** including judging:

1. Gemini free as the judge, because it comes from a different model family than `gpt-oss`.
2. Groq and Cloudflare for candidate runs, including Groq preview models.
3. One-off comparisons: Qwen free quota with "Free Quota Only" on, Cerebras trial, NVIDIA catalog, Cohere trial, SambaNova free and OpenRouter `:free`.

Fixtures must stay invented. Don't paste real Profile or Evidence text into an eval.

## Not verified

- **Console settings:** no account was opened, so I didn't see Groq's Data Controls, Groq's or Gemini's actual limits, Mistral's limits or its toggle on a free account.
- **Groq:** "All customers" against "Eligible Customers" for ZDR. Whether free accounts get the DPA is my reading, and Llama free limits weren't in the table.
- **Cloudflare:** neither the data page nor the service terms name the free plan. The [self-serve agreement](https://www.cloudflare.com/terms/) covers services that need an account, and I found no plan-based exception. Processing location isn't stated. The service terms also allow use of content to improve services while ruling out generative AI training.
- **OpenAI:** the [help article](https://help.openai.com/en/articles/10306912-sharing-feedback-evals-and-api-data-with-openai) returned 403, so details come from search excerpts. Whether a free-tier account can make any API calls is not stated.
- **NVIDIA:** I couldn't parse the [trial terms PDF](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf), so section references come from search excerpts. OpenRouter's label agrees on training. The credit model is unsettled in forum posts.
- **Qwen:** a [notice](https://www.alibabacloud.com/en/notice/product_changechange_announcement_for_alibaba_cloud_model_studio_free_quota_7f5?_p_lc=1) says the quota expands to all regions from August 20, 2026, but the [quota](https://www.alibabacloud.com/help/en/model-studio/new-free-quota) and [pricing](https://www.alibabacloud.com/help/en/model-studio/model-pricing) docs still say Singapore only. Inference location for Singapore wasn't on the [regions page](https://www.alibabacloud.com/help/en/model-studio/regions). I found no retention period. The last 19K characters of the product terms weren't read.
- **Mistral:** the [privacy policy](https://legal.mistral.ai/terms/privacy-policy) returned no readable text, so EU hosting and retention are unconfirmed.
- **Cerebras:** the terms and privacy policy are dated August 2024. I couldn't read the DPA or Third-Party Model Terms.
- **Cohere:** the pricing page's ban on production and commercial use of trial keys, and the enterprise commitments page, were seen only as search excerpts.
- **DeepSeek:** whether the privacy policy's training purpose applies to API traffic. How "granted balance" is earned.
- **OpenRouter:** labels come from page source, not a documented API, and I didn't read each host's terms. Only 10 endpoints were sampled.
- **Not checked:** Hugging Face, Together, Fireworks, Z.ai and other hosts. Paid hosts appear in OpenRouter's lists, but I found no reason to add them as free tiers.
- **Reliability:** no free tier's behaviour under this project's load was tested. Log 429s and failures from the first slice.
