# Engineering Quality

This repository includes a lightweight delivery-quality baseline for demo, review, and resume presentation.

## Backend observability

- Every API response returns `X-Request-ID`.
- Frontend requests now send `X-Request-ID` by default for traceability.
- Backend logs include `request_id`, HTTP status, and request duration.
- `/api/system/overview` exposes:
  - business entity counts
  - in-memory runtime request metrics
  - embedding usage metrics and daily aggregates

## Frontend verification

- `npm run test` runs Node-based frontend unit tests for request tracing helpers.
- Task polling tests cover completion, cancellation, and transient-error recovery for async analysis flows.
- `npm run build` remains the production build check.
- `/tasks` provides a unified task center for async analysis progress, recent tasks, result navigation, and retry entry points.

## Task operations

- Async orchestration tasks expose normalized progress, current step, and duration metadata.
- Users can cancel running tasks from the task center with cooperative backend cancellation.
- Finished, partial, failed, or cancelled tasks can be retried while preserving the original task relationship.
- Startup schema bootstrap plus Alembic migration checks reduce drift risk for task-control fields.

## Eval Snapshot

Latest local eval run: 2026-06-24, using the current `backend/.env` provider configuration.

- RAG eval: `python scripts/eval_rag.py --top-k 5`
- Result: `Recall@5=0.920`, `MRR=0.922`, `Keyword Hit Rate=0.807`
- Lowest doc-type recall after seed expansion: `skill_model=0.769`
- Agent eval: `python scripts/eval_agent.py`
- Result: `MAE=3.0`, `Spearman rho=0.991`, `hit_tol10=10/10`

Interpretation: the eval pipeline is runnable end-to-end. RAG recall improved after adding seed coverage for `resume_template`, `jd_lib`, `interview_q`, `skill_model`, and `industry_report`, then splitting common `skill_model` roles into standalone documents and re-importing all bundled knowledge seeds. Agent scoring now has useful rank differentiation after removing fixed score examples and adding deterministic score caps for obvious adjacent-role weak-fit cases. Treat these numbers as the current baseline, not as a final product-quality claim.

## Eval Gate

Run the quality gate from the repository root:

```powershell
./scripts/eval-quality.ps1
```

To rebuild bundled knowledge seeds before evaluation:

```powershell
./scripts/eval-quality.ps1 -ImportSeeds
```

Default thresholds:

- RAG: `Recall@5 >= 0.85`, `MRR >= 0.85`, `Keyword Hit Rate >= 0.75`
- Agent: `MAE <= 12.0`, `Spearman rho >= 0.80`, `hit_tol10 >= 7`

The script writes JSON reports to `backend/reports/`, which is ignored by Git because reports are environment-specific artifacts.
Each run now keeps timestamped history snapshots such as `rag_eval_20260626_153000.json` and refreshes `rag_eval.json` / `agent_eval.json` as the latest aliases.
The frontend `评测报表` page reads these files through `/api/eval-reports` for history browsing and version comparison.

### What the CI RAG gate actually checks

CI has no MySQL and no pre-built vector store, so `ci.yml` builds a throwaway corpus first
(`backend/scripts/seed_rag_corpus.py` ingests the 16 bundled `docs/knowledge-seeds/*.md` files through the real
ingestion path into a scratch SQLite + a scratch Chroma dir, ~3s), then runs:

```
python scripts/eval_rag.py --min-lexical-recall 0.7 --min-lexical-keyword-hit 0.7 --max-empty-results 0
```

Measured on that corpus (50 queries, mock embeddings): lexical `recall@5 0.813`, `keyword_hit 0.88`, `mrr 0.781`.
The random-retriever baseline on the same corpus is `recall@5 0.479`, `keyword_hit 0.411` — the script computes and
prints it, and fails any floor that sits at or below it.

