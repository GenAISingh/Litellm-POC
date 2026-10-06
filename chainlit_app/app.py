"""
Chainlit front-end for the LiteLLM routing POC.

- Pick any router/model from the LiteLLM dashboard (dropdown, fetched live).
- Chat normally.
- Each answer is annotated with: which model actually served it, the routing
  reasoning (read from the routers' x-litellm-quality-router-* and
  x-litellm-complexity-router-* response headers; older LiteLLM versions fall back to
  the proxy logs when the docker CLI is available), tokens, cost, and latency.
- Calls LiteLLM with its own virtual key (LITELLM_API_KEY), never the master key.

Run:
    cd chainlit_app
    pip install -r requirements.txt
    chainlit run app.py -w      # opens http://localhost:8000
"""

import os
import re
import time
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import httpx
import chainlit as cl
from chainlit.input_widget import Select


def fmt_money(v) -> str:
    """Readable dollars — never scientific notation."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return f"${v}"
    if v == 0:
        return "$0"
    if v >= 1:
        return f"${v:,.2f}"
    if v >= 0.0001:
        return f"${v:.4f}"
    return "$" + f"{v:.8f}".rstrip("0").rstrip(".")

# --- config -----------------------------------------------------------------
LITELLM_BASE = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000")
LITELLM_CONTAINER = os.environ.get("LITELLM_CONTAINER", "litellm-proxy")
# Host of the self-hosted Gemma server, taken from GEMMA_API_BASE so no address is hardcoded.
GEMMA_HOST = urlparse(os.environ.get("GEMMA_API_BASE", "")).hostname or ""
# The docker CLI only exists when the app runs on the host; inside the container the
# log-based details (complexity score, provider budget note) are skipped.
DOCKER_CLI = shutil.which("docker") is not None


def _load_api_key() -> str:
    """LiteLLM virtual key for this UI (never the master key): env LITELLM_API_KEY, else
    CHAINLIT_LITELLM_API_KEY from the sibling ../.env for local runs."""
    key = os.environ.get("LITELLM_API_KEY")
    if key:
        return key
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("CHAINLIT_LITELLM_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


LITELLM_KEY = _load_api_key()
HEADERS = {"Authorization": f"Bearer {LITELLM_KEY}", "Content-Type": "application/json"}

# Routers vs plain models — for a friendlier dropdown ordering / labels.
ROUTERS = {
    "smart-router": "🧠 Complexity Router (by difficulty)",
    "semantic-router": "🧭 Semantic Router (by meaning)",
    "adaptive-router": "📈 Adaptive Router (learns)",
    "chat-tiered": "🏷️ Tag-based (free/paid)",
    "cheap-chat": "⚖️ Load-balanced group",
    "quality-router": "🎯 Quality Router (by quality tier)",
    "gpt-priority": "🥇 Priority failover (Azure, then Groq)",
    "mirror-demo": "🪞 Traffic mirroring (silent test)",
}

# Visible one-tap router buttons (shown under the welcome + every response).
ROUTER_CHOICES = [
    ("smart-router", "🧠 Complexity"),
    ("semantic-router", "🧭 Semantic"),
    ("adaptive-router", "📈 Adaptive"),
    ("chat-tiered", "🏷️ Tag free/paid"),
    ("cheap-chat", "⚖️ Load-balance"),
    ("quality-router", "🎯 Quality"),
    ("gpt-priority", "🥇 Priority failover"),
    ("mirror-demo", "🪞 Mirror test"),
]


def router_actions():
    actions = [
        cl.Action(name="pick_model", payload={"model": m}, label=lbl)
        for m, lbl in ROUTER_CHOICES
    ]
    actions.append(cl.Action(name="show_strategies", payload={}, label="📖 Routing strategies"))
    return actions


@cl.action_callback("pick_model")
async def pick_model(action: cl.Action):
    model = action.payload["model"]
    prev = cl.user_session.get("model")
    cl.user_session.set("model", model)
    if prev != model:
        await cl.Message(content=f"→ routing through **{model}**", author="system").send()


@cl.action_callback("show_strategies")
async def show_strategies(action: cl.Action):
    card = cl.CustomElement(name="StrategyCard", props={"strategies": STRATEGY_CARDS, "active": "complexity"})
    await cl.Message(content=STRATEGIES_GUIDE, author="📖 strategies", elements=[card], actions=router_actions()).send()


# Data for the StrategyCard custom element (public/elements/StrategyCard.jsx)
STRATEGY_CARDS = [
    {
        "id": "complexity", "icon": "complexity", "tab": "Complexity", "model": "smart-router",
        "tag": "Cheap when good enough",
        "why": "Send easy prompts to a cheap model and hard ones to a premium model — automatically. Big cost savings with no quality loss, and zero rules to tune. This is our default answer to “cheap when good enough.”",
        "how": "Scores each prompt across 7 heuristics, maps the total to a tier, then sends it to the model for that tier. 2+ reasoning keywords force the Reasoning tier. Zero external calls, sub-millisecond.",
        "routes": [["SIMPLE", "gemma", "cheapest"], ["MEDIUM", "azure-gpt-mini", "code present"],
                   ["COMPLEX", "groq-gpt-oss-120b", "heavy / technical"], ["REASONING", "claude-opus", "falls back to groq-qwen3"]],
        "examples": ["what's a good name for a pet goldfish?", "write and explain a quicksort in python",
                     "prove, step by step, that the square root of 2 is irrational"],
    },
    {
        "id": "quality", "icon": "quality", "tab": "Quality", "model": "quality-router",
        "tag": "Guaranteed quality tier",
        "why": "Guarantee a minimum quality level per request, and force the top model on sensitive topics (legal, security, production incidents) via keywords — so important asks never get a weak model.",
        "how": "Maps difficulty to a target quality tier and picks a model at that tier. A declared keyword overrides everything (legal/security -> Opus). Ties — a keyword on several models, or several models at one tier — break by highest tier, then cheapest.",
        "routes": [["SIMPLE", "gemma", "tier 1"], ["MEDIUM", "azure-gpt-mini", "tier 2"],
                   ["COMPLEX", "groq-gpt-oss-120b", "tier 3 · cheaper"], ["COMPLEX", "groq-qwen3", "tier 3 · pricier"],
                   ["REASONING", "claude-opus", "tier 4 · legal/security"]],
        "examples": ["fix this grammar mistake", "review this legal contract for me", "do a security review of my app", "help me build a data pipeline"],
    },
    {
        "id": "adaptive", "icon": "adaptive", "tab": "Adaptive", "model": "adaptive-router",
        "tag": "Learns over time",
        "why": "Instead of hand-tuned rules, the gateway learns from real traffic which model gives the best quality-per-dollar for each task type — and keeps improving on its own.",
        "how": "Sorts each request into a task category and learns from real traffic which model gives the best quality-per-dollar (quality:cost weight 0.7:0.3). Cold-start follows each model's declared tier. Needs Postgres.",
        "routes": [["MEDIUM", "groq-gpt-oss-20b", "factual / general"], ["MEDIUM", "azure-gpt-mini", "writing / general"],
                   ["COMPLEX", "groq-gpt-oss-120b", "code / analysis"]],
        "examples": ["what is the capital of France?", "write a python function to merge two sorted lists"],
    },
    {
        "id": "semantic", "icon": "semantic", "tab": "Semantic", "model": "semantic-router",
        "tag": "Routes by meaning",
        "why": "Route by what the prompt is *about* (coding vs chat) using meaning — not keyword lists — so there are no brittle rules to maintain as phrasing changes.",
        "how": "Embeds the prompt and matches it by meaning to example phrases per route (Azure embeddings) — no hand-written rules. Coding-like prompts go to Claude, chat-like prompts to Gemma.",
        "routes": [["CODING", "claude-opus", "similar to coding examples"], ["CHAT", "gemma", "similar to chat examples"]],
        "examples": ["debug this stack trace in my python code", "tell me a joke about cats", "refactor this function for me"],
    },
    {
        "id": "tag", "icon": "tag", "tab": "Free / paid", "model": "chat-tiered",
        "tag": "Per-user tier",
        "why": "Give different users different models from one endpoint — e.g. free users a cheap model, paid users a premium one — based on a label on the request, not the prompt.",
        "how": "Routes by a tag on the request, not the prompt — free users to the cheap model, paid users to the premium one. (Tags are sent via the API; the dropdown picker just selects the group.)",
        "routes": [["FREE", "groq-gpt-oss-20b", "free + default"], ["PAID", "azure-gpt-mini", "paid tier"]],
        "examples": [],
    },
    {
        "id": "load", "icon": "load", "tab": "Load-balance", "model": "cheap-chat",
        "tag": "Load-balancing",
        "why": "Spread traffic across equivalent deployments for throughput and resilience, and use a different strategy for this group than for the rest of the gateway.",
        "how": "cheap-chat sits in a routing group with latency-based routing, so each request goes to whichever deployment (Groq or Azure) has answered fastest recently. Every other model keeps the global simple-shuffle strategy.",
        "routes": [["FASTEST", "groq-gpt-oss-20b", "usually wins"], ["SLOWER", "azure-gpt-mini", "used when faster"]],
        "examples": ["say hi"],
    },
    {
        "id": "budget", "icon": "budget", "tab": "Provider budget", "model": "cheap-chat",
        "tag": "Cost governance",
        "why": "Cap daily spend per provider. When a provider's budget runs out, traffic automatically shifts to another — a hard guardrail that protects the bill.",
        "how": "Caps spend per provider (e.g. $100/day to Groq). Once a provider's budget is used up, the router stops sending it traffic and falls back to another — spend governance, applied across all routing.",
        "routes": [["OK", "azure within budget", "→ used"], ["OVER", "groq over budget", "→ dropped → fallback"]],
        "examples": [],
    },
    {
        "id": "priority", "icon": "priority", "tab": "Priority failover", "model": "gpt-priority",
        "tag": "Primary + backup",
        "why": "Always use the preferred deployment, and switch to a backup only when it fails. This is the primary/backup pattern the production plan uses for two Azure deployments.",
        "how": "Both deployments share the name gpt-priority. Azure has order 1 and serves every request; Groq has order 2 and is tried only when Azure errors or times out.",
        "routes": [["PRIMARY", "azure-gpt-mini", "order 1"], ["BACKUP", "groq-gpt-oss-120b", "order 2"]],
        "examples": ["summarise the benefits of an LLM gateway in two lines"],
    },
    {
        "id": "mirror", "icon": "mirror", "tab": "Mirror test", "model": "mirror-demo",
        "tag": "Silent A/B test",
        "why": "Test a cheaper model on real prompts before switching to it, with zero risk: users always get the current model's answer.",
        "how": "Each request is answered by Azure. In the background LiteLLM sends a copy to groq-gpt-oss-20b (the silent model); its cost and latency show up in logs and spend tracking for comparison. Mirrored calls are billed too.",
        "routes": [["ANSWER", "azure-gpt-mini", "what the user sees"], ["SHADOW", "groq-gpt-oss-20b", "silent copy"]],
        "examples": ["explain what an API gateway does"],
    },
    {
        "id": "health", "icon": "health", "tab": "Health checks", "model": "gemma",
        "tag": "Proactive reliability",
        "why": "Stop sending users to a model that is already broken (expired key, server down) instead of finding out when their request fails.",
        "how": "Every 5 minutes LiteLLM sends a tiny test call to each deployment and routes away from failing ones. Gemma is currently unhealthy, so a request to it falls back to Azure after a 10-second timeout.",
        "routes": [["HEALTHY", "azure / groq models", "in rotation"], ["UNHEALTHY", "gemma (server down)", "→ fallback"]],
        "examples": ["say hi"],
    },
]


STRATEGIES_GUIDE = """## 🧭 LiteLLM Routing Strategies — quick guide

