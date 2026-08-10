# Prosocial Anarchist Bluesky Feed

Self-hosted Bluesky custom feed that aggregates and celebrates **prosocial anarchist** content — mutual aid, dual power, horizontal organizing, and movements that want to decentralize both political power and capital.

Architecture forked from [capital-region-feed](https://github.com/chriscarrollsmith/capital-region-feed).

## Architecture

```
Jetstream (posts/likes/reposts) → matcher → SQLite → getFeedSkeleton → Bluesky AppView
```

Bluesky only asks this service for post URIs; AppView hydrates them.

| Path | Role |
|------|------|
| `server/matcher.py` | Regex floor (strong / ambiguous / hard negatives) |
| `server/classifier.py` | DeepSeek quality rubric (theme / valence / wow / solicit) |
| `server/jetstream.py` | Websocket consumer + cursor persistence |
| `server/indexer.py` | Match → DB writes / deletes |
| `server/app.py` | XRPC + `did:web` endpoints |
| `data/eval_cases.json` | Stratified keep/drop fixtures |
| `publish_feed.py` | Create/update the generator record |

## Matching policy

Decision order:

```
allowlist → gazetteer other/local → hard negatives → strong regex →
event+venue → (ambiguous + context) → soft prior → DeepSeek quality rubric → drop
```

Provisional keeps (including allowlist / strong positives) that look like personal
money-asks or HelpSky-style fundraising boosts (Venmo, CashApp, GoFundMe,
`#HelpSky` / `#MutualAidRequest` / `💸`, “please help”, opaque quote+`#mutualaid`,
…) are rechecked by the quality rubric. If the classifier is offline, those
solicit-shaped posts are dropped.

**Keep** when:

- Strong phrases (`anarchism`, `mutual aid`, `dual power`, `Food Not Bombs`, `IWW`, `CrimethInc`, `AK Press`, …) and not a personal money-ask
- Ambiguous terms (`anarchy`, `direct action`, `libertarian`, `co-op`, …) with anarchist context
- Author is allowlisted (`data/allowlist_handles.txt` / `allowlist_dids.txt`) and not a personal money-ask
- Soft prior authors (repeated strong matches) use bare ambiguous terms
- Event phrasing + anarchist venue/project (`infoshop`, `bookfair`, `free skol`, …)
- DeepSeek (`deepseek-v4-flash`) clears the quality rubric gates on an ambiguous leftover

**Quality rubric** (see `server/classifier.py`):

| Dimension | Gate (defaults) |
|-----------|-----------------|
| `thematic_fit` | ≥ `CLASSIFIER_THEMATIC_MIN` (0.70) |
| `positive_valence` | ≥ `CLASSIFIER_VALENCE_MIN` (0.55) |
| `wow` | ≥ `CLASSIFIER_WOW_MIN` (0.45) |
| `solicit` (inverted) | ≤ `CLASSIFIER_SOLICIT_MAX` (0.35) |
| composite `0.45·theme + 0.25·valence + 0.30·wow` | ≥ `CLASSIFIER_COMPOSITE_MIN` (0.68) |

Personal Venmo/CashApp hardship asks score high on `solicit` and are dropped.
Collective org fundraisers and non-monetary mutual aid praxis can still keep.

**Drop** hard negatives / false friends:

- Anarcho-capitalism / ancap / Rothbard–Hoppe / Mises Institute framing
- Sons of Anarchy, Anarchy Online, “state of anarchy” chaos news
- DeFi / Web3 / NFT “decentralized” jargon without anarchist values
- Personal fundraising wrapped as “mutual aid”

## Local setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14+.

```bash
uv sync
cp .env.example .env
# For local dev:
# FEEDGEN_HOSTNAME=localhost
# SERVICE_DID=did:web:localhost
# DATABASE_PATH=./feed_database.db
# FEED_URI=at://did:plc:test/app.bsky.feed.generator/anarchism
# CLASSIFIER_ENABLED=false   # optional offline
# DEEPSEEK_API_KEY=…         # required when CLASSIFIER_ENABLED=true
```

### Lint, type-check, and test

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
uv run pytest -q
uv run python scripts/eval_filter.py --verbose
```

### Run the feedgen locally

```bash
uv run python -m server
```

Endpoints:

- `GET /healthz`
- `GET /.well-known/did.json`
- `GET /xrpc/app.bsky.feed.describeFeedGenerator`
- `GET /xrpc/app.bsky.feed.getFeedSkeleton?feed=<FEED_URI>`

## Publish the feed record

On your machine (not in a cloud agent), with a Bluesky app password:

```bash
# HANDLE, PASSWORD, FEEDGEN_HOSTNAME, RECORD_NAME, DISPLAY_NAME, DESCRIPTION
uv run python publish_feed.py
```

Put the printed URI into `FEED_URI` / Fly env.

## Deploy on Fly.io

```bash
fly apps create anarchist-bluesky-feed   # once
fly volumes create feed_data --region ewr --size 1
fly secrets set DEEPSEEK_API_KEY=…
fly deploy
```

`fly.toml` keeps **one always-on machine** (`auto_stop_machines = "off"`) because Jetstream must stay connected. Set `DEEPSEEK_API_KEY` as a Fly secret for the live AI pass.

Confirm:

```bash
curl -s https://anarchist-bluesky-feed.fly.dev/healthz
curl -s https://anarchist-bluesky-feed.fly.dev/.well-known/did.json
curl -s "https://anarchist-bluesky-feed.fly.dev/xrpc/app.bsky.feed.getFeedSkeleton?feed=$FEED_URI"
```

## Suggested iteration loop

```bash
uv run python scripts/collect_eval_sample.py authors --from-allowlist > /tmp/sample-authors.jsonl
uv run python scripts/collect_eval_sample.py near-miss > /tmp/sample-near-miss.jsonl
uv run python scripts/collect_eval_sample.py events > /tmp/sample-events.jsonl

# Optional LLM proposals (human confirm still required)
uv run python scripts/llm_label_judge.py --input /tmp/sample-near-miss.jsonl --output /tmp/proposed.jsonl

uv run python scripts/append_eval_cases.py --input /tmp/labeled.jsonl
uv run python scripts/eval_filter.py && uv run pytest -q
```

After matcher changes, audit/purge stale rows with `scripts/audit_indexed_feed.py`.
If Jetstream skips a lag gap, backfill with `scripts/backfill_gap.py`.
