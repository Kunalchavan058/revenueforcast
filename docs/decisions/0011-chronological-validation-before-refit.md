# 0011 - Compare chronological validation models before activating final refits

Date: 2026-10-20. Status: implemented correction to decision 0010.

## Problem and decision

The dataset has sufficient labeled history. Requiring a final refit to predate its own original development origins incorrectly discarded valid model-selection evidence. Training already fit separate native models before each validation window, scored them, selected a recipe and refit afterward. Lifecycle registration omitted those historical models and incorrectly treated refit timing as missing data.

Preserve the selected trial's original fold models/preprocessing and seal them to its final model/recipe/protocol. Re-score both registered recipes on matching chronological validation windows using the correct per-cutoff models. Never predict backward with final weights, compare unrelated stored summaries, claim retrospective model-selection scores are untouched final performance or use Kaggle's unlabeled test as truth. Activate the compatible winning final refit transactionally; manual approval is only for genuinely insufficient evidence.

Exact serving-weight post-fit evaluation remains supported separately and explicitly labeled. Recipe comparisons record original lookback/row/sampling budgets. A joint Auto run provides controlled algorithm comparisons under the same mode/budget, with baselines and the same final holdout. Retained validation artifacts have checksum/cutoff/recipe guards and recovery for existing registrations; fitted final bytes are not mutated. Comparison JSON/Parquet and recipe identities make the selection reproducible. The final holdout remains locked.