There are **two kinds** of routing in this gateway.

**A) Load-balancing** — picks *which copy* of a model handles the call (doesn't read the prompt):
- **Simple-shuffle** *(default)* — random pick, weighted by each deployment's capacity. Lowest overhead.
- **Weighted shuffle** — explicit weights per deployment (e.g. 90/10 canary rollout).
- **Least-busy** — the deployment with the fewest in-flight requests.
- **Usage-based** — the one with the lowest token usage this minute (needs Redis).
- **Usage-based v2** — rate-limit-aware: skips any deployment near its TPM/RPM limit (needs Redis).
- **Latency-based** — the fastest-responding deployment.
- **Cost-based** — the cheapest deployment for the request.
- **Provider-budget** — caps spend per provider; once the budget is hit, stops routing to it.
- **Custom** — your own Python logic (by tenant, region, time-of-day…).

**B) Content / quality / cost-aware** — picks *which model* should handle the request (reads the prompt):
- **🧠 Complexity Router** — scores how hard the prompt is → SIMPLE→cheap … REASONING→premium. Rule-based, zero tuning. *The "cheap when good enough" answer.*
- **🎯 Quality Router** — maps difficulty to a quality tier; a keyword (e.g. "legal", "security") can force the top model.
- **📈 Adaptive Router** — learns from real traffic which model gives the best quality-per-dollar per task type.
- **🧭 Semantic Router** — routes by the *meaning* of the prompt (embeddings) — e.g. coding → Claude, chat → Gemma.
- **🏷️ Tag-based** — routes by a label on the request (free vs paid user, or a team).

