# 0008 — Rolling origins, deterministic baselines and final-holdout release

## In plain English

Historical predictions must be made before their answers are shown to the algorithm. Comparing several transparent rules needs the same target dates and coverage. A final period is reserved before selection and kept separate from tuning.

Date: 2026-10-19. Status: implemented Phase 7; real final holdout remains unscored.

## Decision

Use non-overlapping 48-day development windows and an expanding available history. Refit once per origin and reuse that state for every target horizon. A forecaster protocol accepts physically cutoff-filtered observations and predicts from the existing FeatureRow; scoring truth/observed Open are joined afterward. Baseline adapters implement last-known, last-observed weekday and trailing-weekday means without reading intermediate future actuals.

Keep zero actuals in MAE/RMSE and business totals; report RMSPE only where denominators are positive, with exclusions. Preserve anomalous closed-store actuals. Known-at-origin planned closure can trigger a documented shared zero override; realized closure cannot. Compare identical common-support keys and disclose missing/unsupported coverage. Select baselines using mean development-fold RMSPE, then MAE/name, following the current Rossmann objective without a hardware-dependent timing tie-breaker.

Reserve final calendar by dataset/store scope before development scoring. Final release validates frozen development evidence and exact protocol, claims a local receipt, evaluates only the frozen winner once, and subsequently returns verified cached files. Real final release is deliberately deferred until all intended model choices are frozen; synthetic tests cover that code path now.

## Trade-offs

Disjoint 48-day windows reduce overlapping-outcome dependence and simplify audit, but yield fewer origins than daily rolling evaluation. Three stores bound starter computation and cannot establish all-store performance. Exact coverage requirements can leave no eligible winner rather than hide gaps. Python lists remain bounded but full-stack RAM is unmeasured.

The ledger is an operational guard rather than protection against deliberate filesystem manipulation. Once viewed, a final period must be disclosed as seen in later work. Git/source hashes expose uncommitted provenance but require retaining/committing source for restoration. Future advanced algorithms must implement the same fit/predict boundary and add fold-fitted preprocessing; they are not implemented here.
