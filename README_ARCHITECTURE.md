# CareerReshape — Architecture Notes

This refactor keeps the app on **Streamlit Community Cloud** for now (matches
"just me + a few testers" — no cost, no new infra to run). Everything below
is built so that moving off Streamlit later is a matter of writing a new
thin UI layer (e.g. FastAPI + a JS frontend, or Streamlit-in-Docker on a
VPS) — none of `careerreshape/core/` imports Streamlit at all.

## Layout

```
app.py                          # composition root — the ONLY file that
                                 # knows both Streamlit and Gemini
careerreshape/
  config.py                     # typed Settings, single seam over secrets
  core/
    exceptions.py                # typed error hierarchy
    models.py                    # validated domain objects (parsed LLM output)
    llm/
      client.py                  # LLMClient Protocol (the DI seam)
      gemini_client.py            # concrete Gemini adapter: retry, backoff,
                                   # timeout, circuit breaker, model fallback
      cache.py                    # exact-match TTL response cache
      circuit_breaker.py          # standalone breaker, no extra dependency
    security/
      sanitizer.py                 # prompt-injection mitigation (delimiters)
      url_validator.py             # SSRF protection
    services/
      document_parser.py           # PDF/DOCX/TXT, size + zip-bomb guarded
      web_fetcher.py                # async, SSRF-checked job/LinkedIn fetch
      docx_builder.py               # resume -> .docx
      resume_service.py             # business logic, zero Streamlit imports
      linkedin_service.py           # same, for the LinkedIn tool
    analytics/logger.py            # structured JSON logs + optional webhook
    paywall/usage_tracker.py       # soft session cap, DI'd session_state
  ui/                             # Streamlit rendering only — no LLM/API calls
tests/                            # unit tests using FakeLLMClient, no network
```

## What changed, and why

**Architecture.** The original 754-line `app.py` mixed UI, prompt-building,
the Gemini SDK, file parsing, scraping, and analytics in one file. Business
logic now lives in `resume_service.py` / `linkedin_service.py`, which take
an `LLMClient` (a `Protocol`, not a concrete class) as a constructor
argument. That's the one change that makes the rest possible: tests use
`FakeLLMClient` (see `tests/fakes.py`) instead of mocking Streamlit or
hitting a real API.

**Resilience.** `GeminiLLMClient` retries a *specific* model with
exponential backoff + jitter (via `tenacity`) only on genuinely retryable
errors (429 / timeout) — a 429 no longer silently causes a swap to a
different model, which is what the original loop did. Falling through to
the next discovered model is reserved for structural failures (model not
supported for this key, etc). A small circuit breaker sits in front of all
of it: after repeated failures it opens and fails fast for a cool-down
window instead of making every subsequent user pay the full retry budget
against a dead endpoint.

**Security.**
- Prompt injection: user content is wrapped in a per-request random
  delimiter (`sanitizer.wrap_as_data`) with an explicit "this is data, not
  instructions" framing. Suspicious phrases are logged for abuse monitoring
  but don't hard-block a request — a false positive here just breaks a
  legitimate resume.
- SSRF: `url_validator.assert_safe_url` resolves the hostname and rejects
  private/loopback/link-local/metadata IP ranges *before* any request is
  made, and again after following redirects. Known gap, called out rather
  than hidden: this doesn't pin the validated IP through the actual
  connection, so a narrow DNS-rebinding window remains — closing it fully
  needs a custom `httpx` transport, which is a reasonable next increment
  but was out of scope for this pass.
- DOCX uploads are checked for total *decompressed* size before being
  parsed, guarding against zip-bomb-style files; all uploads are checked
  against a byte-size cap before parsing starts at all.
- The admin panel is still gated by a URL query-string key, unchanged from
  the original — flagged as a real weakness (leaks into logs/referrers,
  no audit trail) rather than fixed, since a proper fix (real auth) is
  bigger than this pass and matters much less at "a few testers" scale.

**Cost & performance.** Exact-match (hash-of-prompt) caching avoids
re-paying for identical resume+job pairs — deliberately not semantic
caching, which would need an embeddings call and a vector index that
isn't justified yet (`cache.py` docstring explains the trade-off and the
`ResponseCache` protocol it's built behind, so swapping later doesn't
touch callers). URL fetching moved to async `httpx` so job-description
fetches don't block synchronously; `asyncio.to_thread` wraps the
Gemini SDK's blocking call so the retry/backoff sleeps don't block the
Streamlit thread either. Streamlit itself reruns the whole script
per-interaction and is effectively single-threaded per session — full
concurrent request handling isn't available on this platform regardless
of how the client code is written; see "Beyond Streamlit Cloud" below.

**Observability.** `StructuredLogger` emits JSON lines to stdout on every
event — including failures, which the original code never logged anywhere
(only successes were pushed to the analytics webhook). Every event carries
a `trace_id` so a single request's start/completion/failure lines can be
grepped together. The webhook is now an optional *additional* sink
(`AnalyticsSink` protocol), not the only record that anything happened.

**Testability.** `tests/` covers the resilience primitives (cache,
circuit breaker), the security primitives (sanitizer, SSRF validator), and
the resume service's business logic — all without Streamlit, network, or
the real Gemini SDK. Run with:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

## Known trade-offs / what's deliberately NOT done here

- **No distributed cache/circuit-breaker.** `InMemoryTTLCache` and
  `CircuitBreaker` live in one Streamlit process's memory. Fine for one
  process; if this ever runs as multiple replicas (see below), swap in a
  Redis-backed cache behind the same `ResponseCache` protocol.
- **No semantic caching.** Exact-match only, as above.
- **No SSRF connection-pinning.** DNS is validated, not pinned through the
  connection.
- **Admin auth is still just a shared query-string secret.**
- **No multi-provider LLM fallback** (e.g. falling back to a different
  provider entirely if Gemini is down) — the `LLMClient` Protocol makes
  this a follow-up (`FallbackLLMClient` composing two adapters), not a
  redesign.

## Beyond Streamlit Cloud

At "tens of users/day" or more, the two real constraints on Streamlit
Community Cloud become: (1) it's a single process per app with no
horizontal scaling, so the in-memory cache/circuit-breaker/session state
don't generalize across replicas, and (2) there's no background worker for
anything long-running. When that becomes the bottleneck, the natural next
step — enabled by, not blocked by, this refactor — is:

1. Keep `careerreshape/core/` entirely as-is.
2. Replace `app.py` with a FastAPI service exposing the same
   `ResumeOptimizerService` / `LinkedInOptimizerService` behind HTTP
   endpoints, run in Docker.
3. Swap `InMemoryTTLCache` for a Redis-backed `ResponseCache`.
4. Put a real frontend (or keep Streamlit talking to the FastAPI backend)
   in front of it.

None of that requires touching prompt logic, the Gemini adapter's
resilience code, or the security/document/fetch modules — that isolation
is the point of this pass.