| claim | gate | why |
| --- | --- | --- |
| lexical retrieval still finds the right kind of document | `--min-lexical-recall` / `--min-lexical-keyword-hit` | BM25 doesn't depend on the embedding provider, so under `EMBEDDING_PROVIDER=mock` this is the only semantic signal available |
| the fused pipeline is wired up (visibility, hydration, RRF, rerank) | `--max-empty-results 0` plus the default `--max-retrieval-errors 0` | an empty or throwing result means a broken path, not bad relevance — which is exactly how this gate used to fail |
| semantic (vector) retrieval quality | **not gated in CI** | mock embeddings are hash-derived pseudo-vectors; setting `--min-recall` / `--min-mrr` / `--min-keyword-hit` on the fused numbers now fails outright under `EMBEDDING_PROVIDER=mock` instead of passing at chance level |

The previous CI line was `--min-recall 0.5` on the fused number — a floor below the random baseline. Use
`scripts/eval-quality.ps1` with a real embedding provider when you need a number worth quoting.

### Agent / recommend gates: baselines measured 2026-09-21 (floors NOT yet retuned)

`eval_agent` is not run in CI at all; its floors live only in `scripts/eval-quality.ps1`
(`MAE <= 12`, `rho >= 0.80`, `hit_tol10 >= 7`) over **10 labeled pairs**.

| null model | MAE | hit ±10 | Spearman ρ |
| --- | --- | --- | --- |
| any constant (mean 66 / median 70 / best-MAE 65) | 18.0 | 2–3/10 | undefined¹ |
| constant 82 + the deterministic cap rule | **9.70** | **8/10** | 0.721 |
| `LLM_PROVIDER=mock` as actually run today | **9.70** | **8/10** | 0.721 |
| uniform random 0–100 (2000 draws) | median 31.2 (best 5% = 20.5) | median 2/10 | 95th pct 0.564; P(ρ≥0.8) = 0.004 |

¹ The old `compute_spearman` returned **0.5** for a zero-variance prediction vector (ties are undefined for
`1 - 6Σd²/n(n²-1)`), so "judge nothing" earned half of a perfect rank score. It now returns `null` plus a
`spearman_reason`. Same class of fix as E4's `predicted = 0`.

Read that table as: **`MAE <= 12` and `hit_tol10 >= 7` are currently passable with no language model at all**
(mock literally scores 9.70 / 8). Only `rho >= 0.80` sits above the null models, and at n=10 a single relabeled
pair moves MAE by 1–4 points and ρ by ~0.1, so floors finer than that are reading noise.

`eval_recommend` gates `skill_match_accuracy >= 0.4` in CI over **2 cases**, and none of its five metrics
currently separates a working system from a copy-paste:

- `skill_match_accuracy`: the labels define `expected_skill_overlap` as *every skill on the resume* (pair 1 even
  counts `docker`, which the JD doesn't ask for), so **copying the resume's skill list scores 1.000**. Predicting
  nothing scores 0.0. The 0.4 floor cannot see the difference.
- `jd_explanation_consistency` had a reading bug: `round(_mean(parts) or 1.0, 3)` turned "both arms completely
  wrong" (0.0) into "perfectly consistent" (1.0). Verified old vs new on the same case: **1.0 → 0.0**. Cases with
  nothing comparable now report `null` (未测出) instead of 1.0, and `measured_cases` says how many cases actually
  contributed. The same `or 0.0` inversion was removed from the aggregate metrics.
- `interview_score_stability` (0.938 today) is computed from the eval set's own `interview_score_samples`
  — a fixture property that no system change can move; a case with one sample scores 1.0.
- `recommendation_explainability` = (keyword hit + template structure)/2, and the keywords are matched against the
  explainer's own fallback template, which this script forces (`_llm_explain` → `_fallback_explain`).
- `feedback_agreement_rate` is structurally unavailable: `job_recommend_feedback` has 0 rows and the eval cases
  carry no `resume_id`/`jd_id`, so the pairing set is always empty → `null`.
- With no MySQL reachable (CI's condition) the script dies with an uncaught `OperationalError` (exit 1) before
  printing anything. **Left red on purpose**: the obvious "degrade gracefully" patch would turn a proven-saturated
  gate from red into falsely green. Fix it together with the labels.

Those provenance notes now travel with the numbers: the console report prints them, they are stored in
`run_meta.metric_notes`, and `check_thresholds` appends them to any failing line.

## Full verification

Run:

```powershell
./scripts/verify.ps1
```

It executes:

1. backend pytest
2. Alembic migration check
3. frontend tests
4. frontend production build
