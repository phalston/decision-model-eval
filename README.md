# decision-model-eval: Jev vs the Strands decider

*Decision models* answer a fixed question with a typed result (a choice among options, a score on a scale, or a yes/no probability) and a confidence, instead of free text. This repo compares a hosted decision model with two open-weight ones that run on a laptop, plus a general chat model as a baseline, on the same questions:

| model | id | what it is | where it ran |
|---|---|---|---|
| **Jev** | `jev-latest` | TypeSafe's hosted decision model ([docs](https://docs.typesafe.ai)); the questions were written against the Jev 1.13 docs | TypeSafe API |
| **Strands decider 2B** | [`strands-decider-2B-qwen3.5-v1-2610`](https://huggingface.co/StrandsAgents/strands-decider-2B-qwen3.5-v1-2610) | open-weight [Strands decider](https://github.com/strands-labs/strands-decider): a LoRA adapter and readout head on Qwen3.5-2B-Base | in-process, MLX on an Apple M1 Pro (32 GB) |
| **Strands decider E4B** | [`strands-decider-E4B-gemma4-v1-2610`](https://huggingface.co/StrandsAgents/strands-decider-E4B-gemma4-v1-2610) | the same design on Google Gemma 4 E4B-it | in-process, MLX on the same Mac |
| **Sonnet** (baseline) | `claude-sonnet-5-5` | Anthropic's general model, given one plain prompt asking for JSON | Anthropic API |

The Strands deciders accept the same request shape as Jev, so one piece of code asks all three decision models.

**The test task: classifying DNS hostnames.** A home Pi-hole forwards a few hundred distinct hostnames a week, and a weekly job asks Jev what each one is for, then writes block proposals for a person to approve (nothing is applied automatically). The question here is whether a free local decider could replace the paid, hosted call, and whether a bigger decider closes the gap. Every model answered about the same 36 hostnames with known answers: 25 ad or tracker domains and 11 legitimate ones.

## Short answer

**No, not on this task.** The E4B decider doubles the 2B's catch rate, but both stay far behind Jev and Sonnet. Under the weekly job's decision rule neither decider would propose a single block. No model ever flagged a legitimate host.

| ad/tracker hosts caught (of 25) · legit hosts caught (of 11) | Jev | Sonnet | Strands 2B | Strands E4B |
|---|---|---|---|---|
| Category is advertising, tracking or malicious | 24 · 0 | 25 · 0 | 7 · 0 | 14 · 0 |
| P(ad-tech) >= 0.5 | 22 · 0 | 22 · 0 | 10 · 0 | 11 · 0 |
| Unwanted score >= 2.5 (0-4 scale) | 18 · 0 | 21 · 0 | 0 · 0 | 5 · 0 |
| **Proposed for block under the weekly rule** | **20 · 0** | n/a | **0 · 0** | **0 · 0** |

Full tables, speed and cost, and every answer side by side: [`results/report.md`](results/report.md).

## What the results say

- **The limit is what the model knows, not how it is asked.** A bare hostname such as `openx.net` or `rubiconproject.com` carries no evidence of its own; the model has to already know the company. On the ad exchanges the E4B misses, its yes/no "is this ad-tech?" answer is low too (media.net 0.35, criteo.com 0.44, bidswitch.net 0.27, openx.net 0.13, rubiconproject.com 0.08), so it is not just choosing "unknown" too readily.
- **Bigger helps, but not on every host.** From the 2B to the E4B, 9 hosts moved into a block category (including googlesyndication.com, adnxs.com, pubmatic.com, taboola.com and moatads.com) and 2 moved out (criteo.com and criteo.net).
- **The deciders are less sure, and less stable.** Median category confidence (the lower of the two option orders) is 0.99 for Jev, 0.47 for the 2B and 0.40 for the E4B. Reversing the option order changed the category for 0 of 36 hosts with Jev, 3 with the 2B and 5 with the E4B.
- **Local is free but not fast on this Mac.** Per host (two requests): 2B 654 ms, E4B 2193 ms, both in-process on an M1 Pro. Jev took 304 ms over the network and bills about 1,250 tokens per host.

This task is close to a worst case for a small model, because the answer is outside the input. Tasks where the evidence is in the text (routing a support ticket, say) may favour a local decider far more; this study does not test that.

## Method

Every model gets the same three questions about `DNS hostname: <name>` ([`triage.py`](triage.py)):

1. **Purpose** (choice): advertising, tracking, telemetry, malicious, content, service or unknown, each with a one-line description.
2. **Unwanted** (score, 0-4): essential · useful first-party · third-party analytics or telemetry · ad serving or cross-site tracking · malicious.
3. **Ad-tech** (yes/no probability): is it operated by an advertising or ad-tech company?

Jev and the deciders are asked twice, with the purpose options in opposite orders, because Jev's documentation warns that Choice favours the first-listed option. The weekly job's rule, `triage.judge()`, proposes a block only when both orders give the same block category (advertising, tracking or malicious), the lower confidence is at least 0.85, and the ad-tech probability is at least 0.5 or the unwanted score at least 2.5. Anything uncertain goes to review; the rule never unblocks.

Sonnet was asked once, with this prompt (no option descriptions, so its wording differs from the others'):

```
You classify DNS hostnames for a home ad blocker. Hostname: <name>

Answer three questions and reply with ONLY a JSON object and no other text:
{"category": one of advertising|tracking|telemetry|malicious|content|service|unknown,
 "unwanted": number 0-4 (0 essential, 1 useful first-party or infrastructure, 2 third-party analytics or telemetry, 3 ad serving or cross-site tracking, 4 malicious),
 "adtech_probability": number 0-1 (is it run by an advertising or ad-tech company),
 "confidence": number 0-1 (your confidence in the category)}
```

Because the four models were asked in different ways and "confidence" means different things (a calibrated probability for Jev and the deciders, a number Sonnet writes, never below 0.70 here), section 2 of the report compares **raw answers only**: forward option order, no confidence threshold.

## Caveats

- **36 hosts is a small sample.** A difference of one or two hosts is noise.
- **Different dates.** Sonnet answered on 2026-10-04. Jev answered 4 of the legit hosts on 2026-10-04 and the other 32 hosts on 2026-10-18. The deciders answered on 2026-10-18.
- **The labels are well-known domains**, chosen by hand. Real traffic has a long tail of obscure names, where knowledge matters even more.
- **The thresholds were not tuned** for any model; they are the weekly job's, set before this test. Tuning them on these 36 hosts would be fitting to the test.
- **The household's own weekly hostname list is not published.** The original comparison also ran on 232 hostnames the Pi-hole forwarded in one week (agreement between Jev and either decider: 91%, mostly both "quiet"); that list shows what a household uses, so it stays private.
- The decider's MLX backend is tested upstream only on Qwen3.5; the E4B (Gemma 4) ran on it here without errors, after the checks in `setup-decider.sh`.

## Reproduce

Report only, from the published answers (standard-library Python 3):

```bash
python3 compare.py
```

Ask a local decider again (Apple silicon; the first run downloads the model):

```bash
bash setup-decider.sh e4b
HF_HUB_OFFLINE=1 .decider/venv/bin/python ask.py decider --model-dir .decider/models/strands-decider-E4B-gemma4-v1-2610 --device mlx
```

Ask Jev again (needs a TypeSafe key; 2 requests per host). Delete `results/answers-jev-latest.json` first, or only missing hosts are asked:

```bash
TYPESAFE_API_KEY=... python3 ask.py jev --model jev-latest
```

Pins: strands-decider code `930e6d5`; 2B at `216d1ccb`, base `Qwen/Qwen3.5-2B-Base` at `b1485b2f`; E4B at `1344d443` (tag 261009), base `google/gemma-4-E4B-it` at `ee0ef602`. `setup-decider.sh` checks the model files against the repo's `MANIFEST.sha256` and its `provenance.json`.

## Files

| path | what |
|---|---|
| `triage.py` | the questions, the API call and `judge()`, as used by the weekly job |
| `ask.py` | asks Jev or a local decider about every labelled host |
| `compare.py` | builds `results/report.md` from the answer files |
| `setup-decider.sh` | installs a pinned decider and checks its files |
| `data/labelled-hosts.csv` | the 36 hostnames and their expected label (ad, tracker, legit) |
| `results/answers-*.json` | every model's raw answers, with timings and token counts |
| `results/report.md` | the full comparison |
