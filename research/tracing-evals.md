# Tracing and eval tooling

Answers [#6](https://github.com/cutture/Job-Copilot/issues/6). Sources read 2026-11-01. Pricing and container versions change, so re-check them before relying on them.

## Short answer

- **Start on Langfuse Cloud Hobby.** It is free and likely covers this tool's volume. Self-hosting has no usage limits, but it needs six containers and more RAM than a small VPS has.
- **Mask personal data in the SDK before sending traces.** Hobby can't auto-delete old data.
- **DeepEval fits the daily Eval Run.** Call `evaluate()` from the worker job and write the returned object to Postgres. It runs locally and needs no Confident AI account.

## Langfuse Cloud Hobby vs self-hosted

| | Cloud Hobby | Self-hosted open source |
|---|---|---|
| Cost | Free, no credit card [1] | Free software; you pay for the server [2] |
| Usage | 50k units/month [1] | Unlimited [2] |
| Users | 2 [1] | Unlimited [2] |
| Projects | Unlimited [1] | Unlimited [2] |
| History | 30 days of data access [1] | No limit stated [2] |
| Automatic deletion | Not available [1] | Enterprise licence only [2] |
| Rate limits | Ingestion 1,000 req/min, general API 30 req/min, Datasets API 100 req/min, Metrics API v2 100 req/day [1] | None listed on the pricing page [2] |
| Other limits | 2 alerts, 1 annotation queue [1] | Not stated |
| Support | Community [1] | Community [2] |
| Operations | Managed by Langfuse | You; Compose has no HA, scaling or backups [4] |

**Units.** A unit is any tracing data point: each trace, observation (span, event or generation) and score counts as one [1].

**Hobby and deletion.** Data older than 30 days is hidden, not removed: it "is still stored" and becomes accessible on upgrade [1]. The deletion API is limited to 50 req/day on Hobby [6]. This matters because traces can hold resume text.

**Self-hosted paid features.** Server-side masking, data retention management, project-level RBAC and audit logs need a paid licence [2]. Core tracing, evaluation, prompts, datasets and the public API are free [2].

### Containers self-hosting needs

Six services, from the [official `docker-compose.yml`](https://github.com/langfuse/langfuse/blob/be69f6bddba4e148133db7d76305224de01a6cb5/docker-compose.yml) [3]:

| Service | Image | Role [5] | Stated minimum [7] |
|---|---|---|---|
| `langfuse-web` | `langfuse/langfuse:4` | UI and APIs | 2 CPU, 4 GiB |
| `langfuse-worker` | `langfuse/langfuse-worker:4` | Async event processing | 2 CPU, 4 GiB |
| `postgres` | `postgres:17` | Transactional data | 2 CPU, 4 GiB |
| `redis` | `redis:7` | Cache and job queue | 1 CPU, 1.5 GiB |
| `clickhouse` | `clickhouse-server:26.3.62.3` | Traces, observations, scores | 2 CPU, 8 GiB |
| `minio` | `chainguard/minio` | Raw events and attachments | 2 CPU, 4 GiB |

**Sizing.** For a Compose VM, Langfuse recommends at least 4 cores, 16 GiB of memory and about 100 GiB of disk [4]. The per-service minimums above add up to 11 CPU and 25.5 GiB (my sum); they sit on the scaling page and are not labelled as Compose figures [7].

**ClickHouse can't be avoided.** No other OLAP database is supported [8].

**Compose caveats.** Langfuse describes Compose as the simplest way "to give it a try" and recommends Kubernetes for high availability and high throughput [4]. Default secrets must be changed [3], and the default logging doesn't rotate, so it can fill the disk [4].

**Sharing Postgres.** The docs don't say whether Langfuse can share the app's Postgres. Langfuse uses the `public` schema of its database, and v4 needs Postgres 15 or later [9]. Compose already runs its own instance, so the simple path is to leave the app's database separate.

### Will 50k units be enough?

My estimate, not a measurement. Replace it with real counts once the first slice runs.

| Workload | Per day | Units each | Units/month |
|---|---|---|---|
| Posting filter | 200 | 2 | 12,000 |
| Application Pack, with verification | 10 | 14 | 4,200 |
| Eval cases | 20 | 15 | 9,000 |
| **Total** | | | **25,200** |

### Recommendation

Use Cloud Hobby first:

- Self-hosting would add six containers and at least 16 GiB of RAM on a VPS meant to be small, which is hard to justify in a 2-3 day thin path.
- Use the Langfuse SDK's masking hook. It runs in the app before anything is sent [10].
- Log IDs and metadata rather than raw resume text wherever a trace doesn't need the text.
- Choose the data region deliberately. Cloud offers US, EU and Japan [11].

Move to self-hosting if units regularly near 50k, or if masked traces still hold personal data you won't keep on a third-party service. The hosted app version could be a trigger too. Both Cloud and self-hosted take the same SDK traces, so tracing code should mostly carry over; I did not test a migration.

## DeepEval for a daily Eval Run

**Run it from the worker, not the CLI.** `deepeval test run` is meant for CI/CD gating [12]. `evaluate()` can be called from any Python script and returns data [12][13], so the scheduled job can stay on the Postgres-backed queue.

**No Confident AI needed.** The docs say DeepEval "runs entirely locally"; test runs appear on Confident AI only if you're logged in [12]. Don't log in on the server, so results stay in your own Postgres.

**Judge model.** `LiteLLMModel` plugs into metrics, which matches the provider-agnostic layer already chosen. `litellm` must be installed separately [14][15]. Most built-in metrics call an LLM [16], so judge calls should count towards the $10 monthly cap. A metric's `threshold` defaults to 0.5, and `threshold=None` records a score without affecting pass/fail [16].

**What to store.** The return value is typed in source [13][17]:

| Object | Fields worth keeping |
|---|---|
| `EvaluationResult` | `test_results`; ignore `confident_link`, and `test_run_id` may be empty (it is optional) |
| `TestResult` | `name`, `success`, `input`, `actual_output`, `expected_output`, `metadata`, `metrics_data` |
| `MetricData` | `name`, `score`, `threshold`, `success`, `reason`, `error`, `evaluation_model`, `evaluation_cost`, `input_tokens`, `output_tokens`, `strict_mode`, `flaky` |

Suggested tables, each with a user or tenant ID as the map requires:

- `eval_run`: start and finish time, git SHA, DeepEval version, status.
- `eval_case`: one row per test case.
- `eval_metric`: one row per metric on a case, using the `MetricData` fields above.

Use Eval Cases built from fixtures rather than real resumes, or `input` and `actual_output` will copy personal data into these tables.

**Sketch** (not run):

```python
from deepeval import evaluate
from deepeval.evaluate import CacheConfig, DisplayConfig, ErrorConfig

result = evaluate(
    test_cases=cases,
    metrics=metrics,  # each built with model=LiteLLMModel(...)
    display_config=DisplayConfig(print_results=False, show_indicator=False),
    error_config=ErrorConfig(ignore_errors=True),  # keep going; failures land in MetricData.error
    cache_config=CacheConfig(write_cache=False),
)
save_eval_run(result)  # the app's own insert into the three tables
```

**Config to set** [18][19]:

- `ignore_errors=True` keeps one failed judge call from ending the run. Treat a metric with `error` set as "did not run", not as a failure.
- Leave `use_cache` off (the default), so each daily run really re-scores.
- `write_cache=False` avoids cache files on the container's disk.
- Lower `max_concurrent` (default 20) or raise `throttle_value` in `AsyncConfig` for free-model rate limits.
- Set `DEEPEVAL_TELEMETRY_OPT_OUT=1`. Telemetry to PostHog is on by default and includes public IP and metric names.

**How the tools relate.** DeepEval produces the Eval Run; Postgres and the dashboard page hold it. Langfuse holds traces of live runs. They need no integration for v1, though storing a Langfuse trace ID in `metadata` would link a bad score to its trace.

**Version.** DeepEval 4.3.2 is the latest release (uploaded 2026-10-27), Apache-2.0, Python 3.9 or later [20]. Pin it, because the stored fields come from its source rather than from a documented schema.

## Not verified

- **Hobby at the 50k cap.** The pricing, clarifications and docs search results I read don't say whether ingestion stops, is throttled or prompts an upgrade. Hobby lists no overage price [1][21]. Check with Langfuse or watch usage before the cap.
- **Training on customer data.** The Langfuse security page doesn't address it [11], and I didn't read the privacy policy or terms.
- **Nothing was run.** I did not deploy Langfuse or execute DeepEval. RAM use on a real small VPS is unmeasured; the figures above are Langfuse's stated guidance.
- **Default judge model.** The metrics page implies OpenAI but doesn't name a model [16]. Set the model explicitly so this doesn't matter.
- **Result-field stability.** The field tables come from the `main` branch of DeepEval, not the 4.3.2 tag. Re-check against the pinned version.
- **Page reading.** Most web pages were read through a summarising fetch tool. The compose services and DeepEval classes were checked against the raw files.

## Sources

1. [Langfuse pricing](https://langfuse.com/pricing)
2. [Langfuse self-hosted pricing](https://langfuse.com/pricing-self-host)
3. [`docker-compose.yml`, langfuse/langfuse at be69f6b](https://github.com/langfuse/langfuse/blob/be69f6bddba4e148133db7d76305224de01a6cb5/docker-compose.yml)
4. [Langfuse: Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose)
5. [Langfuse: self-hosting overview](https://langfuse.com/self-hosting)
6. [Langfuse: API limits](https://langfuse.com/faq/all/api-limits)
7. [Langfuse: scaling](https://langfuse.com/self-hosting/configuration/scaling)
8. [Langfuse: ClickHouse](https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse)
9. [Langfuse: PostgreSQL](https://langfuse.com/self-hosting/deployment/infrastructure/postgres)
10. [Langfuse: masking](https://langfuse.com/docs/observability/features/masking)
11. [Langfuse: security](https://langfuse.com/security)
12. [DeepEval: evaluation introduction](https://deepeval.com/docs/evaluation-introduction)
13. [`deepeval/evaluate/evaluate.py` at 90e230c](https://github.com/confident-ai/deepeval/blob/90e230cbe916c73240a48312c494065a39bf52d1/deepeval/evaluate/evaluate.py)
14. [DeepEval: LiteLLM integration](https://deepeval.com/integrations/models/litellm)
15. [deepeval 4.3.2 PyPI metadata](https://pypi.org/pypi/deepeval/4.3.2/json)
16. [DeepEval: metrics introduction](https://deepeval.com/docs/metrics-introduction)
17. [`deepeval/evaluate/types.py`](https://github.com/confident-ai/deepeval/blob/90e230cbe916c73240a48312c494065a39bf52d1/deepeval/evaluate/types.py) and [`deepeval/tracing/api.py`](https://github.com/confident-ai/deepeval/blob/90e230cbe916c73240a48312c494065a39bf52d1/deepeval/tracing/api.py) at 90e230c
18. [DeepEval: flags and configs](https://deepeval.com/docs/evaluation-flags-and-configs)
19. [DeepEval: data privacy](https://deepeval.com/docs/data-privacy)
20. [deepeval on PyPI](https://pypi.org/project/deepeval/)
21. [Langfuse: clarifications](https://langfuse.com/resources/engineering/clarifications)
