# LiteLLM Routing POC

Proof of concept that runs [LiteLLM](https://docs.litellm.ai/) as an LLM gateway with a Chainlit front end. It is used to compare LiteLLM's routing strategies across Azure OpenAI, Groq and a self-hosted Gemma model before the AI Office production deployment.

This is a POC, not a production deployment. The production design for Azure Container Apps is in the deployment plan (`Plan_LiteLLM_Azure_Container_Apps_*.docx`), which is kept out of git.

## What is in this repo

| Path | Purpose |
| --- | --- |
| `docker-compose.yml` | Runs PostgreSQL 16, Redis 7, the LiteLLM proxy, an OpenTelemetry collector, the Chainlit UI and Caddy |
| `litellm-config.yml` | Models, routers (complexity, quality, adaptive, semantic, tag-based, load-balanced) and reliability settings |
| `router.json` | Semantic route file mounted into the proxy. Not used at the moment, because `litellm-config.yml` defines the semantic routes inline |
| `otel-collector-config.yaml` | Receives traces from LiteLLM and exports them to Azure Monitor (Application Insights) |
| `Caddyfile` | TLS reverse proxy for the Chainlit UI on `GATEWAY_HOSTNAME` |
| `chainlit_app/` | Chainlit UI: `app.py`, `Dockerfile`, static assets in `public/`, settings in `.chainlit/config.toml` |
| `.env.example` | Template for every environment variable the stack needs |

## Prerequisites

- Docker Engine with Docker Compose v2
- Access to Azure OpenAI or Microsoft Foundry, and a Groq API key
- A reachable Gemma vLLM server (optional; the `gemma` model fails without it)
- For the public Chainlit UI: a DNS name for the host and ports 80 and 443 open, so Caddy can obtain TLS certificates

## Set up

1. Create your local environment file and lock it down:

   ```bash
   cp .env.example .env
   chmod 600 .env
   ```

2. Fill in `.env`. Generate the LiteLLM keys like this:

   ```bash
   echo "sk-$(openssl rand -hex 24)"   # LITELLM_MASTER_KEY
   openssl rand -hex 32                # LITELLM_SALT_KEY: set it once and never change it
   ```

3. Start the stack:

   ```bash
   docker compose up -d --build
   docker compose ps
   ```

4. Create the virtual key the Chainlit UI uses (it must not use the master key), then restart Chainlit:

   ```bash
   LITELLM_MASTER_KEY=$(grep '^LITELLM_MASTER_KEY=' .env | cut -d= -f2-)
   curl -s http://127.0.0.1:4000/key/generate \
     -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
     -H "Content-Type: application/json" \
     -d '{"key_alias": "chainlit-ui"}'
   # Copy the "key" value into .env as CHAINLIT_LITELLM_API_KEY=..., then:
   docker compose up -d chainlit
   ```

   Until this key is set, the UI shows a message explaining what is missing.

## Use it

- **Chainlit UI:** `https://<GATEWAY_HOSTNAME>`, signed in with `APP_USERNAME` and `APP_PASSWORD`.
- **LiteLLM proxy:** `http://127.0.0.1:4000`. It listens on localhost only, so from another machine use an SSH tunnel: `ssh -L 4000:127.0.0.1:4000 <user>@<host>`.
- **LiteLLM Admin UI:** `http://127.0.0.1:4000/ui`. Sign in as `admin` with the master key.

Example call through the proxy:

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer <virtual-key>" \
  -H "Content-Type: application/json" \
  -d '{"model": "smart-router", "messages": [{"role": "user", "content": "hello"}]}'
```

Model names you can call:

| Type | Names |
| --- | --- |
| Routers | `smart-router`, `quality-router`, `adaptive-router`, `semantic-router`, `chat-tiered`, `cheap-chat` |
| Base models | `azure-gpt-mini`, `groq-gpt-oss-20b`, `groq-gpt-oss-120b`, `groq-qwen3`, `claude-opus`, `gemma`, `text-embedding` |
| Routing demos | `gpt-priority` (Azure first, Groq backup), `mirror-demo` (Azure answer, silent copy to Groq) |

## Make changes

| You changed | Run |
| --- | --- |
| `litellm-config.yml` | `docker compose restart litellm` |
| `chainlit_app/` code or `public/` assets | `docker compose up -d --build chainlit`, then hard-refresh the browser (assets are baked into the image) |
| `Caddyfile` | `docker compose restart caddy` |
| `.env` values | `docker compose up -d` (recreates the services whose settings changed) |

## Security notes

- Never commit `.env`. `.gitignore` excludes it; run `git check-ignore -v .env` before your first commit to confirm.
- If a secret is ever pushed, rotate it straight away and tell Security. Removing the commit is not enough.
- `LITELLM_SALT_KEY` encrypts credentials stored in the database. Changing it makes them unreadable, so it cannot simply be rotated.
- Give applications virtual keys, not the master key.

## Known gaps (POC only)

- If `GEMMA_API_BASE` uses `http://`, the Gemma API key and prompts travel unencrypted. Fixing this needs TLS on the Gemma server.
- The auto-routing features are beta in LiteLLM, and the semantic router is deprecated. From v1.101.0, customising more than one auto-router needs a LiteLLM licence.
- Traffic mirroring lives on its own `mirror-demo` model: LiteLLM's background health check forwards `silent_model` to Azure, which rejects it, so a mirrored deployment would be marked unhealthy.
- Health-check routing cannot remove a model group that has only one deployment (Gemma). Gemma has a 10-second timeout, and timed-out calls go straight to their fallback.
- Background health checks log a harmless `custom_llm_provider is required` error from the provider-budget tracker.

## LiteLLM routing strategies reference

Every routing technique LiteLLM offers, from the [official docs](https://docs.litellm.ai/docs/routing) and the [`router_strategy` code](https://github.com/BerriAI/litellm/tree/main/litellm/router_strategy), checked on Oct 6, 2026. Each entry says why you would use it, what you gain, and a config example in LiteLLM's documented syntax. Model names in the examples are placeholders.

**Version column:** this POC runs LiteLLM v1.104.0 (upgraded on Oct 6, 2026 from v1.89.3), so every entry marked "POC" or "v1.92+" works here.

| # | Technique | Type | In this POC | Version |
| --- | --- | --- | --- | --- |
| 1 | Simple shuffle (weighted pick) | Load balancing | Yes (active) | POC |
| 2 | Least busy | Load balancing | Comment only | POC |
| 3 | Usage-based routing (v1) | Load balancing | Comment only | POC |
| 4 | Usage-based routing v2 | Load balancing | Comment only | POC |
| 5 | Latency-based routing | Load balancing | Comment only | POC |
| 6 | Cost-based routing | Load balancing | Comment only | POC |
| 7 | Provider budget routing | Load balancing | Yes | POC |
| 8 | Routing groups | Per-group strategy | Yes (`cheap-chat`, latency-based) | POC |
| 9 | Deployment ordering (priority) | Reliability | Yes (`gpt-priority`) | POC |
| 10 | Weighted failover | Reliability | No | POC |
| 11 | Fallbacks (general, context window, content policy) | Reliability | Yes | POC |
| 12 | Retries, retry policy, cooldowns, allowed fails | Reliability | Yes | POC |
| 13 | Max parallel requests | Reliability | No | POC |
| 14 | Health-check-driven routing | Reliability | Yes (every 5 min) | POC |
| 15 | Pre-call checks (context window, region) | Filtering | Context window only | POC |
| 16 | Session affinity (sticky sessions) | Filtering | No | POC |
| 17 | Tag-based routing | Rule-based | Yes | POC |
| 18 | Wildcard (provider) routing | Rule-based | No | POC |
| 19 | Traffic mirroring (silent model) | Evaluation | Yes (`mirror-demo`) | POC |
| 20 | Complexity router (auto router) | Content-aware | Yes (`smart-router`) | POC |
| 21 | Quality router | Content-aware | Yes (`quality-router`) | POC |
| 22 | Adaptive router | Content-aware | Yes (`adaptive-router`) | POC |
| 23 | Semantic router (deprecated) | Content-aware | Yes (`semantic-router`) | POC |
| 24 | Request prioritization (beta) | Scheduling | No | POC |
| 25 | Custom routing strategy | Custom | No | POC (Python SDK) |
| 26 | Routing plugins | Custom | No | v1.92+ |
| 27 | Budget fallbacks (per key) | Spend control | No | v1.92+ |
| 28 | Team-based and region-based routing (deprecated) | Rule-based | No | Use tag routing instead |
| 29 | LAR-1 confidence routing | Custom | No | In the repo only, undocumented |

Only one of strategies 1 to 6 is active for the whole proxy (`router_settings.routing_strategy`), unless you use routing groups (8). They decide between deployments that share a `model_name`; the content-aware routers (20 to 23) decide which model to use.

### Load-balancing strategies

#### 1. Simple shuffle (weighted pick)

- **Why:** spread traffic across several deployments of the same model (regions, keys, providers).
- **Benefit:** lowest overhead and LiteLLM's recommended production default. Picks by `weight`, or by `rpm`/`tpm` capacity, or at random.

```yaml
model_list:
  - model_name: gpt-standard
    litellm_params:
      model: azure/<deployment-a>
      api_base: os.environ/AZURE_API_BASE_A
      weight: 9            # or rpm: / tpm: to pick by capacity
  - model_name: gpt-standard
    litellm_params:
      model: azure/<deployment-b>
      api_base: os.environ/AZURE_API_BASE_B
      weight: 1            # 90/10 split, useful for canary rollouts
router_settings:
  routing_strategy: simple-shuffle
```

#### 2. Least busy

- **Why:** requests vary a lot in duration and you want to avoid piling onto one deployment.
- **Benefit:** sends each request to the deployment with the fewest requests in flight.

```yaml
router_settings:
  routing_strategy: least-busy
```

#### 3. Usage-based routing (v1)

- **Why:** stay under each deployment's per-minute token limit.
- **Benefit:** picks the deployment with the lowest tokens used this minute. Needs Redis when you run more than one instance.

```yaml
model_list:
  - model_name: gpt-standard
    litellm_params:
      model: azure/<deployment-a>
      tpm: 100000
      rpm: 1000
router_settings:
  routing_strategy: usage-based-routing
  redis_host: os.environ/REDIS_HOST
  redis_port: os.environ/REDIS_PORT
  redis_password: os.environ/REDIS_PASSWORD
```

#### 4. Usage-based routing v2 (rate-limit aware)

- **Why:** avoid 429s from providers by respecting each deployment's TPM/RPM.
- **Benefit:** skips deployments that would exceed their limits. Adds Redis lookups to every request, so it is slower than simple shuffle.

```yaml
router_settings:
  routing_strategy: usage-based-routing-v2
  redis_host: os.environ/REDIS_HOST
  redis_port: os.environ/REDIS_PORT
  redis_password: os.environ/REDIS_PASSWORD
```

#### 5. Latency-based routing

- **Why:** user-facing traffic where response time matters most.
- **Benefit:** picks the deployment with the lowest recent latency; the buffer spreads load among deployments that are nearly as fast.

```yaml
router_settings:
  routing_strategy: latency-based-routing
  routing_strategy_args:
    ttl: 10                      # seconds of latency history to keep
    lowest_latency_buffer: 0.5   # treat deployments within 50% of the fastest as equal
```

#### 6. Cost-based routing

- **Why:** the same model is offered by providers at different prices.
- **Benefit:** picks the cheapest deployment using LiteLLM's cost map or your `model_info` costs. A deployment missing from the cost map counts as $1.

```yaml
model_list:
  - model_name: cheap-chat
    litellm_params:
      model: groq/openai/gpt-oss-20b
    model_info:
      input_cost_per_token: 0.0000001
      output_cost_per_token: 0.0000005
router_settings:
  routing_strategy: cost-based-routing
```

#### 7. Provider budget routing

- **Why:** cap daily or monthly spend per provider.
- **Benefit:** once a provider's budget for the period is used up, the router stops sending it traffic and uses other deployments. Needs Redis across instances.

```yaml
router_settings:
  provider_budget_config:
    azure:
      budget_limit: 100     # USD
      time_period: 1d       # 1d, 30d, 1mo ...
    groq:
      budget_limit: 20
      time_period: 1d
  redis_host: os.environ/REDIS_HOST
  redis_port: os.environ/REDIS_PORT
  redis_password: os.environ/REDIS_PASSWORD
```

#### 8. Routing groups (a strategy per model group)

- **Why:** you want latency-based routing for one model but the default for everything else.
- **Benefit:** different strategies in one proxy, and each group can be called as a model. Each `model_name` can belong to only one group.

```yaml
router_settings:
  routing_strategy: simple-shuffle          # default for models in no group
  routing_groups:
    - group_name: latency-sensitive         # required
      models: ["gpt-standard"]
      routing_strategy: latency-based-routing
      routing_strategy_args:
        ttl: 3600
```

### Reliability

#### 9. Deployment ordering (priority)

- **Why:** a primary deployment with backups (for example a provisioned-throughput deployment first, pay-as-you-go second).
- **Benefit:** lower `order` is tried first; on failure the router moves to the next order level, each with its own retries.

```yaml
model_list:
  - model_name: gpt-standard
    litellm_params:
      model: azure/<primary-deployment>
      order: 1          # tried first
  - model_name: gpt-standard
    litellm_params:
      model: azure/<backup-deployment>
      order: 2          # used when order 1 fails
```

#### 10. Weighted failover

- **Why:** several regional copies of one model; a failed region should fail over to its peer, not to a different model.
- **Benefit:** retries inside the same model group (re-picking by weight) before using cross-group fallbacks.

```yaml
router_settings:
  enable_weighted_failover: true
```

#### 11. Fallbacks

- **Why:** keep answering when a model fails, its context window is too small, or a content filter blocks it.
- **Benefit:** requests move to the next model group in the list automatically.

```yaml
router_settings:
  fallbacks:
    - {"gpt-standard": ["gpt-backup"]}
  context_window_fallbacks:
    - {"gpt-standard": ["gpt-long-context"]}
  content_policy_fallbacks:
    - {"gpt-standard": ["claude-standard"]}
```

#### 12. Retries, retry policy, cooldowns and allowed fails

- **Why:** absorb transient errors and stop hammering a failing deployment.
- **Benefit:** retries per error type, and a deployment is cooled down (skipped) after too many failures.

```yaml
router_settings:
  num_retries: 3
  retry_after: 5                     # minimum seconds before a retry
  retry_policy:
    AuthenticationErrorRetries: 0
    TimeoutErrorRetries: 2
    RateLimitErrorRetries: 3
  allowed_fails: 2                   # failures before cooldown
  cooldown_time: 30                  # seconds
  allowed_fails_policy:
    RateLimitErrorAllowedFails: 100
```

#### 13. Max parallel requests

- **Why:** protect a deployment (for example a self-hosted model) from more concurrent requests than it can serve.
- **Benefit:** a per-deployment concurrency cap; extra requests get an immediate 429, which retries and fallbacks handle. The cap is per proxy worker.

```yaml
model_list:
  - model_name: gemma
    litellm_params:
      model: openai/<model-id>
      max_parallel_requests: 10
router_settings:
  default_max_parallel_requests: 20
```

#### 14. Health-check-driven routing

- **Why:** stop sending users to a deployment that is already broken (expired key, server down).
- **Benefit:** background checks remove failing deployments before a user request fails. Each check calls every model, so it costs tokens; use a sensible interval.

```yaml
general_settings:
  background_health_checks: true
  health_check_interval: 300
  enable_health_check_routing: true
  health_check_ignore_transient_errors: true   # 429 and 408 do not mark a deployment unhealthy
```

### Filtering before the pick

#### 15. Pre-call checks (context window, region)

- **Why:** avoid sending a prompt to a deployment whose context window is too small, or outside the allowed region.
- **Benefit:** unsuitable deployments are filtered out before routing. Azure deployments need `base_model` for the context window check.

```yaml
model_list:
  - model_name: gpt-standard
    litellm_params:
      model: azure/<deployment>
      region_name: "eu"            # for region filtering
    model_info:
      base_model: azure/<model-name>
router_settings:
  enable_pre_call_checks: true
```

#### 16. Session affinity (sticky sessions)

- **Why:** deployments do not share state, for example provider-side prompt caching, or a conversation must stay in one region.
- **Benefit:** every request with the same session id goes to the deployment that served the first one.

```yaml
router_settings:
  optional_pre_call_checks: ["session_affinity"]
  deployment_affinity_ttl_seconds: 3600
```

Clients send the session id in the `x-litellm-session-id` header.

### Rule-based routing

#### 17. Tag-based routing

- **Why:** route by who is calling (free vs paid users, team, environment, provider) rather than by prompt.
- **Benefit:** one endpoint, different models per tag; replaces the deprecated team-based and region-based routing.

```yaml
model_list:
  - model_name: chat
    litellm_params:
      model: groq/openai/gpt-oss-20b
      tags: ["free", "default"]     # "default" catches untagged requests
  - model_name: chat
    litellm_params:
      model: azure/<deployment>
      tags: ["paid"]
router_settings:
  enable_tag_filtering: true
```

Clients send `"tags": ["paid"]` in the body or the `x-litellm-tags` header.

#### 18. Wildcard (provider) routing

- **Why:** expose every model from a provider without listing each one.
- **Benefit:** less config to maintain. The downside is less control over which models callers can use.

```yaml
model_list:
  - model_name: "groq/*"
    litellm_params:
      model: "groq/*"
      api_key: os.environ/GROQ_API_KEY
```

### Evaluation

#### 19. Traffic mirroring (silent model)

- **Why:** test a cheaper or newer model on real production prompts before switching.
- **Benefit:** the silent model gets a copy of each request in the background; users only ever see the primary response. Mirrored requests are billed too.

```yaml
model_list:
  - model_name: primary-model
    litellm_params:
      model: azure/<deployment>
      silent_model: evaluation-model     # mirror traffic here
  - model_name: evaluation-model
    litellm_params:
      model: groq/openai/gpt-oss-120b
```

### Content-aware routers

#### 20. Complexity router (auto router)

- **Why:** "cheap when good enough": easy prompts to a cheap model, hard ones to a premium model.
- **Benefit:** a local heuristic scores each prompt (no extra API call) and maps it to a tier. Beta. From v1.94 it also offers an LLM classifier, keyword rules with semantic matching, tier pools and session affinity; from v1.101.0, customizing more than one router needs a licence.

```yaml
model_list:
  - model_name: smart-router
    litellm_params:
      model: auto_router/complexity_router
      complexity_router_config:
        tiers:
          SIMPLE: cheap-model
          MEDIUM: mid-model
          COMPLEX: strong-model
          REASONING: reasoning-model
        # v1.94+: rules that run before the scorer
        # keyword_tier_rules:
        #   - keywords: ["kubernetes", "istio"]
        #     tier: REASONING
      complexity_router_default_model: mid-model
```

#### 21. Quality router

- **Why:** guarantee a minimum quality level, and force the best model for sensitive topics.
- **Benefit:** maps the prompt's complexity to a quality tier and picks a model at that tier; a matching keyword overrides it. Exists in the LiteLLM code but has no page in the docs, so treat it as experimental.

```yaml
model_list:
  - model_name: strong-model
    litellm_params:
      model: azure/<deployment>
    model_info:
      litellm_routing_preferences:
        quality_tier: 3
        keywords: ["legal", "security"]
  - model_name: quality-router
    litellm_params:
      model: auto_router/quality_router
      quality_router_default_model: cheap-model
      quality_router_config:
        available_models: ["cheap-model", "mid-model", "strong-model"]
        complexity_to_quality: {SIMPLE: 1, MEDIUM: 2, COMPLEX: 3, REASONING: 3}
```

#### 22. Adaptive router

- **Why:** you do not want to hand-tune rules.
- **Benefit:** learns from real traffic which model gives the best quality per dollar for each type of request. Beta; needs PostgreSQL to keep what it learns.

```yaml
model_list:
  - model_name: strong-model
    litellm_params:
      model: azure/<deployment>
    model_info:
      adaptive_router_preferences:
        quality_tier: 3            # 1 = budget, 3 = frontier
        strengths: ["code_generation", "analytical_reasoning"]
  - model_name: adaptive-router
    litellm_params:
      model: auto_router/adaptive_router
      adaptive_router_config:
        available_models: ["strong-model", "cheap-model"]
        weights:
          quality: 0.7             # must sum to 1.0 with cost
          cost: 0.3
```

#### 23. Semantic router (deprecated)

- **Why:** route by what a prompt is about (coding vs chat) using embeddings.
- **Benefit:** no keyword lists to maintain. Deprecated: new setups should use the complexity router's keyword rules with semantic matching (upgrade).

```yaml
model_list:
  - model_name: semantic-router
    litellm_params:
      model: auto_router/semantic_router_1
      auto_router_default_model: cheap-model
      auto_router_embedding_model: text-embedding
      auto_router_config: '{"routes":[{"name":"strong-model","description":"coding tasks","utterances":["debug this stack trace","refactor this function"],"score_threshold":0.3}]}'
```

### Scheduling, custom and spend control

#### 24. Request prioritization (beta)

- **Why:** under heavy load, serve important requests first.
- **Benefit:** requests carry a `priority` (lower is served first) and wait in a queue for a healthy deployment. LiteLLM marks it for testing only.

```yaml
litellm_settings:
  request_timeout: 600       # queued requests keep retrying until this timeout
router_settings:
  redis_host: os.environ/REDIS_HOST
  redis_port: os.environ/REDIS_PORT
  redis_password: os.environ/REDIS_PASSWORD
```

Clients add `"priority": 0` to the request body.

#### 25. Custom routing strategy

- **Why:** business rules none of the built-in strategies cover (by tenant, time of day, region).
- **Benefit:** full control over which deployment is picked. Set through the Python SDK.

```python
from litellm import Router
from litellm.router import CustomRoutingStrategyBase

class MyStrategy(CustomRoutingStrategyBase):
    async def async_get_available_deployment(self, model, messages=None, input=None,
                                             specific_deployment=False, request_kwargs=None):
        ...  # return one deployment dict from router.model_list

router = Router(model_list=model_list)
router.set_custom_routing_strategy(MyStrategy())
```

#### 26. Routing plugins (v1.92+)

- **Why:** add your own step to the routing decision without replacing the router.
- **Benefit:** plugins can narrow the candidate models or publish signals before the router (or the complexity router's tier pick) decides.

```yaml
model_list:
  - model_name: smart-router
    litellm_params:
      model: auto_router/complexity_router
      complexity_router_config:
        tiers: {SIMPLE: cheap-model, MEDIUM: mid-model, COMPLEX: strong-model, REASONING: strong-model}
        plugins:
          - plugins.cost_ceiling_plugin.cost_ceiling_plugin   # dotted path to your plugin
```

#### 27. Budget fallbacks per key (v1.92+)

- **Why:** when a key has spent its budget on an expensive model, move it to a cheaper one instead of rejecting it.
- **Benefit:** the request is silently rerouted to the first fallback that still has budget. Configured on the virtual key, not in `config.yaml`.

```bash
curl http://127.0.0.1:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"model_max_budget": {"claude-opus": {"budget_limit": 5, "time_period": "1d"}},
       "budget_fallbacks": {"claude-opus": ["azure-gpt-mini"]}}'
```

#### 28. Team-based and region-based routing (deprecated)

Both are deprecated in LiteLLM's docs. Use tag-based routing (17) with a tag per team or region instead.

#### 29. LAR-1 confidence routing

A strategy in the LiteLLM repo ([`lar1_routing.py`](https://github.com/BerriAI/litellm/blob/main/litellm/router_strategy/lar1_routing.py)) that routes on an agent's self-reported confidence, passed as LAR-1 metadata, with thresholds in `routing_strategy_args` (`confidence_threshold_low`, `confidence_threshold_medium`, `confidence_threshold_high`). It has no documentation page, so it is listed here for completeness only.

### Sources

- [Routing guide](https://docs.litellm.ai/docs/routing), [Load balancing](https://docs.litellm.ai/docs/proxy/load_balancing), [Reliability](https://docs.litellm.ai/docs/proxy/reliability)
- [Provider budget routing](https://docs.litellm.ai/docs/proxy/provider_budget_routing), [Tag routing](https://docs.litellm.ai/docs/proxy/tag_routing), [Wildcard routing](https://docs.litellm.ai/docs/wildcard_routing)
- [Health check routing](https://docs.litellm.ai/docs/proxy/health_check_routing), [Traffic mirroring](https://docs.litellm.ai/docs/traffic_mirroring), [Request prioritization](https://docs.litellm.ai/docs/scheduler)
- [Auto routing](https://docs.litellm.ai/docs/proxy/auto_routing), [Adaptive router](https://docs.litellm.ai/docs/adaptive_router), [Semantic auto router](https://docs.litellm.ai/docs/proxy/auto_routing_semantic)
- [Routing plugins](https://docs.litellm.ai/docs/routing_plugins), [Budget fallbacks](https://docs.litellm.ai/docs/proxy/budget_fallbacks)
- [Team-based routing](https://docs.litellm.ai/docs/proxy/team_based_routing), [Region-based routing](https://docs.litellm.ai/docs/proxy/customer_routing)
- Source code: [`litellm/router_strategy`](https://github.com/BerriAI/litellm/tree/main/litellm/router_strategy), [`litellm/types/router.py`](https://github.com/BerriAI/litellm/blob/main/litellm/types/router.py)
