#!/usr/bin/env python3
"""Ask one model the triage questions about every labelled host; write results/answers-<name>.json.

  TYPESAFE_API_KEY=... python3 ask.py jev --model jev-latest            # Jev over the TypeSafe API (2 requests per host)
  python3 ask.py decider --model-dir .decider/models/<name> --device mlx  # a Strands decider, in-process on this machine
  OPENAI_API_KEY=... python3 ask.py openai --model gpt-6-luna           # OpenAI Decisions API (2 requests per host)

Hosts already in the output file are skipped, so a run can be resumed. The key is read from the environment, never argv.
"""
import argparse, csv, json, os, sys, time, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import triage  # noqa: E402


def decider_post_fn(model_dir, device):
    from strands_decider.infer import load_engine
    from strands_decider.schema import SystemOneRequest
    eng = load_engine(model_dir, device=device)

    def post_fn(body):
        try:
            return eng.evaluate(SystemOneRequest(**body)).model_dump()
        except Exception as e:  # one bad host must not stop the run
            return {"error": type(e).__name__ + ": " + str(e)[:200]}
    return post_fn


OPENAI_URL = "https://api.openai.com/v1/decisions"


def openai_body(body):
    """Jev /v1/systemone request -> OpenAI /v1/decisions request. Option and level order are kept (the reverse-order check needs it)."""
    qs = []
    for name, q in body["questions"].items():
        o = {"name": name, "instructions": q["instructions"]}
        if q["type"] == "choice":
            o.update(type="choice", choices=[{"value": v, "description": d} for v, d in q["criteria"].items()])
        elif q["type"] == "score":
            o.update(type="score", levels=[{"label": str(i), "description": d} for i, d in enumerate(q["criteria"])])
        elif q["type"] == "noul":
            o["type"] = "predicate"
        else:
            raise ValueError("no OpenAI type for " + q["type"])
        qs.append(o)
    return {"model": body["model"], "input": body["state"], "questions": qs}


def openai_answers(resp):
    """OpenAI /v1/decisions response -> Jev response shape, so triage.ask() reads it unchanged."""
    out = {}
    for a in resp.get("answers", []):
        t = a.get("type")
        if t == "refusal": return {"error": "refusal"}
        if t == "choice": out[a["name"]] = {"choice": a["choice"], "confidence": a["confidence"]}
        elif t == "score": out[a["name"]] = {"score": a["score"], "confidence": a.get("confidence")}
        elif t == "predicate": out[a["name"]] = {"noul": a["probability"]}
        else: return {"error": "answer type %s" % t}
    u = resp.get("usage") or {}  # not documented by OpenAI's guide: use it when present, else zeros
    return {"answers": out, "usage": {"input_tokens": u.get("input_tokens", 0) or 0, "output_tokens": u.get("output_tokens", 0) or 0}}


def openai_post_fn(key):
    def post_fn(body):
        req = urllib.request.Request(OPENAI_URL, json.dumps(openai_body(body)).encode(),
                                     {"Content-Type": "application/json", "Authorization": "Bearer " + key})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return openai_answers(json.load(r))
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise SystemExit("auth failed (HTTP %d): check the OpenAI key and that it has Decisions API access" % e.code)
                if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(2 ** attempt * 2); continue
                return {"error": "HTTP %d" % e.code}
            except Exception as e:
                if attempt < 3:
                    time.sleep(2 ** attempt); continue
                return {"error": type(e).__name__}
    return post_fn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arm", choices=("jev", "decider", "openai"))
    ap.add_argument("--model", default=None, help="Jev model (default jev-latest) or OpenAI model (default gpt-6-luna)")
    ap.add_argument("--model-dir", help="decider checkpoint directory")
    ap.add_argument("--device", default="mlx", help="decider device: mlx, mps, cuda or cpu")
    ap.add_argument("--labels", default="data/labelled-hosts.csv")
    ap.add_argument("--results", default="results")
    a = ap.parse_args()

    hosts = [r["hostname"].strip().lower() for r in csv.DictReader(open(a.labels))]
    if a.arm == "jev":
        key = os.environ.get("TYPESAFE_API_KEY", "")
        if not key:
            raise SystemExit("TYPESAFE_API_KEY is not set")
        name, post_fn = a.model or "jev-latest", None
        meta = {"model": name, "source": "TypeSafe API (%s)" % triage.URL.replace("https://", "")}
    elif a.arm == "openai":
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise SystemExit("OPENAI_API_KEY is not set")
        name, post_fn = a.model or "gpt-6-luna", openai_post_fn(key)
        meta = {"model": name, "source": "OpenAI Decisions API (%s), public beta" % OPENAI_URL.replace("https://", "")}
    else:
        if not a.model_dir:
            raise SystemExit("decider needs --model-dir")
        name = os.path.basename(os.path.normpath(a.model_dir))
        key, post_fn = None, decider_post_fn(a.model_dir, a.device)
        meta = {"model": name, "source": a.model_dir, "device": a.device}

    out = os.path.join(a.results, "answers-%s.json" % name)
    data = json.load(open(out)) if os.path.exists(out) else dict(meta, hosts={})
    todo = [h for h in hosts if h not in data["hosts"]]
    print("%s: %d hosts, %d to ask" % (name, len(hosts), len(todo)))
    for i, h in enumerate(todo, 1):
        t = time.time()
        r = triage.ask(h, key, name, post_fn=post_fn)
        if "error" in r:
            print("  error", h, r["error"])
            continue
        r["ms"] = round((time.time() - t) * 1000)
        data["hosts"][h] = r
        if i % 10 == 0:
            print("  %d/%d" % (i, len(todo)))
    os.makedirs(a.results, exist_ok=True)
    json.dump(data, open(out, "w"), indent=1)
    print("wrote", out)


if __name__ == "__main__":
    main()
