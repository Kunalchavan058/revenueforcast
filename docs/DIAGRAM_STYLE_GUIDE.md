# Diagram and explanation standards

## In plain English
Diagrams should tell the same story as the text. Labels carry meaning even when color is unavailable. Small maps are easier to follow than crowded ones. Every diagram explains its inputs, outputs, and failures. Editable Mermaid source stays in Markdown for reviewers.

## Visible legend
| Color family | Meaning and label | Fill | Border | Text |
|---|---|---|---|---|
| Blue | Data: observations and snapshot inputs | #dbeafe | #1e40af | #111827 |
| Violet | Transformation/training: Features, Train, Evaluate | #ede9fe | #5b21b6 | #111827 |
| Green | Approved outputs: active models, Predict results, exports | #dcfce7 | #166534 | #111827 |
| Orange | Decisions/warnings: cutoff, rejection, prohibited inputs | #ffedd5 | #9a3412 | #111827 |
| Gray | Infrastructure: Browser, API, worker, registry, archived storage | #f3f4f6 | #4b5563 | #111827 |

Use light fills, dark borders, and dark text. Always label Active, Prohibited, Approve, or other meaning explicitly; color is never the only signal. Shapes/dashed edges may reinforce but not replace labels. A database containing Data can be blue even though its host is infrastructure. Feature-building operations are violet; observations are blue. Retained inactive lifecycle history uses gray.

## Mermaid rules
Use fenced mermaid source embedded in Markdown with GitHub-supported flowchart/state syntax. No scripts, external images, click handlers, or HTML labels. Use LR for journeys/timelines and TB for ownership. Aim for about 10 substantive nodes; split crowded diagrams. D5 has eight leaf states in two named regions. Keep labels short and qualifications below the chart. Label meaningful arrows with action verbs; initial/final markers may be implicit.

Vocabulary must agree across pages: Data, Features, Train, Evaluate, Approve, Predict. Separate attempt status from approval roles. Explain whether arrows represent control, movement, or version roles. Immediately below each chart include a plain-English story, numbered steps, inputs, outputs, and errors. State concurrency and omitted dependencies. Dates/horizons may be illustrative; never invent observed accuracy or performance numbers.

## Inventory and review
| ID | Location | Purpose |
|---|---|---|
| D1 | ARCHITECTURE.md | first training, model reuse, optional retraining |
| D2 | ARCHITECTURE.md | owners, storage, labeled actions |
| D3 | DATA_FLOW.md | validation, temporal Features, Train, Evaluate |
| D4 | DATA_FLOW.md | July 31 to August 7 direct forecast |
| D5 | MODEL_LIFECYCLE.md | separate attempts/approvals, archive and rollback |

Review branch reachability, action labels, leakage boundaries, active-model continuity, and persistence ownership. If Mermaid CLI is already installed, render all five sources and inspect them. Do not install tooling in a documentation-only phase. Otherwise record static review and explicitly disclose unverified rendering. No rendered images are claimed for this phase.
