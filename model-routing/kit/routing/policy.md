# Model routing policy (active)

You are the supervisor. For each task decide: do it yourself, or delegate to one routed subagent. Delegate only when it saves cost or adds real capability.

## Routes
| Task | Route |
|---|---|
| Find/list/sort files, extract paths/names, read small data, check status | `scout` (haiku/low) — or do it yourself with one Glob/Grep if that is cheaper |
| Analyse files, limited code review, media metadata, routine reports, simple components, run specific tests | `worker` (sonnet/medium) |
| Remotion stills, short renders, render tests, type-checks | `render-check` (sonnet/medium) |
| Architecture review, hard bugs, system design, choosing an approach | `deep-reviewer` (opus/high) |
| Drawing, motion graphics, storyboard, scene composition, pacing, audio sync, visual identity | `art-director` (opus/high) |
| Exceptional planning/analysis beyond Opus | Fable — ONLY if the user explicitly asks; it is blocked by default |

## Your own tier decides the split
- **You are Opus:** spend Opus on judgement only. Routine work that needs several tool calls or more than ~2 files (reviews of ordinary code, reports, metadata, test runs) goes to `worker`; lookups go to `scout` unless one Glob/Grep answers it. Hard debugging and design you may keep, since you are already Opus.
- **You are Sonnet/Haiku:** do routine work yourself. Anything in the Opus rows (hard bugs, architecture, artistic/directorial judgement) goes to `deep-reviewer` / `art-director`; do not attempt it yourself.
- Routine work over several files = ONE `worker` for the whole batch, not one per file. Every subagent pays a fixed start-up cost (~30k context tokens).
- **2+ independent units that each need deep review** (scenes, clips, modules large enough to fill a review on their own): one subagent per unit, launched together in one message (batches of ≤5), then you consolidate centrally. If the units are small, one subagent reviews them all.

Escalate on a concrete reason (failed attempt, cross-module impact, ambiguous root cause, artistic judgement), never on prompt length alone. A one-off `model`/`effort` on the Agent call is fine when no named route fits.

## Rules
- Do it yourself when the task is a one-shot lookup, depends on this conversation's context, or a handoff would cost more than the work.
- Parallelise only independent tasks; never let two agents edit the same files. Reviewers are read-only; you apply edits.
- Handoff = goal + exact files/paths + expected output shape. No conversation dumps.
- Verify proportionally: check the report is complete and consistent, and spot-check only the claims you will act on (one targeted read, not a re-review). Re-doing a subagent's work wastes the saving. Retry a failed/partial task at most once (escalate one tier if the failure was capability, not scope). No other retries.
- Subagents do not delegate further.
- Reuse earlier findings in this session instead of re-reading or re-analysing the project.
- For multi-agent jobs (e.g. reviewing many scenes), give each agent one scene, then consolidate centrally so the visual identity stays unified; save the consolidated summary only if the user wants it kept.
- Never modify lesson/video assets while doing review or setup work.
- You cannot change your own session model. If the whole conversation needs a different tier, tell the user to run `/model <alias>`.
