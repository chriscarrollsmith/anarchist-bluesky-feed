# Backlog

Living backlog for the prosocial anarchist Bluesky feed.

## Product goals

- **Precision:** Keep out ancap / chaos / crypto false friends and personal
  fundraising wrapped as “mutual aid.”
- **Recall:** Allowlisted collectives and mutual-aid *praxis* should appear even
  without explicit anarchist keywords (org project updates stay; Venmo asks go).
- **Quality rubric:** Ambiguous leftovers (and solicit-shaped provisional keeps)
  are scored by DeepSeek (`deepseek-v4-flash`) on thematic fit, positive valence,
  wow factor, and solicit intensity.

## P0 — Ship / harden v1

### B-001 — Grow allowlist of aligned orgs
- Curate publishers, IWW branches, Food Not Bombs chapters, infoshops, mutual-aid
  networks. Screen with `scripts/screen_allowlist_candidates.py`.
- Keep DIDs in sync via `scripts/resolve_allowlist_dids.py`.

### B-002 — Expand eval set from live near-misses
- Sample with `collect_eval_sample.py` (authors / near-miss / events).
- Optional LLM proposals via `llm_label_judge.py` — human confirm before append.

### B-003 — Tune quality-rubric gates on holdout
- Log classifier keep/drop reasons (incl. `quality_reject:*` / solicit cues).
- Adjust thematic / valence / wow / solicit / composite gates only with
  stratified eval evidence.

### B-004 — Publish + Fly cutover
- `publish_feed.py` with real credentials on an operator machine.
- Set `FEED_URI` + `DEEPSEEK_API_KEY` on Fly; verify `did.json` + skeleton.

## P1 — Quality

### B-010 — Multilingual anarchist terms
- Spanish/French/German strong positives and hard negatives.

### B-011 — Soft-prior analytics
- Dashboard or script for authors approaching the soft-prior threshold.

### B-013 — Quality rubric ranking
- Optionally store grade breakdowns on indexed posts and soft-boost wow /
  valence in `RANKING_MODE` experiments once the index is non-empty.
