# 0002 — Local stack and process boundaries

## In plain English
The app should run on a normal laptop without paid services or a GPU. The browser displays results, the API handles requests, and a worker trains models separately. Saved models make predictions cheaper than relearning. A local schedule cannot run while the computer is asleep. These choices keep V1 understandable.

Date: 2026-10-19. Status: Accepted design, not implemented.

## Decision
Use Next.js TypeScript, Tailwind/shadcn/ui, Apache ECharts, FastAPI, typed Python modules, CPU-first LightGBM/XGBoost, Docker PostgreSQL, MLflow, and DVC. Exact dependency versions will be pinned/tested during tooling, not this phase. Use a separate Python worker/scheduler with a PostgreSQL durable job queue and one child training process. API requests never Train synchronously. Shared feature contracts serve evaluation and prediction.

Use pooled direct horizon-aware models and bounded origin sampling/batches instead of 48 independent models. Train algorithms sequentially with named trial/time/thread limits. No notebooks, GPU requirement, paid API, LLM, or distributed queue stack.

## Alternatives and consequences
In-API tasks tie training memory/lifetime to serving and complicate restart recovery. Redis/Celery adds deployment burden beyond V1. Colab is an environment experiment, not the local app runtime. Pooled direct models reduce job/artifact overhead but require honest evaluation; they do not guarantee accuracy. Process separation isolates lifetime/crashes but does not guarantee resource isolation on shared hardware.

Measure combined RAM/CPU on the 8 GB target. Verify bounded feature expansion, chronological cutoffs, durable queue recovery, and Predict during training. The scheduler requires an awake host/worker and audited missed-run handling. See ARCHITECTURE.md for contracts and MODEL_LIFECYCLE.md for states.
