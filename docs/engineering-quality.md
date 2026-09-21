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
- Agent: `MAE <= 8.0`, `Spearman rho >= 0.85`, `hit_tol10 >= 9` — chosen to beat the model-free
  baseline the script prints (see below), not to match whatever the current model scores. A red run
  here is information, not a broken gate.

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

### Agent / recommend gates: baselines, and what each floor now claims

Both scripts compute their own null models on every run, print them, and **fail any floor that
cannot beat them** — the same discipline the RAG gate got in E6.

`eval_agent` over **10 labeled pairs** (measured 2026-09-21; the script prints these numbers live):

| null model | MAE | hit ±10 | Spearman ρ |
| --- | --- | --- | --- |
| any constant (mean 66 / median 70 / best-MAE 65) | 18.0 | 2–3/10 | undefined¹ |
| best constant + the deterministic cap rule (tuned on this set) | **9.5** | **8/10** | 0.721 |
| `LLM_PROVIDER=mock` as actually run today | 9.7 | 8/10 | 0.721 |
| uniform random 0–100 (500 draws) | median 31.2 (best 5% = 20.5) | median 2/10 | 95th pct **0.576**; P(ρ≥0.8) = 0.004 |

¹ `compute_spearman` used to return **0.5** for a zero-variance prediction vector (ties are undefined
for `1 - 6Σd²/n(n²-1)`), so "judge nothing" earned half a perfect rank score. It now returns `null` plus
a `spearman_reason`. Same class of fix as E4's `predicted = 0`.

So the old floors (`MAE <= 12`, `hit_tol10 >= 7`) were passable **with no language model at all**, and
`eval-quality.ps1` now defaults above the baseline (8.0 / 9 / 0.85). CI runs `eval_agent` with
`--max-errors 0` only: under a mock provider a quality floor would assert nothing about quality.
Resolution caveat that no floor can fix: at n=10, relabeling one pair moves MAE by 1–4 points and ρ by
~0.1, so digits finer than that are reading noise. Adding labeled pairs is the only cure.

`eval_recommend` gates the **explanation layer against the `skill_gap` authority**, over a rebuilt
16-case set (was 2). Labels are the documented set rule — `canonical(resume) ∩ (canonical(required) ∪
canonical(nice_to_have))` and `canonical(required) − canonical(resume)` — and
`tests/test_recommend_eval.py::test_fixture_labels_are_the_documented_set_rule` recomputes them, so
nobody can quietly regenerate the expectations from the code under test. The old labels defined
`expected_skill_overlap` as *every skill on the resume*, which is why copying the resume list scored
1.000; on the new labels:

| null model (never looks at the system) | skill_match_accuracy | missing consistency |
| --- | --- | --- |
| copy the resume's skill list | **0.676** | — |
| predict every JD requirement as hit | 0.484 | — |
| predict nothing | 0.0 | 0.188 |
| claim every requirement is missing | — | **0.38** |
| the explainer's rule engine + fallback template (today) | 1.000 (16/16) | 1.000 (13/16 comparable) |

Because that arm is deterministic (no LLM, no DB), CI gates it at **1.0**: anything less is a real
semantic change in `_calc_skill` / `skill_gap`. Verified: mutating two labels drops the run to
0.969 / 0.962 and exits 3; setting the floor back to the old `0.4` exits 3 with
"门槛 0.4 ≤ 空模型基线 0.676".

Three of its metrics still do not measure the system, and now say so wherever the number appears
(console, `run_meta.metric_notes`, the API summary, and every failing gate line):
`interview_score_stability` is the dispersion of the eval set's own `interview_score_samples`;
`recommendation_explainability` compares the text against the explainer's own fallback template
(this script forces `_llm_explain` → `_fallback_explain`); `feedback_agreement_rate` needs real
`job_recommend_feedback` rows paired by `resume_id`/`jd_id` (the table has 0 rows, so it is `null`).
The DB is now optional: an unreachable database reports `linkage_status: db unavailable: …` instead of
killing the run with an uncaught `OperationalError` — safe to soften only *after* the gate got real
floors, which is why it was left red until this change.

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
