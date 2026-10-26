# Decision models on a DNS question

*Decision models* answer a fixed question with a typed result (a choice among options, a score on a scale, or a yes/no probability) and a confidence, instead of free text. Code can branch on the answer directly: there is nothing to parse and no prompt to coax.

This repo puts four of them, and one general chat model for reference, to the same small, real job: deciding whether DNS hostnames that slipped past a home [Pi-hole](https://pi-hole.net) ad blocker are ads or trackers.

**Read the results:**

- **[The story](https://phalston.github.io/decision-model-eval/)**: *OpenAI's Decisions API, put to a household test*. A scrolling ([Closeread](https://closeread.dev)) walk through the results, one chart at a time.
- **[The report](https://phalston.github.io/decision-model-eval/report.html)**: *Decision Models on a DNS Question*. The same results as a short read, about four minutes.
- **[`results/report.md`](results/report.md)**: the plain tables, and every model's answer for every hostname.

## The question

Pi-hole only blocks hostnames that are already on its blocklists; anything new resolves. On 4 October 2026 an ad got into an iPhone app on a home network that way. A weekly job already asks TypeSafe's Jev about the household's unfamiliar hostnames and proposes blocks for a person to approve; nothing is blocked automatically. Could another decision model do that job as well, including two free ones that run on a laptop?

| model | id | what it is | where it ran | price |
|---|---|---|---|---|
| **Decisions API** | `gpt-6-luna` | OpenAI's decision model, public beta | OpenAI API | $0.10 per 1M input tokens, output free |
| **Jev** | `jev-latest` | TypeSafe's decision model ([docs](https://docs.typesafe.ai)); the household's current weekly check | TypeSafe API | not published |
| **Strands 2B** | [`strands-decider-2B-qwen3.5-v1-2610`](https://huggingface.co/StrandsAgents/strands-decider-2B-qwen3.5-v1-2610) | open-weight [Strands decider](https://github.com/strands-labs/strands-decider) on Qwen3.5-2B-Base | MLX on an Apple M1 Pro (32 GB) | free |
| **Strands E4B** | [`strands-decider-E4B-gemma4-v1-2610`](https://huggingface.co/StrandsAgents/strands-decider-E4B-gemma4-v1-2610) | the same design on Google Gemma 4 E4B-it | same Mac | free |
| **Sonnet** (reference) | `claude-sonnet-5-5` | Anthropic's general model, one plain prompt asking for JSON | Anthropic API | per token |

## Short answer

**The Decisions API and Jev can both do this job; the small Strands models can't yet.** On 36 hand-labelled hostnames (25 ad or tracker domains, 11 ordinary sites), the Decisions API named a blocking category for all 25 unwanted hosts and Jev for 24. No model ever put an ordinary site in a blocking category.

| ad/tracker hosts caught (of 25) · ordinary sites caught (of 11) | Decisions API | Jev | Sonnet | Strands 2B | Strands E4B |
|---|---|---|---|---|---|
| Category is advertising, tracking or malicious | 25 · 0 | 24 · 0 | 25 · 0 | 7 · 0 | 14 · 0 |
| P(ad-tech) >= 0.5 | 20 · 0 | 22 · 0 | 22 · 0 | 10 · 0 | 11 · 0 |
| Unwanted score >= 2.5 (0-4 scale) | 17 · 0 | 18 · 0 | 21 · 0 | 0 · 0 | 5 · 0 |
| **Proposed for block under the weekly rule** | **16 · 0** | **20 · 0** | n/a | **0 · 0** | **0 · 0** |
| Median confidence (lower of both option orders) | 0.95 | 0.99 | n/a | 0.47 | 0.40 |
| Median time per host (2 requests) | 420 ms | 304 ms | 1410 ms (1 request) | 654 ms | 2193 ms |

## What the results say

- **The Decisions API reads questions literally.** Asked whether an analytics company (Mixpanel, Hotjar, Segment) is ad-tech, it says no, and scores it at the scale's analytics level. Under a rule tuned for Jev that means fewer automatic blocks (16 against 20) and more for a person to review, not more mistakes.
- **It is cheap and the only one with a published price:** about $0.02 for all 263 hostnames asked, household traffic included.
- **The small models are limited by what they know, not by how they are asked.** A bare hostname such as `openx.net` carries no evidence of its own; the model has to know the company already. The E4B doubles the 2B's catch rate, but both are rarely confident enough for a rule to act on, so nearly everything would go to a person.
- **On the household's own traffic** (232 hostnames from two weeks of October, no answer key), Jev proposed 1 block and sent 18 to review; the other models proposed none. The hostnames themselves are not published; [`data/household-summary.json`](data/household-summary.json) holds totals only.

Jev stays the household's weekly check for now, with the Decisions API as a strong second opinion.

## Method

Every model gets the same three questions about `DNS hostname: <name>` ([`triage.py`](triage.py)):

1. **Purpose** (choice): advertising, tracking, telemetry, malicious, content, service or unknown, each with a one-line description.
2. **Unwanted** (score, 0-4): essential · useful first-party · third-party analytics or telemetry · ad serving or cross-site tracking · malicious.
3. **Ad-tech** (yes/no probability): is it operated by an advertising or ad-tech company?

The decision models are asked twice, with the purpose options in opposite orders, because Jev's documentation warns that Choice favours the first-listed option. The weekly rule, `triage.judge()`, proposes a block only when both orders give the same block category (advertising, tracking or malicious), the lower confidence is at least 0.85, and the ad-tech probability is at least 0.5 or the unwanted score at least 2.5. Anything uncertain goes to review; the rule never unblocks.

Sonnet was asked once, with category names but no descriptions, and wrote its numbers as text. Its "confidence" is a number it writes, not a calibrated probability, so it is a reference point rather than a contestant.

## Caveats

- **36 hostnames is a demonstration, not a benchmark.** A difference of one or two hosts is noise, and the labelled hosts are well-known names; real traffic has a long tail of obscure ones.
- **The rule was built for Jev**, before the other models were tested. Its thresholds were not tuned on these hosts. The raw-answer rows above use no rule.
- **Different dates.** Sonnet answered on 4 October 2026; the decision models mostly on 18 October (some of Jev's answers are from 4 October). Run-to-run variation was not measured.
- **The Decisions API is in public beta,** and `gpt-6-luna` may change before general release.
- **No model could look anything up.** Each answered from what it already knew; only hostnames were sent, never device names or addresses.

## Reproduce

Tables from the saved answers (standard-library Python 3):

```bash
python3 compare.py
```

Both pages (needs [Quarto](https://quarto.org) and R with `jsonlite`, `ggplot2`, `knitr` and `rmarkdown`; no API calls). This writes `analysis/*.html` and the published copies in `docs/`:

```bash
bash analysis/render.sh
```

Ask a model again. Hosts already answered are skipped, so delete the answer file first for a full rerun:

```bash
OPENAI_API_KEY=... python3 ask.py openai --model gpt-6-luna
TYPESAFE_API_KEY=... python3 ask.py jev --model jev-latest
bash setup-decider.sh e4b
HF_HUB_OFFLINE=1 .decider/venv/bin/python ask.py decider --model-dir .decider/models/strands-decider-E4B-gemma4-v1-2610 --device mlx
```

Pins: strands-decider code `930e6d5`; 2B at `216d1ccb`, base `Qwen/Qwen3.5-2B-Base` at `b1485b2f`; E4B at `1344d443` (tag 261009), base `google/gemma-4-E4B-it` at `ee0ef602`. `setup-decider.sh` checks the model files against the repo's `MANIFEST.sha256` and its `provenance.json`.

## Your own catalog: `evaluate.py`

`evaluate.py` runs the same kind of comparison on any labelled catalog, described by one task file. It was written for **ticket triage**: tickets filed under the wrong request type ("enable this feature" that is really a new AI agent capability; "trouble deleting an app" that is really a security incident). Would a decision model catch those at intake, and how many good tickets would it bother people about? Unlike a bare hostname, a ticket carries its own evidence, which may suit the small local models better.

1. **Make a task folder:** copy [`tasks/ticket-triage-example/`](tasks/ticket-triage-example/) (14 made-up tickets) to `tasks/<name>/`. Edit `tickets.csv` (an id, the true type, the submitted type, the text) and `task.json` (column mapping, the state template, the question, one criterion per type, `min_confidence`, and `high_stakes` types that must never be waved through).
2. **Ask each model** (each item twice, options in opposite orders):

   ```bash
   TYPESAFE_API_KEY=... python3 evaluate.py ask tasks/<name>/task.json jev --model jev-latest
   python3 evaluate.py ask tasks/<name>/task.json claude --model claude-opus-5-5     # pip install anthropic
   HF_HUB_OFFLINE=1 .decider/venv/bin/python evaluate.py ask tasks/<name>/task.json decider --model-dir .decider/models/strands-decider-E4B-gemma4-v1-2610 --device mlx
   ```

3. **Report:** `python3 evaluate.py report tasks/<name>/task.json` writes `results/<name>/report.md`.

The rule (`evaluate.judge()`) only proposes; a person confirms. If both option orders agree at or above `min_confidence`, it **accepts** a ticket whose submitted type matches and **reclassifies** one that doesn't. Anything else goes to **review**, and so does any ticket where either order names a high-stakes type without a confident, stable answer. The report counts misfiled tickets caught, reclassified, sent to review or missed, and the cost in false alarms on correctly filed ones.

Answer files record a hash of the spec, so answers from a different question are never mixed in. `python3 -m unittest test_evaluate` runs the whole pipeline on canned answers, with no model or network.

**Before using real tickets:** `tasks/*` (except the example) and `results/*/` are gitignored, but asking Jev or Claude sends ticket text to that vendor, so check that's allowed. Ticket text is written by whoever files the ticket and can try to steer the answer, so keep a person in the loop. Use resolved tickets for labels, and a few hundred of them.

## Files

| path | what |
|---|---|
| `triage.py` | the questions, the API call and `judge()`, as used by the weekly job |
| `ask.py` | asks the Decisions API, Jev or a local decider about every labelled host |
| `compare.py` | builds `results/report.md` and `results/verdicts.json` from the answer files |
| `data/labelled-hosts.csv` | the 36 hostnames and their expected label (ad, tracker, legit) |
| `data/household-summary.json` | household totals from the Pi-hole's runs; no hostnames |
| `results/answers-*.json` | every model's raw answers, with timings and token counts |
| `results/report.md` | the full comparison as tables |
| `analysis/` | Quarto sources for the report and the Closeread story, and `render.sh` |
| `docs/` | the published pages (GitHub Pages): `index.html` is the story, `report.html` the report |
| `setup-decider.sh` | installs a pinned Strands decider and checks its files |
| `evaluate.py`, `test_evaluate.py`, `tasks/ticket-triage-example/` | the same comparison for any labelled catalog, its test, and a synthetic example |
