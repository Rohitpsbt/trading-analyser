"""
Thesis drafter.

Assembles the quantitative screen, catalyst, credibility flag and red-team
report into a single skeptical prompt and asks an LLM to produce a structured
thesis — bull case, bear case, explicit red-team answers, conviction, suggested
action, and (non-negotiable for catalyst trades) EXIT conditions.

If no LLM key/network is available, it falls back to an offline structured
template assembled purely from the numbers — no narrative, but every field the
ledger needs, so the pipeline always completes.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import date
import json
import re

import config
from screening import ScreenResult
from credibility import CredibilityResult
from redteam import RedTeamReport, CHECKLIST


@dataclass
class Thesis:
    symbol: str
    name: str
    as_of: str
    catalyst: str
    conviction: str                 # LOW | MEDIUM | HIGH
    suggested_action: str           # WATCH | BUY_CANDIDATE | TRIM | AVOID
    reference_price: float | None
    fundamental_summary: str
    credibility_flag: str
    bull_case: str
    bear_case: str
    exit_conditions: str
    redteam: dict[str, str] = field(default_factory=dict)
    narrated: bool = True           # False if offline template was used
    source: str = ""                # which model produced this, e.g. "groq:llama-3.1-8b-instant"
    # When part of a multi-model second opinion, the human-readable points where
    # the models disagreed (empty if they agreed or this was a solo draft).
    disagreements: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


SYSTEM_PROMPT = """You are a deliberately skeptical equity analyst for Indian
markets running a thematic catalyst-swing strategy (weeks-to-months horizon).

Hard rules:
- You produce ANALYSIS, not orders. A human reviews and decides.
- Be adversarial toward the bull case. The credibility flag and red-team report
  are provided; if credibility is CAUTION, explicitly discount management's
  optimistic narrative.
- Price often runs AHEAD of fundamentals in thematic moves; if the stock has
  already run, say the entry is poor even if the theme is real.
- For catalyst trades, EXIT discipline matters more than entry. Always specify
  concrete exit conditions (target, stop, and thesis-invalidation trigger).
- Never output a confidence percentage; use LOW/MEDIUM/HIGH conviction with reasons.
Return ONLY valid JSON with keys: conviction, suggested_action,
fundamental_summary, bull_case, bear_case, exit_conditions, redteam.
'redteam' must be an object keyed by: """ + ", ".join(k for k, _ in CHECKLIST) + "."


def _build_user_prompt(screen: ScreenResult, cred: CredibilityResult,
                       rt: RedTeamReport, catalyst: str, ref_price) -> str:
    return f"""STOCK: {screen.symbol} ({screen.name})
REFERENCE PRICE: {ref_price}
CATALYST / LINKAGE CONTEXT: {catalyst or 'none supplied'}

FUNDAMENTAL SCREEN (score {screen.score}/100, passed={screen.passed}):
metrics: {json.dumps(screen.metrics, default=str)}
checks: {json.dumps(screen.checks)}
notes: {screen.notes}

CREDIBILITY FLAG: {cred.flag.value}
reasons: {cred.reasons}
guidance_history: {cred.guidance_history or 'none provided'}

RED-TEAM (automated): {json.dumps(rt.automated, indent=2)}
RED-TEAM (answer these explicitly in your 'redteam' object): {json.dumps(rt.open_questions)}

Draft the thesis as JSON now."""


def _call_llm(system: str, user: str, provider: str | None = None) -> str | None:
    """Call one LLM provider and return its raw text, or None on failure / no key.
    `provider` defaults to the configured one; pass it explicitly to target a
    specific model (used by the multi-model second opinion)."""
    cfg = config.LLM
    provider = (provider or cfg.get("provider") or "none").lower()
    model = config.model_for(provider)  # explicit override or per-provider default
    try:
        if provider == "groq" and cfg.get("groq_api_key"):
            from groq import Groq
            client = Groq(api_key=cfg["groq_api_key"])
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=0.2, response_format={"type": "json_object"})
            return r.choices[0].message.content
        if provider == "gemini" and cfg.get("gemini_api_key"):
            import google.generativeai as genai
            genai.configure(api_key=cfg["gemini_api_key"])
            gmodel = genai.GenerativeModel(
                model, system_instruction=system,
                generation_config={"response_mime_type": "application/json",
                                   "temperature": 0.2})
            r = gmodel.generate_content(user)
            return r.text
        if provider == "anthropic" and cfg.get("anthropic_api_key"):
            import anthropic
            client = anthropic.Anthropic(api_key=cfg["anthropic_api_key"])
            r = client.messages.create(
                model=model, max_tokens=1500, system=system,
                messages=[{"role": "user", "content": user}])
            return r.content[0].text
    except Exception as e:
        print(f"[thesis] {provider} call failed ({e}); using offline template.")
    return None


def _extract_json(raw: str) -> str:
    """Pull a JSON object out of an LLM response that may be fenced (```json …```)
    or wrapped in prose. Groq's JSON mode returns clean JSON; Gemini/others can be
    chattier, so we recover the outermost {...}."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.S)
    if m:
        return m.group(1)
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        return raw[start:end + 1]
    return raw


