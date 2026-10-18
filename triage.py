#!/usr/bin/env python3
"""The questions, the API call and the decision rule shared by every model in this study.

Extracted unchanged from a home Pi-hole's weekly triage script, which asks Jev about the hostnames the Pi-hole
forwarded that week and writes block PROPOSALS for a person to approve. Nothing is ever applied automatically.

Built around Jev 1.13's documented weaknesses (docs.typesafe.ai/model-jaggedness/jev-1.13):
  - Choice favours the first-listed option -> every hostname is asked twice, categories in opposite order; disagreement = review.
  - Adversarial content: a hostname is attacker-controlled text -> instruction-like names are flagged for review, and the
    model is only ever used to propose BLOCKS (never to allow or unblock anything).
  - Score levels are weak numerically -> Score is only compared with a threshold, never used as a magnitude.
  - Small state (one hostname) and explicit per-option criteria, as the page recommends.
"""
import json, re, time, urllib.request, urllib.error

URL = "https://api.typesafe.ai/v1/systemone"
CATEGORIES = [
    ("advertising", "Ad serving, ad exchanges, real-time bidding, ad measurement or ad verification"),
    ("tracking", "User tracking, analytics, attribution, session replay, fingerprinting"),
    ("telemetry", "Crash reporting or device/app diagnostics sent to a vendor"),
    ("malicious", "Malware, phishing, command-and-control, or algorithmically generated random-looking names"),
    ("content", "CDN, media, images, fonts, static assets or APIs a site or app needs to display content"),
    ("service", "A first-party service, login, update, sync, messaging or infrastructure a user needs"),
    ("unknown", "Cannot tell from the name"),
]
PURPOSE = "What is the main purpose of this DNS hostname?"
UNWANTED = {"type": "score", "instructions": "How unwanted is this hostname on a typical home network?",
            "criteria": ["Essential: a site or app breaks without it", "Useful first-party or infrastructure service",
                         "Third-party analytics or telemetry", "Ad serving or cross-site tracking", "Malicious or clearly abusive"]}
ADTECH = {"type": "noul", "instructions": "Is this hostname operated by an advertising or ad-tech company (ad server, exchange, DSP, SSP or ad verification)?"}
BLOCK = ("advertising", "tracking", "malicious")
MIN_CONF = 0.85
SUSPICIOUS = re.compile(r"(ignore|instruction|prompt|assistant|system-?message|trusted|verified|whitelist|allow-?list|not-?an?-?ad|no-?ads?\b|safe-?to)", re.I)


def choice_q(reverse):
    items = list(reversed(CATEGORIES)) if reverse else CATEGORIES
    return {"type": "choice", "instructions": PURPOSE, "criteria": dict(items)}


def post(body, key):
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json", "Authorization": "Bearer " + key})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise SystemExit("auth failed (HTTP %d): check the TypeSafe key" % e.code)
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt * 2); continue
            return {"error": "HTTP %d" % e.code}
        except Exception as e:
            if attempt < 3:
                time.sleep(2 ** attempt); continue
            return {"error": type(e).__name__}


def ask(host, key, model, post_fn=None):
    """post_fn(body) -> response dict; defaults to the TypeSafe API. ask_decider.py passes a local Strands decider."""
    post_fn = post_fn or (lambda body: post(body, key))
    state = "DNS hostname: " + host
    fwd = post_fn({"state": state, "model": model, "questions": {"purpose": choice_q(False), "unwanted": UNWANTED, "is_adtech": ADTECH}})
    rev = post_fn({"state": state, "model": model, "questions": {"purpose": choice_q(True)}})
    if "error" in fwd or "error" in rev:
        return {"error": fwd.get("error") or rev.get("error")}
    a, b = fwd["answers"], rev["answers"]["purpose"]
    return {"category": a["purpose"]["choice"], "cat_conf": a["purpose"]["confidence"],
            "category_rev": b["choice"], "cat_conf_rev": b["confidence"],
            "unwanted": a["unwanted"]["score"], "p_adtech": a["is_adtech"]["noul"],
            "in_tokens": fwd["usage"]["input_tokens"] + rev["usage"]["input_tokens"],
            "out_tokens": fwd["usage"]["output_tokens"] + rev["usage"]["output_tokens"], "ts": int(time.time())}


def judge(host, r):
    """Return (verdict, reasons). verdict: block | review | quiet. Never 'allow': Jev does not unblock anything."""
    reasons = []
    cats = {r["category"], r["category_rev"]}
    stable = r["category"] == r["category_rev"]
    block_cat = bool(cats & set(BLOCK))
    signal = r["p_adtech"] >= 0.5 or r["unwanted"] >= 2.5
    confident = min(r["cat_conf"], r["cat_conf_rev"]) >= MIN_CONF
    flagged_name = bool(SUSPICIOUS.search(host))
    if flagged_name:
        reasons.append("hostname contains instruction-like wording; treat the model's answer with suspicion")
    if block_cat and not stable:
        reasons.append("category changed when the option order was reversed (%s vs %s)" % (r["category"], r["category_rev"]))
    if block_cat and stable and not confident:
        reasons.append("%s but confidence only %.2f / %.2f" % (r["category"], r["cat_conf"], r["cat_conf_rev"]))
    if block_cat and stable and confident and not signal:
        reasons.append("category says %s but neither the ad-tech question nor the score agrees" % r["category"])
    if not block_cat and signal:
        reasons.append("category is %s but ad-tech probability %.2f / unwanted score %.1f point to blocking" % (r["category"], r["p_adtech"], r["unwanted"]))
    if r["category"] == "telemetry" or r["category_rev"] == "telemetry":
        reasons.append("vendor telemetry: your call whether you mind it")
    if block_cat and stable and confident and signal and not flagged_name:
        return "block", ["both option orders say %s (confidence %.2f / %.2f), ad-tech %.2f, unwanted %.1f" %
                         (r["category"], r["cat_conf"], r["cat_conf_rev"], r["p_adtech"], r["unwanted"])]
    return ("review", reasons) if reasons else ("quiet", [])
