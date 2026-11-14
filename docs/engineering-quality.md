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

## API auth is a property of the prefix

- 20 of the 28 `include_router` calls in `backend/app/api/router.py` mount `SESSION_GUARD`
  (`Depends(get_current_user)`) at include level. An endpoint added under one of those prefixes is
  authenticated without the author writing anything; it answers 401 to anonymous callers.
- The 8 remaining calls mount 6 prefixes that mix public and authenticated operations (`/auth`,
  `/system`, `/interview`, `/subscription`, `/jobs` — three separate calls — and the `X-API-Key`
  `/v1` group), so they still declare auth per endpoint. Adding `SESSION_GUARD` to one of them
  breaks a public operation — `tests/test_public_api_surface.py` fails if that happens.
- Whatever the prefix, keep declaring `Depends(get_current_user)` in the signature: the include-level
  guard is a safety net, not the intent, and FastAPI resolves it once per request either way.
- New anonymous operations are not allowed by omission. They have to be listed in
  `PUBLIC_OPERATIONS` in `tests/test_public_api_surface.py` with a reason; that test walks the real
  router graph and fails otherwise.

## Frontend API layer has no dead exports

`frontend/src/api/*.js` is a thin wrapper per endpoint, and nothing forces a wrapper to have a caller.
After `runMatch` was deleted (2026-11-14, `docs/真provider实测.md` §7) a scan of the whole layer found
**16 exports nobody imported** — 15 more of the same shape, plus one WS helper:

| Export | Backend endpoint | Why it went |
| --- | --- | --- |
| `dashboard.getNextActions` | `GET /dashboard/next-actions` alive | Home renders from `/dashboard/overview`; no next-actions block exists |
| `interview.deleteInterview` | `DELETE /interview/sessions/{id}` alive | Interview history has no delete action (deliberate: the record is the history) |
| `interview.getQuestionCategories` | `GET /interview/question-bank/categories` alive | The bank page filters from `getQuestionBank`'s own payload |
| `interview.getInterviewPrep` | `GET /interview/preparation/{jd_id}` alive | The screen shows `preparation_tips` inside each question instead |
| `interview.isWSConnected` | n/a (client state) | No caller ever checked connection state directly |
| `jobs.fetchJobDetail` | `POST /jobs/fetch-detail` alive | External search returns detail inline; import uses the server-side fetcher |
| `knowledge.getKnowledgeDoc` | `GET /knowledge/{id}` alive | The drawer reads `getKnowledgeChunks` only |
| `multi_agent.startMultiAgent` | `POST /multi-agent/start` alive | The page uses `/multi-agent/auto` + `/run/{id}/detail` (the manual-entry pair) |
| `multi_agent.getMultiAgentRun` | `GET /multi-agent/run/{id}` alive | Same: the detail endpoint replaced the status one |
| `resume.getAccessibleResumeList` | `GET /resume/accessible-list` alive | Enterprise resume pool has no screen; candidate pages use `/resume/list` |
| `resume.seedDemoResumes` | `POST /resume/seed-demo` alive | Superseded by D2's `POST /demo/seed` |
| `subscription.getSubscriptionPlans` | `GET /subscription/plans` alive (public) | No screen shows the plan table |
| `subscription.checkQuota` | `POST /subscription/check-quota` alive | The server judges quota on the action; the UI never pre-checks |
| `subscription.getMyOrders` | `GET /subscription/orders` alive | Candidate side has no orders page (admin uses `/subscription/admin/orders`) |
| `targets.getTargetDetail` | `GET /targets/{id}` alive | The list row already carries what the dialog shows |
| `targets.getPipelineDetail` | **no such route** (`PUT`/`DELETE` only) | Would 405 if called |

Two things this table is careful about: the **endpoints stay** (a dead client wrapper is not a dead
capability — several of these are backend features with no entry point yet), and only the one whose
route never existed was actually broken.

