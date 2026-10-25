# Shared data for decision-models.qmd and decision-models-story.qmd. Paths are relative to analysis/.
# Reads only what this repo holds: the 36 labelled hostnames (data/labelled-hosts.csv), every model's answers
# about them (results/answers-*.json), their weekly-rule verdicts (results/verdicts.json, written by compare.py),
# and household TOTALS (data/household-summary.json, exported from the Pi-hole repo; no hostnames).
# Rendering makes no API calls.

suppressPackageStartupMessages({ library(jsonlite); library(ggplot2) })
options(stringsAsFactors = FALSE)
rj <- function(p) if (file.exists(p)) fromJSON(p, simplifyVector = FALSE) else NULL

hosts <- read.csv("../data/labelled-hosts.csv")
hosts$unwanted_host <- hosts$expected %in% c("ad", "tracker")
grp_levels <- c("ad exchange", "tracker", "legitimate")
hosts$group <- factor(hosts$expected, levels = c("ad", "tracker", "legit"), labels = grp_levels)
BLOCK <- c("advertising", "tracking", "malicious")

# The four decision models, all asked the same way (triage.ask: one request with three questions, then the category
# question again with the options in reverse order). Names are display names; values are the answer-file ids.
dm <- c(`Jev` = "jev-latest", `gpt-6-luna` = "gpt-6-luna",
        `Strands 2B` = "strands-decider-2B-qwen3.5-v1-2610", `Strands E4B` = "strands-decider-E4B-gemma4-v1-2610")
num <- function(x) if (is.null(x)) NA_real_ else as.numeric(x)
answers <- do.call(rbind, lapply(names(dm), \(m) {
  f <- rj(sprintf("../results/answers-%s.json", dm[[m]]))
  if (is.null(f)) return(NULL)
  do.call(rbind, lapply(names(f$hosts), \(h) { r <- f$hosts[[h]]
    data.frame(model = m, hostname = h, category = r$category, cat_conf = num(r$cat_conf), category_rev = r$category_rev,
               cat_conf_rev = num(r$cat_conf_rev), unwanted = num(r$unwanted), p_adtech = num(r$p_adtech), ms = num(r$ms),
               tokens_in = num(r$in_tokens), tokens_out = num(r$out_tokens), ts = num(r$ts)) }))
}))
answers$model <- factor(answers$model, levels = names(dm))

# Sonnet: a general language model, one prompt per hostname asking for JSON, answered on 4 Oct.
sf <- rj("../results/answers-sonnet-claude-sonnet-5-5.json")
son <- if (is.null(sf)) NULL else do.call(rbind, lapply(names(sf$hosts), \(h) { r <- sf$hosts[[h]]
  if (is.null(r$category)) return(NULL)
  data.frame(model = "Sonnet", hostname = h, category = r$category, unwanted = num(r$unwanted), p_adtech = num(r$p_adtech),
             conf = num(r$conf), latency_s = num(r$ms) / 1000, tokens_in = num(r$in_tokens), tokens_out = num(r$out_tokens)) }))
have_son <- !is.null(son) && nrow(son) > 0

lab <- merge(hosts, answers, by = "hostname")
lab_all <- rbind(lab[, c("hostname", "group", "unwanted_host", "model", "category", "unwanted", "p_adtech")],
                 if (have_son) merge(hosts, son, by = "hostname")[, c("hostname", "group", "unwanted_host", "model", "category", "unwanted", "p_adtech")])
models_all <- c(names(dm), if (have_son) "Sonnet")
lab_all$model <- factor(lab_all$model, levels = models_all)

# Weekly-rule verdicts on the labelled hosts (triage.judge via compare.py).
vj <- rj("../results/verdicts.json")
vd <- do.call(rbind, lapply(names(dm), \(m) { v <- vj[[dm[[m]]]]; if (is.null(v)) return(NULL)
  data.frame(hostname = names(v), model = m, verdict = unlist(v)) }))
vd <- merge(vd, hosts[, c("hostname", "expected", "unwanted_host")], by = "hostname")
vd$model <- factor(vd$model, levels = names(dm))

# Household totals: every host asked (household weekly lists + the labelled set) as anonymous numbers, and the
# weekly-rule results on the household hosts as counts.
hs <- rj("../data/household-summary.json")
have_hs <- !is.null(hs)
conf_all <- if (have_hs) do.call(rbind, lapply(names(dm), \(m) data.frame(model = m, c = unlist(hs$models[[m]]$conf)))) else NULL
mstat <- function(m, k) if (have_hs) hs$models[[m]][[k]] else NA
son_tool_uses <- if (have_hs && !is.null(hs$sonnet)) hs$sonnet$tool_uses else NA
son_replies <- if (have_hs && !is.null(hs$sonnet)) hs$sonnet$replies else NA

wrap_table <- function(df, align = "l") { cat("\n::: {.table-wrap}\n"); print(knitr::kable(df, row.names = FALSE, align = align)); cat("\n:::\n") }
caught <- function(d, flag) sprintf("%d · %d", sum(flag & d$unwanted_host, na.rm = TRUE), sum(flag & !d$unwanted_host, na.rm = TRUE))
first_day <- function(m) sub("^0", "", format(as.POSIXct(min(answers$ts[answers$model == m], na.rm = TRUE), origin = "1970-01-01"), "%d %b"))
ex <- answers[answers$hostname == "media.net", ]
