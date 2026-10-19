"""Non-overlapping rolling origins and a final holdout reserved by calendar only."""

from datetime import date, timedelta

from retailforecast.evaluation.contracts import BacktestConfig, BacktestPlan, Fold


def make_plan(start: date, end: date, config: BacktestConfig) -> BacktestPlan:
    """Reserve the final H labeled dates, then N development windows of length H.

    Refit on expanding available history through each cutoff. No random split,
    target-dependent date choice or development window overlaps the final holdout.
    Later development origins may legitimately train on earlier development actuals.
    """
    folds: list[Fold] = []
    for index in range(config.development_folds + 1):
        target_end = end - timedelta(days=config.horizon_days * (config.development_folds - index))
        cutoff = target_end - timedelta(days=config.horizon_days)
        if cutoff < start:
            raise ValueError("Insufficient calendar history for requested folds and final holdout")
        final = index == config.development_folds
        folds.append(
            Fold(
                fold_id="final" if final else f"development_{index + 1}",
                role="final" if final else "development",
                cutoff_date=cutoff,
                target_end=target_end,
            )
        )
    return BacktestPlan(historical_start=start, historical_end=end, folds=tuple(folds))