The guard is `frontend/tests/unit/apiLayerNoDeadExports.test.js`. It does not grep for the name in
file text — a comment mentioning an export would then keep it alive, which is exactly how a dead
export survives review. It resolves the **import graph** instead: named imports, default imports, and
`import * as ns` member access (`auth` is consumed that way). Scope is `src/**` — an export used only
by a test still counts as dead, because a test vouching for dead code is not a user.

Two anti-vacuity checks are part of the guard: a synthetic case proves the detector reds on an unused
export, and another proves a prose mention does **not** count. Measured on the real tree: adding
`export const mutationProbe` to `src/api/jobs.js` made it fail with exactly `jobs.js::mutationProbe`;
removing it went green again.

## Async tasks have a queued phase

`/analysis/full` only accepts a task when a worker is consuming the queue (otherwise 503 — see
`docs/真provider实测.md` §6). So "after we have a task id" has two genuinely different waits, and the
screen used to render both as the same motionless 0%:

- **queued** — the row exists, `progress.step_counts.total === 0`, nobody has written the first
  `agent_step_log` yet;
- **running** — steps exist, the progress panel has something to show.

`frontend/src/utils/taskPhase.js` owns the classification (`taskPhase`) and the two sentences. The
shared poller passes it as the third argument of `onProgress(taskData, steps, phase)`, so all three
consumers of `useAgentTaskPolling` (SmartAnalysis, AnalysisResult, the career-planning run chain) make
the same call. The judgement reads the payload only — never the clock: a long wait may just mean the
worker is busy with the previous task, and the frontend cannot see the queue length.

Two copy rules came out of building it:

1. **The queued panel says what is and is not guaranteed.** It promises "progress within seconds" and
   "a failure with a reason in about two minutes **if no worker is available**" — the conditional is
   load-bearing, because a busy worker is allowed to take longer and will not fail.
2. **The frontend writes the failure sentence itself.** A task that fails before its first step is a
   state the frontend can see (`status === 'failed'` + zero steps), so `failedBeforeFirstStep()` picks
   `NEVER_STARTED_FAILURE` instead of echoing the backend's `error_msg`. That is the same rule the job
   pollers already enforce from the other side: the shared poller deliberately does **not** put
   `error_msg` on `error.userMessage`, because three tests (`resumeRewriteJobPolling`,
   `resumeReportPage`, `careerPlanningUnmountNoToast`) prove that server or model text must never
   reach a candidate's screen. A first attempt at this echoed `error_msg` and those three went red —
   the guard was right.

The first attempt was also wrong in a second way, caught by a real-browser run: `SmartAnalysis`'s
outer `catch` overwrote the specific message `onFailed` had just written, leaving "分析请求失败，请稍后
重试" while the database held a fully explained failure. It now only applies its fallback when nothing
was written.

A later pass extended the same treatment to the two surfaces that still lost it:

- **`AnalysisResult`** used to answer a failure with a 5-second toast only. It now keeps an inline
  alert with the reason and a 重新分析 button, next to the existing load-error alert — a person who
  looks back at the screen 30 seconds later no longer sees "nothing happened". It also stopped saying
  "未知错误": the fallback is now 任务没有完成，可以稍后重试（`FAILURE_FALLBACK`）.
- **`TaskCenter`** drew one 0 % bar for both "queued" and "running but stuck". A running task with
  zero steps now says 排队中 and draws no bar at all, and its failed-before-first-step card carries
  the same frontend-owned sentence instead of the generic 任务没有完成.

Measured on a real screen (1366×900, demo account, worker stopped but heartbeat freshly planted so the
door accepts exactly one task):