**C) Reliability and testing:**
- **🥇 Priority failover**: a primary deployment with a backup that is used only when the primary fails (`order`).
- **⚖️ Routing groups**: a different strategy for one group (here latency-based for `cheap-chat`) while the rest keeps the default.
- **🪞 Traffic mirroring**: users get one model's answer while a silent copy goes to another model for comparison.
- **🩺 Health checks**: background test calls remove broken deployments before users hit them.
- Always on: **fallbacks** (try a backup model on failure), **retries**, **cooldowns** (skip a failing model for a while), and **timeouts**.

👉 Pick a router from the buttons below and chat — each answer shows **which model handled it and why**.
"""


async def fetch_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{LITELLM_BASE}/v1/models", headers=HEADERS)
            ids = sorted(m["id"] for m in r.json().get("data", []))
            # routers first, then everything else
            routers = [m for m in ids if m in ROUTERS]
            others = [m for m in ids if m not in ROUTERS]
            return routers + others
    except Exception as e:
        return [f"(could not reach LiteLLM: {e})"]


def provider_label(api_base: str) -> str:
    if not api_base:
        return "?"
    if GEMMA_HOST and GEMMA_HOST in api_base:
        return "Gemma (self-hosted)"
    if "groq" in api_base:
        return "Groq"
    if "azure" in api_base:
        return "Azure"
    return api_base


def routing_reason(requested_model: str) -> str | None:
    """Best-effort: pull the Complexity Router decision from the proxy logs.
    Only meaningful for smart-router (and any complexity router), and only when the
    docker CLI is available."""
    if requested_model not in ("smart-router",) or not DOCKER_CLI:
        return None
    try:
        out = subprocess.run(
            ["docker", "logs", LITELLM_CONTAINER, "--tail", "40"],
            capture_output=True, text=True, timeout=8,
        )
        text = (out.stdout or "") + (out.stderr or "")
        lines = [l for l in text.splitlines() if "ComplexityRouter: tier" in l]
        if lines:
            return lines[-1].split("ComplexityRouter: ", 1)[-1].strip()
    except Exception:
        return None
    return None


def budget_note():
    """Best-effort: surface a provider-budget block from the proxy logs, in plain $.
    Only when the docker CLI is available."""
    if not DOCKER_CLI:
        return None
    try:
        out = subprocess.run(
            ["docker", "logs", LITELLM_CONTAINER, "--tail", "15"],
            capture_output=True, text=True, timeout=8,
        )
        text = (out.stdout or "") + (out.stderr or "")
        last = None
        for line in text.splitlines():
            m = re.search(
                r"Exceeded budget for provider (\S+?):\s*([\d.eE+-]+)\s*>=\s*([\d.eE+-]+)", line
            )
            if m:
                last = m
        if last:
            prov, spend, limit = last.group(1), last.group(2), last.group(3)
            return (
                f"⚠️ **Provider budget hit:** `{prov}` spent **{fmt_money(spend)}** "
                f"of its **{fmt_money(limit)}** cap → request routed to a fallback provider."
            )
    except Exception:
        return None
    return None


def complexity_reason(headers) -> str | None:
    """Complexity Router decision, read from its x-litellm-complexity-router-* response headers."""
    tier = headers.get("x-litellm-complexity-router-tier")
    if not tier:
        return None
    parts = [f"tier={tier}"]
    score = headers.get("x-litellm-complexity-router-score")
    if score:
        parts.append(f"score={score}")
    cause = headers.get("x-litellm-complexity-router-cause")
    if cause:
        parts.append(f"cause={cause}")
    return ", ".join(parts)


def quality_reason(headers) -> str | None:
    """Quality Router decision, read from its x-litellm-quality-router-* response headers."""
    tier = headers.get("x-litellm-quality-router-tier")
    if not tier:
        return None
    parts = [f"quality tier {tier}"]
    keyword = headers.get("x-litellm-quality-router-keyword")
    complexity = headers.get("x-litellm-quality-router-complexity")
    if keyword:
        parts.append(f"keyword '{keyword}'")
    elif complexity:
        parts.append(f"complexity {complexity}")
    via = headers.get("x-litellm-quality-router-via")
    if via:
        parts.append(f"via {via}")
    return " · ".join(parts)


@cl.password_auth_callback
def auth_callback(username: str, password: str):
    """Single shared login for the internal demo. Creds come from chainlit_app/.env
    (APP_USERNAME / APP_PASSWORD); CHAINLIT_AUTH_SECRET must also be set there."""
    expected_user = os.environ.get("APP_USERNAME", "tungsten")
    expected_pass = os.environ.get("APP_PASSWORD", "")
    if expected_pass and username == expected_user and password == expected_pass:
        return cl.User(identifier=username, metadata={"role": "viewer"})
    return None


@cl.on_chat_start
async def start():
    if not LITELLM_KEY:
        await cl.Message(
            content=("❌ No LiteLLM key configured. Create a virtual key for this UI and set "
                     "`CHAINLIT_LITELLM_API_KEY` in `.env` (see README), then restart Chainlit."),
            author="error",
        ).send()
        return
    models = await fetch_models()
    initial = models.index("smart-router") if "smart-router" in models else 0
    settings = await cl.ChatSettings(
        [Select(id="model", label="Router / Model", values=models, initial_index=initial)]
    ).send()
    cl.user_session.set("model", "smart-router")
    card = cl.CustomElement(name="StrategyCard", props={"strategies": STRATEGY_CARDS, "active": "complexity"})
    await cl.Message(
        content=(
            f"**LiteLLM Routing** · `{LITELLM_BASE}` — pick a strategy, then chat (or click an example). "
            "Each answer shows which model handled it and why. (⚙️ has the full model list.) "
            "Tap **📖 Routing strategies** below for a plain-English guide to all of them."
        ),
        author="system",
        elements=[card],
        actions=router_actions(),
    ).send()


@cl.on_settings_update
async def on_settings(settings):
    cl.user_session.set("model", settings["model"])
    await cl.Message(content=f"Switched to **{settings['model']}**.", author="system").send()


# Friendly name + one-line "why" for the per-answer routing panel
STRATEGY_BRIEF = {
    "smart-router":    ("Complexity Router", "picked the tier matching the prompt's difficulty — cheap for easy, premium for hard"),
    "quality-router":  ("Quality Router", "picked a model for the required quality tier; a keyword can force the top model"),
    "adaptive-router": ("Adaptive Router", "used what it has learned about quality-per-cost for this kind of task"),
    "semantic-router": ("Semantic Router", "matched the prompt's meaning to a route"),
    "chat-tiered":     ("Tag-based routing", "routed by the request's tag (free vs paid)"),
    "cheap-chat":      ("Load-balancing", "picked the fastest deployment (latency-based routing group)"),
    "gpt-priority":    ("Priority failover", "order 1 (Azure) serves every request; Groq is used only if Azure fails"),
    "mirror-demo":     ("Traffic mirroring", "Azure answered; a silent copy went to groq-gpt-oss-20b for comparison"),
    "gemma":           ("Health-checked model", "self-hosted Gemma; if it is down the request falls back to Azure"),
}

# Which tier the Complexity / Quality routers assign each model (explains the "why")
SMART_TIER = {
    "gemma": "SIMPLE tier — easy prompt", "azure-gpt-mini": "MEDIUM tier — moderate",
    "groq-gpt-oss-120b": "COMPLEX tier — heavy/technical", "claude-opus": "REASONING tier — hardest",
    "groq-qwen3": "REASONING tier — fallback",
}
QUALITY_TIER = {
    "gemma": "quality tier 1", "azure-gpt-mini": "quality tier 2",
    "groq-gpt-oss-120b": "quality tier 3", "groq-qwen3": "quality tier 3",
    "claude-opus": "quality tier 4 — top (keyword/important)",
}

# Cache: litellm model-id (hash) -> friendly model_name, resolved via /model/info
_MODEL_IDS = {}


async def model_ids():
    global _MODEL_IDS
    if _MODEL_IDS:
        return _MODEL_IDS
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{LITELLM_BASE}/model/info", headers=HEADERS)
        for m in r.json().get("data", []):
            mid = (m.get("model_info") or {}).get("id")
            if mid:
                _MODEL_IDS[mid] = m.get("model_name")
    except Exception:
        pass
    return _MODEL_IDS


@cl.on_message
async def on_message(message: cl.Message):
    model = cl.user_session.get("model") or "smart-router"
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(
                f"{LITELLM_BASE}/v1/chat/completions",
                headers=HEADERS,
                json={"model": model, "messages": [{"role": "user", "content": message.content}]},
            )
        latency = time.time() - t0
        if r.status_code != 200:
            await cl.Message(content=f"❌ {r.status_code}: {r.text[:500]}", author="error").send()
            return
        j = r.json()
        answer = j["choices"][0]["message"]["content"]
    except Exception as e:
        await cl.Message(content=f"❌ request failed: {e}", author="error").send()
        return

    # --- metadata from response + headers ---
    served_by = provider_label(r.headers.get("x-litellm-model-api-base", ""))
    adaptive = r.headers.get("x-litellm-adaptive-router-model")
    quality_model = r.headers.get("x-litellm-quality-router-model")
    cost = r.headers.get("x-litellm-response-cost")
    usage = j.get("usage", {}) or {}
    # LiteLLM v1.102+ returns the Complexity Router decision in headers; fall back to logs.
    reason = complexity_reason(r.headers) or routing_reason(model)

    # --- routing panel FIRST — so "which model & why" is always visible above the answer ---
    name, why = STRATEGY_BRIEF.get(model, (f"`{model}`", "routed to a deployment"))

    ids = await model_ids()
    chosen = ids.get(r.headers.get("x-litellm-model-id", "")) or adaptive or quality_model
    model_disp = f"`{chosen}` · via {served_by}" if chosen else served_by

    decision = None
    if model == "smart-router":
        decision = SMART_TIER.get(chosen)
    elif model == "quality-router":
        decision = quality_reason(r.headers) or QUALITY_TIER.get(chosen)
    elif model == "semantic-router":
        decision = "matched by meaning (embeddings)"
    elif model == "chat-tiered":
        decision = "by request tag (free / paid)"
    elif model == "adaptive-router":
        decision = "learned best quality-per-cost for this task type"
    elif model == "cheap-chat":
        decision = "fastest recent deployment (latency-based)"
    elif model == "gpt-priority":
        decision = ("primary (order 1)" if "Azure" in served_by
                    else "backup (order 2): the primary failed")
    elif model == "mirror-demo":
        decision = "answered by Azure; silent copy sent to groq-gpt-oss-20b"
    elif model == "gemma":
        decision = ("served by Gemma" if "Gemma" in served_by
                    else "Gemma unavailable: fell back to another model")
    if reason:
        decision = f"`{reason}`"

    usage_str = (
        f"{usage.get('total_tokens', '?')} "
        f"(in {usage.get('prompt_tokens', '?')} / out {usage.get('completion_tokens', '?')})"
    )
    try:
        cv = float(cost) if cost not in (None, "") else None
    except (TypeError, ValueError):
        cv = None
    if cv is None or cv == 0:
        cost_str = "**$0** — self-hosted / free" if "Gemma" in served_by else "$0 / not reported"
    else:
        cost_str = f"**{fmt_money(cv)}** per call · {fmt_money(cv * 1000)} / 1k calls"

    rows = [f"| 🤖 **Model used** | {model_disp} |"]
    if decision:
        rows.append(f"| 🧠 **Why** | {decision} |")
    rows.append(f"| 🔢 **Tokens** | {usage_str} |")
    rows.append(f"| 💲 **Cost** | {cost_str} |")
    rows.append(f"| ⚡ **Latency** | {latency:.2f}s |")

    panel = (
        f"#### 🧭 {name}\n"
        f"_{why}._\n\n"
        f"| | |\n|:--|:--|\n" + "\n".join(rows)
    )
    bnote = budget_note()
    if bnote:
        panel += f"\n\n{bnote}"

    await cl.Message(content=panel, author="routing", actions=router_actions()).send()

    # --- the actual answer (below the routing panel) ---
    await cl.Message(content=answer).send()
