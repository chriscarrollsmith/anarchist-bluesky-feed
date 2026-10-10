import os

from dotenv import load_dotenv

from server.allowlists import (
    load_allowlist_dids,
    load_allowlist_handles,
    load_blocklist_dids,
    load_blocklist_handles,
)
from server.logger import logger

# Override process env so a shell HOSTNAME cannot beat .env / Fly config.
load_dotenv(override=True)


def _get_bool_env_var(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {'1', 'true', 't', 'yes', 'y'}


# FEEDGEN_HOSTNAME avoids colliding with the OS/shell HOSTNAME variable.
_hostname = os.environ.get('FEEDGEN_HOSTNAME') or os.environ.get('HOSTNAME')
if not _hostname or _hostname == 'cursor':
    raise RuntimeError(
        'Set FEEDGEN_HOSTNAME (or HOSTNAME) to your public feedgen hostname '
        '(e.g. mutualist-bluesky-feed.fly.dev).'
    )
HOSTNAME: str = _hostname

SERVICE_DID = os.environ.get('SERVICE_DID') or f'did:web:{HOSTNAME}'

_feed_uri = os.environ.get('FEED_URI')
if not _feed_uri:
    raise RuntimeError('Set FEED_URI after publishing the Bluesky feed generator record.')
FEED_URI: str = _feed_uri

IGNORE_ARCHIVED_POSTS = _get_bool_env_var(os.environ.get('IGNORE_ARCHIVED_POSTS', 'true'))
IGNORE_REPLY_POSTS = _get_bool_env_var(os.environ.get('IGNORE_REPLY_POSTS', 'true'))
POST_RETENTION_DAYS = int(os.environ.get('POST_RETENTION_DAYS', '7'))
# Soft priors: authors with this many strong text matches in the window may keep
# bare ambiguous terms (never hard negatives). See server/author_priors.py.
SOFT_PRIOR_MIN_STRONG = int(os.environ.get('SOFT_PRIOR_MIN_STRONG', '3'))
SOFT_PRIOR_WINDOW_DAYS = int(os.environ.get('SOFT_PRIOR_WINDOW_DAYS', '30'))
DATABASE_PATH = os.environ.get('DATABASE_PATH', 'feed_database.db')
JETSTREAM_URL = os.environ.get(
    'JETSTREAM_URL',
    'wss://jetstream2.us-east.bsky.network/subscribe',
)
PORT = int(os.environ.get('PORT', '8080'))
RANKING_MODE = os.environ.get('RANKING_MODE', 'indexed').strip().lower()
if RANKING_MODE not in {'indexed', 'created', 'engagement'}:
    raise RuntimeError(
        f'RANKING_MODE must be indexed, created, or engagement (got {RANKING_MODE!r})'
    )
# Comma-separated substrings; matched posts containing any are not indexed.
MUTED_KEYWORDS = tuple(
    part.strip().lower() for part in os.environ.get('MUTED_KEYWORDS', '').split(',') if part.strip()
)

# DeepSeek quality rubric (ambiguous leftovers + solicit-shaped provisional keeps).
CLASSIFIER_ENABLED = _get_bool_env_var(os.environ.get('CLASSIFIER_ENABLED', 'true'))
CLASSIFIER_MODEL = os.environ.get('CLASSIFIER_MODEL', 'deepseek-v4-flash').strip()
# Composite floor; CLASSIFIER_THRESHOLD is a legacy alias read by classifier.py.
CLASSIFIER_COMPOSITE_MIN = float(
    os.environ.get('CLASSIFIER_COMPOSITE_MIN') or os.environ.get('CLASSIFIER_THRESHOLD', '0.68')
)
CLASSIFIER_THRESHOLD = CLASSIFIER_COMPOSITE_MIN
CLASSIFIER_THEMATIC_MIN = float(os.environ.get('CLASSIFIER_THEMATIC_MIN', '0.70'))
CLASSIFIER_VALENCE_MIN = float(os.environ.get('CLASSIFIER_VALENCE_MIN', '0.55'))
CLASSIFIER_WOW_MIN = float(os.environ.get('CLASSIFIER_WOW_MIN', '0.45'))
CLASSIFIER_SOLICIT_MAX = float(os.environ.get('CLASSIFIER_SOLICIT_MAX', '0.35'))
DEEPSEEK_API_KEY_SET = bool(os.environ.get('DEEPSEEK_API_KEY', '').strip())

ALLOWLIST_DIDS = load_allowlist_dids()
ALLOWLIST_HANDLES = load_allowlist_handles()
BLOCKLIST_DIDS = load_blocklist_dids()
BLOCKLIST_HANDLES = load_blocklist_handles()

logger.info(
    'config loaded hostname=%s service_did=%s allowlist_dids=%d allowlist_handles=%d '
    'blocklist_dids=%d blocklist_handles=%d '
    'soft_prior_min=%d soft_prior_window_days=%d ranking_mode=%s muted_keywords=%d '
    'classifier_enabled=%s classifier_model=%s deepseek_key=%s '
    'rubric_thematic>=%.2f valence>=%.2f wow>=%.2f solicit<=%.2f composite>=%.2f',
    HOSTNAME,
    SERVICE_DID,
    len(ALLOWLIST_DIDS),
    len(ALLOWLIST_HANDLES),
    len(BLOCKLIST_DIDS),
    len(BLOCKLIST_HANDLES),
    SOFT_PRIOR_MIN_STRONG,
    SOFT_PRIOR_WINDOW_DAYS,
    RANKING_MODE,
    len(MUTED_KEYWORDS),
    CLASSIFIER_ENABLED,
    CLASSIFIER_MODEL,
    'set' if DEEPSEEK_API_KEY_SET else 'missing',
    CLASSIFIER_THEMATIC_MIN,
    CLASSIFIER_VALENCE_MIN,
    CLASSIFIER_WOW_MIN,
    CLASSIFIER_SOLICIT_MAX,
    CLASSIFIER_COMPOSITE_MIN,
)