def _offline_thesis(screen, cred, rt, catalyst, ref_price) -> dict:
    """Deterministic structured thesis from numbers alone — no narrative."""
    flag = cred.flag.value
    already_run = "already_run" in rt.flags
    if screen.passed and flag in ("CREDIBLE", "NEUTRAL") and not already_run:
        conviction, action = "MEDIUM", "BUY_CANDIDATE"
    elif already_run or flag == "CAUTION":
        conviction, action = "LOW", "WATCH"
    else:
        conviction, action = "LOW", "WATCH"
    return {
        "conviction": conviction,
        "suggested_action": action,
        "fundamental_summary": f"Screen {screen.score}/100, passed={screen.passed}. "
                               f"Notes: {'; '.join(screen.notes) or 'none'}",
        "bull_case": f"Catalyst: {catalyst or 'n/a'}. Fundamental checks passing: "
                     f"{[k for k,v in screen.checks.items() if v]}.",
        "bear_case": f"Credibility {flag}: {'; '.join(cred.reasons) or 'n/a'}. "
                     + ("Stock already run — entry risk. " if already_run else ""),
        "exit_conditions": f"Stop {config.RISK['default_stop_pct']:.0%} below entry; "
                           f"trail after +{config.RISK['trail_after_gain_pct']:.0%}; "
                           f"invalidate if catalyst (demand signal) reverses.",
        "redteam": {**rt.automated, **{k: "[needs human/LLM input]"
                                       for k in rt.open_questions}},
    }


def _draft_one(screen: ScreenResult, cred: CredibilityResult, rt: RedTeamReport,
               catalyst: str, ref_price, provider: str | None) -> Thesis:
    """Draft a single thesis from one provider (or the configured default).
    Falls back to the offline template if the provider has no key or errors."""
    user = _build_user_prompt(screen, cred, rt, catalyst, ref_price)
    raw = _call_llm(SYSTEM_PROMPT, user, provider=provider)
    narrated = True
    data: dict
    if raw:
        try:
            data = json.loads(_extract_json(raw))
        except Exception:
            data, narrated = _offline_thesis(screen, cred, rt, catalyst, ref_price), False
    else:
        data, narrated = _offline_thesis(screen, cred, rt, catalyst, ref_price), False

    rt_obj = data.get("redteam", {})
    if not isinstance(rt_obj, dict):
        rt_obj = {"raw": str(rt_obj)}

    resolved = (provider or config.LLM.get("provider") or "none").lower()
    source = f"{resolved}:{config.model_for(resolved)}" if narrated else "offline"

    return Thesis(
        symbol=screen.symbol, name=screen.name, as_of=date.today().isoformat(),
        catalyst=catalyst, conviction=str(data.get("conviction", "LOW")).upper(),
        suggested_action=str(data.get("suggested_action", "WATCH")).upper(),
        reference_price=ref_price,
        fundamental_summary=data.get("fundamental_summary", ""),
        credibility_flag=cred.flag.value,
        bull_case=data.get("bull_case", ""),
        bear_case=data.get("bear_case", ""),
        exit_conditions=data.get("exit_conditions", ""),
        redteam={str(k): str(v) for k, v in rt_obj.items()},
        narrated=narrated,
        source=source,
    )


def draft_thesis(screen: ScreenResult, cred: CredibilityResult, rt: RedTeamReport,
                 catalyst: str = "", ref_price=None, provider: str | None = None) -> Thesis:
    """Single-model thesis (the configured provider unless one is named)."""
    return _draft_one(screen, cred, rt, catalyst, ref_price, provider)


@dataclass
class SecondOpinion:
    """Two independent model views of the same call, plus where they diverge.
    Divergence is itself a signal — agreement raises confidence, disagreement
    says dig deeper before acting."""
    theses: list[Thesis]
    disagreements: list[str] = field(default_factory=list)

    @property
    def agree(self) -> bool:
        return not self.disagreements

    @property
    def narrated_count(self) -> int:
        return sum(1 for t in self.theses if t.narrated)


def _compare(theses: list[Thesis]) -> list[str]:
    """Flag the actionable points where the models differ: conviction and
    suggested action. (Credibility/red-team automated fields are computed before
    the LLM, so they're identical by construction and not compared here.)"""
    out: list[str] = []
    for field_name, label in (("conviction", "Conviction"),
                              ("suggested_action", "Suggested action")):
        vals = {getattr(t, field_name) for t in theses}
        if len(vals) > 1:
            detail = ", ".join(f"{_short_source(t)}={getattr(t, field_name)}"
                               for t in theses)
            out.append(f"{label} differs: {detail}")
    return out


def _short_source(t: Thesis) -> str:
    """'groq:llama-3.1-8b-instant' -> 'groq'; 'offline' -> 'offline'."""
    return t.source.split(":", 1)[0] if t.source else "?"


def draft_second_opinion(screen: ScreenResult, cred: CredibilityResult,
                         rt: RedTeamReport, catalyst: str = "", ref_price=None,
                         providers: tuple[str, ...] = ("groq", "gemini")
                         ) -> SecondOpinion:
    """Draft the same thesis from each provider and compare. Each model's view is
    a full Thesis (with its `source`); the shared `disagreements` are stamped onto
    every thesis so the divergence travels with each ledger row."""
    theses = [_draft_one(screen, cred, rt, catalyst, ref_price, p) for p in providers]
    disagreements = _compare(theses)
    for t in theses:
        t.disagreements = disagreements
    return SecondOpinion(theses=theses, disagreements=disagreements)
