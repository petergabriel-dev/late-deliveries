---
id: ADR-0015
title: Phase 5 communication - rendered reports, committed outputs and a staleness guard
status: Active
date: 2026-11-16
kind: engineering
judgment_call: none
readWhen: Editing the memo, write-up or README, changing report rendering, or rebuilding and publishing generated outputs
---

# ADR-0015: Phase 5 communication - rendered reports, committed outputs and a staleness guard

Records the owner's Phase 5 discuss/plan choices before any Phase 5 code. ADR-0014 fixes the money reading and memo content; this decision fixes how those results reach readers, without changing the analysis.

## Options considered

- **Numbers and prose:** templates plus a small renderer (chosen) keep numbers tied to sources; hand-written prose plus a number scan catches digits but cannot prove their meaning; source notes beside hand-written numbers leave copying errors possible.
- **Location and README:** keep templates and rendered reports in `docs/report/`, with the rendered README at the root (chosen); root-level reports clutter the entry point; a hand-written README leaves its headline outside the renderer.
- **Placeholder language:** explicit source, dictionary path and optional format spec (chosen); arbitrary expressions add a second programming language; list indexes silently change meaning when rows move.
- **Derived values:** one `derived()` function, exact-match list selection and shared table formatting (chosen); arithmetic in templates or copied calculations spread logic across documents.
- **Literal numbers:** allow only identifiers and ADR-defined parameters outside placeholders (chosen); ban every digit and identifiers become awkward; scan digits automatically and still miss spelled-out or semantically wrong values. Use a manual audit instead.
- **Generated outputs:** commit `outputs/` and guard staleness (chosen); keep it ignored and GitHub readers cannot inspect results without rebuilding. Keep `data/processed/` ignored either way.
- **Staleness guard:** a Make target after the full rebuild, excluding PNG bytes (chosen); a pytest check runs before estimators; guarding PNG bytes risks machine-dependent rendering failures; no guard lets committed results drift.
- **Deliverables:** Markdown-only memo with an enforced word cap and a guided technical summary (chosen); PDF adds another rendering path; an uncapped memo or full table dump obscures the decision.
- **Polish and license:** core communication work plus a README notice for derived results (chosen); a code LICENSE, CI and brief rename are separate work, not prerequisites for this phase.
- **Publishing:** push once at the end, only after fresh owner approval (chosen); automatic or per-task pushes publish before the owner reviews the finished work.

## Decision

### Sources and rendering

- Templates live at `docs/report/memo.template.md`, `docs/report/writeup.template.md` and `docs/report/README.template.md`. Their targets are `docs/report/memo.md`, `docs/report/writeup.md` and root `README.md` respectively. Mark the README as generated, naming its template and `make report` at the end.
- `src/late_delivery/report.py` uses stdlib only, plus existing `diagnostics.rounded` and `diagnostics.md_table`. Keep pure functions and a thin `main()`; parameters live in `config.py` with ADR-0015 comments.
- Load each `outputs/*.json` by its filename stem, `assumptions.toml` as `assumptions`, and computed values as `report`. `derived(sources)` is the sole place for report arithmetic; write its result to `outputs/report.json`, with floats rounded to six decimals, indented JSON and no timestamps. Do not read stale `report.json` back as an analysis source.
- Grammar is `{source:dot.path}` or `{source:dot.path:fmt}`, using Python format specs. Paths traverse dictionaries only, never lists. `{{` and `}}` escape literal braces. Unknown sources, missing keys, list traversal, stray braces and invalid formatting raise with template and placeholder context; no silent fallback.
- For a value in a list, `one(rows, **match)` must find exactly one matching dictionary or raise. Store selected or computed values in `derived()`; build small summary tables there with `md_table`. Every derived key must be used by a template; an unused key raises.
- Validate all rendered documents before writing any of them: no partial rendered-document writes on error. Count words with a regex that ignores Markdown symbols. Resolve relative links and images from each target file's own location; missing targets raise. Skip URLs and anchors.
- Every statistic, count, money figure and input value in the memo, write-up and README must be a placeholder resolved from analysis JSON, `assumptions.toml` or derived `report.json` (invariant 6). Literal digits are allowed only for identifiers (ADR, phase, JC, check and task numbers) and definitional parameters named in ADRs, such as window dates, review-star definitions, repeat windows and confidence levels. No hand-typed result, including a spelled-out number, escapes this rule. Audit templates manually; no automatic number scanner.

### Rebuild and guard

- Commit every generated file in `outputs/`, including PNGs. This replaces the conventions rule "Never commit generated output" for `outputs/` only; `data/processed/` remains ignored and untracked. No estimator or analytical definition changes here.
- Add `make report`, depending on diagnostics, ladder, robustness and money; include report in `make all`. Add `make check-outputs`, depending on `all`, which inspects `git status --porcelain -- outputs docs/report README.md`, fails on any non-PNG change or untracked path, and lists offenders. PNGs remain committed and regenerated but are excluded from the byte-staleness guard.
- `make test` must work before estimators run: renderer tests use synthetic sources, never existing `outputs/`. Rendered Markdown and analysis JSON must be byte-identical across consecutive rebuilds. A clean clone must pass `uv sync && make check-outputs`.

### Reader-facing content and scope

