#!/usr/bin/env python3
"""Ask one model the triage questions about every labelled host; write results/answers-<name>.json.

  TYPESAFE_API_KEY=... python3 ask.py jev --model jev-latest            # Jev over the TypeSafe API (2 requests per host)
  python3 ask.py decider --model-dir .decider/models/<name> --device mlx  # a Strands decider, in-process on this machine

Hosts already in the output file are skipped, so a run can be resumed. The key is read from the environment, never argv.
"""
import argparse, csv, json, os, sys, time

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arm", choices=("jev", "decider"))
    ap.add_argument("--model", default="jev-latest", help="Jev model name")
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
        name, post_fn = a.model, None
        meta = {"model": name, "source": "TypeSafe API (%s)" % triage.URL.replace("https://", "")}
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