| moment | what the screen shows |
| --- | --- |
| after clicking 生成求职分析, 0 steps | info panel「排队中：后台还没开始跑第一步」+ the two sentences; the 分析进度 panel is absent |
| 2 min later, converged | inline error「任务还没开始执行就被收口了：后台没有可用的 worker。请稍后重试；如果一直这样，请联系管理员启动编排 worker。」+ 重新分析 |
| a run with a live worker | 分析进度 4 / 6 步，步骤时间线逐条点亮（匹配度 0 那一格是因为 embedding 欠费，不是阶段判断） |
| 任务中心，排队中 | 卡片标签「排队中」+「排队中：任务已提交，后台还没开始跑第一步。正常情况下几秒内就会进入进度。」+ 耗时 + 取消，**没有进度条** |
| 任务中心，收口后 | 同一张卡片变成「失败 / 耗时：2.0 分钟」+ the same frontend sentence + 重试；服务端 `error_msg` 一个字没上屏 |
| 分析结果页，排队中 → 收口 | 排队块换成行内错误 + 重新分析，服务端原文同样没上屏 |

A fourth family uses the same poller with a **different payload shape**: the three report jobs
(`ResumeReport`, `ProjectReport`, `PortfolioReport`) have no `progress` at all — only
`pending / running / completed / failed`. "Queued" there is simply `pending` (the row exists and is
submitted to the local pool but no worker has claimed it), and `taskPhase()` already answers `queued`
for that status, so the classifier did not grow a second rule. All three used to say 正在逐节生成 while
queued; they now say 排队中…（前面可能还有别的作业）until the job is claimed.

Evidence boundary, stated because it differs from the rows above: those three are covered by
component-level tests (`reportJobsQueuedCopy`, real components + the real poller + a `pending`
payload), **not** by a browser screenshot. Catching that window in a browser needs the report pool
saturated; the copy branch is one `v-if`, and the same machinery is browser-verified on the two
screens above.

## Frontend verification

- `npm run test` runs Node-based frontend unit tests for request tracing helpers.
- Task polling tests cover completion, cancellation, and transient-error recovery for async analysis flows.
- `npm run build` remains the production build check.
- `/tasks` provides a unified task center for async analysis progress, recent tasks, result navigation, and retry entry points.

## Score colour is one scale

- `frontend/src/utils/scoreTone.js` is the only place a score becomes a display
  band: 85/70/50 for match and resume scores — the bands the backend
  recommendation label uses (`MatchExplainer._recommendation`) — 85/70/55 for
  interview performance, and `unknown` when no score was computed.
- Views attach `.score-tone--*` / `.score-fill--*` / `.score-chip--*` /
  `.score-level--*`, call `scoreToneTagType` for `el-tag`, or pass
  `var(--app-score-*)` where a colour value is required. No view or layout keeps
  a hex literal in `<script>`; `scriptColorLiterals: {}` in
  `frontend/tests/unit/styleDebtRatchet.test.js` locks that.
- Two contract tests guard what a hex budget cannot see: every tone a view can
  emit must have a rule, and the `--app-score-*` token set must be complete per
  tone. They exist because an earlier pass deleted `.score-high/.score-mid/.score-low`
  while `OfferCompare` kept emitting those class names, which silently left one
  score uncoloured.

## Dates come from one module

- `frontend/src/utils/format/date.js` owns every calendar-string render: `monthDay`,
  `monthDayTime`, `dateTime`, `compactDateTime`, `isoMonthDay`, `utcStamp`,
  `rawStamp`. Before it, 18 copies lived in 16 files (counted by behaviour —
  `toLocale*`/`Intl` in a view — because counting by function name finds only 15 and
  misses `formatShortDate` / `formatPipelineTime`).
- `tests/unit/dateFormat.test.js` keeps the pre-migration bodies verbatim and asserts
  per-input equality, so "output unchanged" is measured. The three places that
  deliberately differ are asserted as different: a missing locale on
  `Profile.vue`'s timestamps, dead `catch { return d }` blocks that could never fire
  (`toLocaleString` returns the string `Invalid Date` rather than throwing), and each
  page's own empty placeholder.
- The ratchet's fifth check fails if any view or layout calls `toLocale*` /
  `Intl.DateTimeFormat` again.