- Memo is Markdown only, capped by `MEMO_MAX_WORDS = 450`. Use plain words, not regression, CI, fixed effects, ε, tornado, GMV or take rate. Follow every ADR-0014 content requirement: outside-estimates qualifier in the figure's sentence, measured repeat loss beside it, horizon alternatives and follow-up measurement, support-cost caveat outside the range, BRL first with USD in brackets, annual illustration labeled illustrative. End with the recommendation: break-even, promise-first and test longer promises before rollout.
- Write-up is a guided summary of 2,500-3,500 words, not a dump of full output tables. Fixed order: question and answer; limitations; data and sample; definitions (JC 1 and JC 5); method ladder (JC 3); reconciliation (JC 4); robustness; money (JC 6); reproduce. Cover all six judgment calls, including pre-registration (JC 2). Each section gives key results, at most one headline table and at most one figure, with alt text and a `Details:` line linking relevant ADRs and output Markdown. Use `fig_ladder.png`, `fig_robustness.png` and `fig_money_tornado.png` in their corresponding sections.
- README starts with the question on line 1 and the answer on line 3, links to memo and write-up first, then short limitations near the top. Include reproduction commands, outputs, decision-log and repository guides. The Data section states that results in `outputs/` and `docs/report/` derive from the Olist data and are shared under CC BY-NC-SA 4.0; this is the owner's publishing choice, not a legal review or a code license.
- Core polish only: no code LICENSE, CI setup or project-brief rename. Owner approves memo, write-up and README prose. Never push or publish without explicit approval at that moment; push once at Phase 5 end, never force-push.

## Why

- Placeholders make invariant 6 auditable without duplicating analysis logic or introducing a templating dependency.
- Dictionary-only paths and exact-match list selection fail loudly rather than attaching a result to the wrong label after reordering.
- Committed results let a GitHub reader follow the argument; the rebuild guard exposes stale prose and machine-readable outputs. Excluding PNG bytes avoids claiming cross-machine image determinism.
- The memo supports a decision; the write-up explains uncertainty near the top and sends technical readers to full evidence. ADR-0014's caveats remain attached to its money figures.

## Falsification test

- A clean clone's `uv sync && make check-outputs` exits nonzero: the reproducibility/determinism claim is wrong; investigate before claiming the phase done. A same-machine clone does not establish cross-machine byte identity.
- ADR-0014's required content cannot fit the memo's 450-word cap in plain words: the cap is wrong; record a new ADR before raising it, never silently relax it.
- Any reader-facing statistic, count, money figure or input value cannot be resolved to a placeholder and its source: invariant 6 is broken, even if the copied number happens to match.

## Affects

Docs (planned unless this task creates them):

- `docs/engineering/decisions/ADR-0015-phase5-communication-choices.md`
- `docs/engineering/decisions/README.md` (regenerated by Pi)
- `docs/engineering/architecture.md`
- `docs/engineering/dev-workflow.md`
- `docs/engineering/conventions.md`
- `docs/engineering/invariants.md`
- `docs/engineering/traps.md`
- `docs/report/memo.template.md` and `docs/report/memo.md`
- `docs/report/writeup.template.md` and `docs/report/writeup.md`
- `docs/report/README.template.md` and `README.md`

Code and configuration (planned):

- `src/late_delivery/report.py`
- `src/late_delivery/config.py`
- `tests/test_report.py`
- `Makefile`
- `.gitignore`

Generated results (committed in the outputs task; report JSON added with the renderer):

- `outputs/diagnostics.json`, `outputs/diagnostics.md`, `outputs/exclusions.json`
- `outputs/fe.json`, `outputs/fe.md`, `outputs/naive.json`, `outputs/naive.md`
- `outputs/rd.json`, `outputs/rd.md`, `outputs/matching.json`, `outputs/matching.md`
- `outputs/ladder.json`, `outputs/ladder.md`, `outputs/robustness.json`, `outputs/robustness.md`
- `outputs/money.json`, `outputs/money.md`, `outputs/report.json`
- `outputs/fig_days_late.png`, `outputs/fig_monthly.png`, `outputs/fig_rd.png`
- `outputs/fig_ladder.png`, `outputs/fig_robustness.png`, `outputs/fig_money_tornado.png`

Read-only sources: `assumptions.toml` and existing analysis JSON above. Raw data and analytical ADRs stay unchanged.

## Consequences

- Good: one rebuild updates prose and results from the same sources; readers can inspect evidence without running Python.
- Good: bad placeholders, ambiguous selections, unused derived values, excess memo words and broken relative links stop rendering.
- Bad/risk: a manual literal-number audit can miss a copied result; review must check semantic traceability as well as digits.
- Bad/risk: committed PNGs can become stale without the guard detecting them; `make all` still regenerates them.
- Bad/risk: generated README edits are overwritten; prose edits belong in its template. Cross-machine determinism remains unverified until tested.

## Read when

- writing or reviewing the Phase 5 memo, write-up or README
- changing report sources, placeholders, derived values, word limits or link checks
- rebuilding, committing or publishing generated results

## Supersedes

- No ADR. Replaces the unversioned-in-ADR conventions rule against committing generated output for `outputs/` only; ADR-0002's stack, raw-data and license decisions remain unchanged.