## Resolved: the frontend format gate (was "cannot pass")

`npm run format:check` — CI step "Check frontend formatting" — used to fail no
matter what the change under review did. It is now green: one `npm run format`
commit (`5662916`, recorded in `docs/archive/upgrade-plan.md` as D13) moved the tree to
prettier 3.9.5 rather than pinning the dep back to the 3.3 line.

**Correcting the number this section used to carry: it said 95 files. The
reproducible figure is 17.** The 95 came from a local working tree, and a local
tree lies twice over about line endings: `core.autocrlf=true` checks text files
out as CRLF, so `prettier --write` rewrites files whose only real change is `\r\n`
-> `\n`. That run reported 66 files; **49 of them have no diff at all**, because
the repository objects were already LF. Only 17 had real style drift.

The number that matches CI is measured like this, and `gh` is blocked here so
this probe is the substitute:

```
git archive origin/master frontend | tar -x -C /tmp/probe
python -c "...replace b'\r\n' with b'\n' in every file..."   # git archive applies
                                                            # autocrlf on Windows
cd /tmp/probe/frontend && node <repo>/frontend/node_modules/prettier/bin/prettier.cjs --check .
```

That probe reported 17 offenders on `origin/master`, 18 on `HEAD~1`, 0 on the
formatting commit. A red "Check frontend formatting" step is no longer a known
gap: read it as a regression from the change under review.

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
- Agent: `MAE <= 8.0`, `Spearman rho >= 0.85`, `hit_tol10 >= 17` (of 25) — chosen to beat the
  model-free baseline the script prints (see below), not to match whatever the current model scores.
  A red run here is information, not a broken gate. `hit_tol10` is a **count**, so it has to be
  revisited whenever the labeled set grows.

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

`eval_agent` runs over **25 labeled pairs** — the original 10 plus 15 drafted on 2026-09-21 that are
**awaiting review of their scores** (the pairs, not the format; `test_agent_fixture_keeps_enough_score_resolution`
guards the spread). The script prints these null models on every run:

| null model | MAE | hit ±10 | Spearman ρ |
| --- | --- | --- | --- |
| any constant (best tuned on this set) | 16.4 | ≤ 11/25 (44%) | undefined¹ |
| constant + the deterministic cap rule | **16.44** | **11/25** | 0.554 |
| `LLM_PROVIDER=mock` as actually run today | 19.2 | 11/25 | 0.543 |
| uniform random 0–100 (500 draws) | median ~31 | — | 95th pct **0.349** |

Compare with the same table at n=10 (before the new pairs): best model-free MAE was **9.5** with
**8/10** hits and ρ **0.721** — i.e. the old `MAE <= 12` / `hit_tol10 >= 7` floors were *below* what a
constant plus the cap rule could produce, so mock provider output passed them. Widening the labeled set
is what made those numbers honest: the same trick now lands at MAE 16.4 and 44% hits, and
`tests/test_eval_thresholds.py::test_agent_floors_must_beat_the_model_free_baseline` pins the
relationship as ratios (MAE ≥ 14, hit rate ≤ 0.5, ρ ≤ 0.7) so it survives the set growing further.

¹ `compute_spearman` used to return **0.5** for a zero-variance prediction vector (ties are undefined
for `1 - 6Σd²/n(n²-1)`), so "judge nothing" earned half a perfect rank score. It now returns `null` plus
a `spearman_reason`. Same class of fix as E4's `predicted = 0`.

CI runs `eval_agent` with `--max-errors 0` only: under a mock provider any quality floor would assert
nothing about quality. The floors live in `scripts/eval-quality.ps1` (real provider) and are checked
against the printed baseline at every run. Resolution after widening the set: at n=25, relabeling one
pair moves MAE by ~0.8 points instead of 1-4, so the floors are no longer reading single-row noise -
but they are only as good as the labels, which is why the 15 new scores need a review pass.

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
