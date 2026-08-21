"""Prosocial anarchist post matcher.

Keeps posts that celebrate or practice anarchism under a broad definition:
movements and projects that want to decentralize both political power and
capital — mutual aid, dual power, horizontal organizing, worker autonomy,
commons stewardship, and related anti-authoritarian currents.

Rejects common false positives:
- Anarcho-capitalism / right-"libertarian" market fundamentalism
- Chaos / entertainment uses of "anarchy" without political content
- Crypto/Web3 "decentralized" jargon without anarchist values
- Bare ambiguous left terms without anarchist context
- Personal fundraising / extractive "mutual aid" money asks (quality rubric)

Recall without keywords comes from author allowlists and soft author priors
earned from repeated strong text matches. Author blocklists drop an account
even when the text would otherwise keep. Ambiguous leftovers — and
provisional keeps that look like money asks — route to the DeepSeek quality
rubric (see ``server/classifier.py``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

from server.classifier import ClassifierBackend, ClassifierDecision, classify_candidate
from server.gazetteer import Gazetteer, default_gazetteer


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    reason: str


# Phrases that almost always mean prosocial / left anarchism.
_STRONG_POSITIVE = re.compile(
    r"""
    (?:
        \#anarchism\b
      | \#anarchist\b
      | \#anarchy\b
      | \#mutualaid\b
      | \#directaction\b
      | \#anarchocommunism\b
      | \#anarchosyndicalism\b
      | \banarchism\b
      | \banarchists?\b
      | anarcho[\s-]?syndical(?:ism|ist)s?
      | anarcho[\s-]?communis(?:m|t)s?
      | anarcho[\s-]?feminis(?:m|t)s?
      | anarcho[\s-]?primitivis(?:m|t)s?
      | mutual\s+aid
      | dual\s+power
      | prefigurative(?:\s+politics)?
      | horizontalis[mt]
      | horizontalidad
      | food\s+not\s+bombs
      | \bcrimethinc\b
      | no\s+gods?,?\s+no\s+masters
      | free\s+association
      | affinity\s+groups?
      | \binfoshops?\b
      | anarchist\s+bookfair
      | black\s+rose\s+anarchist
      | institute\s+for\s+anarchist\s+studies
      | perspectives\s+on\s+anarchist\s+theory
      | \bak\s+press\b
      | social\s+ecology
      | \bbookchin\b
      | \bkropotkin\b
      | emma\s+goldman
      | \bwobblies\b
      | industrial\s+workers\s+of\s+the\s+world
      | \bi\.?w\.?w\.?\b
      | worker(?:s)?(?:'s|s')?\s+self[\s-]?management
      | seize\s+the\s+means
      | commons[\s-]based
      | solidarity\s+economy
      | anti[\s-]?authoritarian
      | without\s+(?:bosses|rulers|masters)
      | abolish\s+(?:the\s+)?(?:state|capitalism|wage\s+labor|prisons?)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Ambiguous terms that need anarchist / anti-capitalist context (or AI).
_AMBIGUOUS_TERM = re.compile(
    r"""
    (?:
        \banarchy\b
      | \blibertarian\b
      | \bautonom(?:y|ous|ist)s?\b
      | direct\s+action
      | \bmutualism\b
      | \bcommunes?\b
      | decentraliz(?:e|ed|ing|ation)
      | \bantifa(?:scist)?\b
      | \bacab\b
      | \bpunk\b
      | \bcooperatives?\b
      | \bco[\s-]?ops?\b
      | \bsocialis(?:m|t)s?\b
      | \bcommunis(?:m|t)s?\b
      | free\s+the\s+people
      | no\s+rulers
      | power\s+to\s+the\s+people
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Context that unlocks ambiguous terms toward keep.
# Intentionally excludes bare "anarchy" / "anarchist" / "anarchism" — those are
# either strong positives on their own or the ambiguous term being gated.
_ANARCHIST_CONTEXT = re.compile(
    r"""
    (?:
        mutual\s+aid
      | dual\s+power
      | anti[\s-]?authoritarian
      | anti[\s-]?capitalis(?:m|t)
      | horizontal
      | prefigurative
      | without\s+(?:bosses|rulers|masters)
      | abolish\s+(?:the\s+)?(?:state|capitalism)
      | \binfoshop\b
      | \bzines?\b
      | bookfair
      | \bwobbl(?:y|ies)\b
      | \bi\.?w\.?w\.?\b
      | food\s+not\s+bombs
      | \bcrimethinc\b
      | left[\s-]?libertarian
      | liberatory
      | \bcommons\b
      | expropriat
      | \bsyndical
      | no\s+gods?
      | no\s+masters
      | no\s+bosses
      | no\s+rulers
      | no\s+landlords
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Hard negatives that always win over an otherwise-strong phrase when they
# clearly indicate right-"libertarian" / ancap / entertainment collisions.
# Collisions that should not be rescued by a nearby strong anarchist phrase.
# Plain "anarcho-capitalism" is intentionally absent so critiques like
# "anarchism is not anarcho-capitalism" can still keep via strong_positive_over_negative.
_HARD_NEGATIVE_BLOCKS_STRONG = re.compile(
    r"""
    (?:
        sons\s+of\s+anarchy
      | anarchy\s+online
      | decentralized\s+finance
      | \bdefi\b
      | \bweb3\b
      | sovereign\s+citizens?
      | mises\s+institute
      | \brothbard\b
      | \bhoppean\b
      | hans[\s-]hermann\s+hoppe
      | \bvoluntaryism\b
      | free[\s-]market\s+anarch
      | property[\s-]rights\s+anarch
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_HARD_NEGATIVE = re.compile(
    r"""
    (?:
        anarcho[\s-]?capitalis(?:m|t)s?
      | \bancaps?\b
      | \banarcho[\s-]?cap\b
      | \brothbard\b
      | \bhoppean\b
      | hans[\s-]hermann\s+hoppe
      | mises\s+institute
      | \bvoluntaryism\b
      | property[\s-]rights\s+anarch
      | free[\s-]market\s+anarch
      | sons\s+of\s+anarchy
      | anarchy\s+online
      | decentralized\s+(?:finance|exchange|autonomous\s+organization)
      | \bdefi\b
      | \bnfts?\b.{0,40}decentral
      | decentral.{0,40}\bnfts?\b
      | \bweb3\b
      | sovereign\s+citizens?
      | this\s+is\s+anarchy!
      | pure\s+chaos\s+anarchy
      | state\s+of\s+anarchy
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Upcoming-event phrasing unlocks high-confidence anarchist venues/projects.
_EVENT_CUE = re.compile(
    r"""
    \b(?:
        tonight|tomorrow|this\s+weekend|this\s+saturday|this\s+sunday|
        next\s+(?:friday|saturday|sunday|week)|
        doors(?:\s+at|\s+open)|tickets?|presale|save\s+the\s+date|join\s+us|
        open\s+mic|festival|bookfair|distro|teach[\s-]?in|assembly|
        \d{1,2}:\d{2}\s*(?:am|pm)|(?<!\d)\d{1,2}\s*(?:am|pm)\b|
        january|february|march|april|june|july|august|september|
        october|november|december
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_LOCAL_EVENT_VENUE = re.compile(
    r"""
    (?:
        anarchist\s+bookfair
      | \binfoshops?\b
      | food\s+not\s+bombs
      | free\s+skoo?l
      | mutual\s+aid\s+(?:distro|clinic|network|hub)
      | really\s+really\s+free\s+market
      | \bdistro\b.{0,40}\bzines?\b
      | \bzines?\b.{0,40}\bdistro\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Mutual-aid token used to pair boost/ask vernacular with the strong phrase.
_MUTUAL_AID_TOKEN = re.compile(
    r'(?:\#mutualaid\b|mutual\s+aid)',
    re.IGNORECASE,
)

# Cheap cue that a provisional keep may be a personal money-ask. Forces a
# quality-rubric pass (solicit gate) when the classifier is available; when it
# is not, the post is dropped for precision.
#
# Includes Bluesky "HelpSky" fundraising hashtag culture and short boost/ask
# shapes that otherwise sail through on bare ``#mutualaid`` / "mutual aid".
_SOLICIT_CUE = re.compile(
    r"""
    (?:
        \bvenmo\b
      | \bcash\s*app\b
      | \bcashapp\b
      | \bpaypal(?:\.me)?\b
      | gofund\.?\s*me
      | \bgofundme\b
      | \bko-?fi\b
      | \bpatreon\b
      | please\s+(?:donate|venmo|cash\s*app|send\s+(?:money|cash|\$))
      | \bdonat(?:e|ions?)\s+to\s+me\b
      | mutual\s+aid\s+request
      | \bneed(?:s|ing)?\s+(?:mutual\s+aid|donations?|money|rent|funds?)\b
      | \bcan\s+you\s+(?:spare|send|donate)\b
      | \bsend\s+(?:me\s+)?(?:\$|money|venmo|cash)
      | \bdm\s+me\s+for\s+(?:my\s+)?(?:venmo|cash\s*app|cashapp|paypal)
      | \#helpsky\b
      | \#helpfolkslive\b
      | \#mutualaidrequest\b
      | \#mutualaidboost\b
      | \#mutualaidsaveslives\b
      | \#urgentmutualaid\b
      | \#emergencyma\b
      | \#maboost\b
      | \#madboost\b
      | \#fundsky\b
      | \#lgbtqma\b
      | \#bipocma\b
      | 💸
      | \banything\s+helps\b
      | \brent\s+due\b
      | \b(?:urgent|immediate)\b.{0,60}(?:\#mutualaid\b|mutual\s+aid|\#emergencyma\b)
      | \bplease\s+(?:help|assist|donate|boost)\b.{0,60}
        (?:\#mutualaid\b|mutual\s+aid|venmo|cash|\$|donat|rent)
      | (?:\#mutualaid\b|mutual\s+aid).{0,60}\bplease\s+(?:help|assist|donate|boost)\b
      | \b(?:bumping|boosting|amplifying|re-?sharing|passing\s+along)\b
        .{0,80}(?:\#mutualaid\b|mutual\s+aid)
      | (?:\#mutualaid\b|mutual\s+aid).{0,40}\b(?:plz|pls|please)\b
      | \b(?:plz|pls)\b.{0,40}(?:\#mutualaid\b|mutual\s+aid)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_HANDLE_MENTION = re.compile(r'(?<![\w.])@[\w.-]+', flags=re.UNICODE)

_EMBED_TEXT_MAX = 320


def _normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


def _clip_embed_text(value: object, *, max_len: int = _EMBED_TEXT_MAX) -> str:
    text = str(value or '').strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip()


def _record_embed_payload(embed: object | None) -> dict[str, Any] | None:
    """Return the inner record/ref dict for quote embeds, if present."""
    if isinstance(embed, dict):
        record_obj = embed.get('record')
        if not isinstance(record_obj, dict):
            return None
        record = cast(dict[str, Any], record_obj)
        # recordWithMedia nests the quote under record.record.
        nested_obj = record.get('record')
        if isinstance(nested_obj, dict):
            nested = cast(dict[str, Any], nested_obj)
            if 'uri' in nested or 'cid' in nested or 'value' in nested or 'text' in nested:
                return nested
        return record
    record_attr = getattr(embed, 'record', None) if embed is not None else None
    if record_attr is None:
        return None
    nested_attr = getattr(record_attr, 'record', None)
    if nested_attr is not None and (
        getattr(nested_attr, 'uri', None)
        or getattr(nested_attr, 'cid', None)
        or getattr(nested_attr, 'value', None)
        or getattr(nested_attr, 'text', None)
    ):
        if isinstance(nested_attr, dict):
            return cast(dict[str, Any], nested_attr)
        uri = getattr(nested_attr, 'uri', None)
        return {'uri': uri} if uri else None
    return cast(dict[str, Any], record_attr) if isinstance(record_attr, dict) else None


def _quoted_record_text(record_payload: dict[str, Any]) -> str:
    """Best-effort text from a hydrated quote payload (AppView) or empty."""
    for key in ('value', 'record'):
        nested = record_payload.get(key)
        if isinstance(nested, dict):
            text = nested.get('text')
            if isinstance(text, str) and text.strip():
                return text
    text = record_payload.get('text')
    return text if isinstance(text, str) else ''


def is_opaque_record_embed(embed: object | None) -> bool:
    """True when a quote embed is only a strong ref (Jetstream create shape).

    Firehose records carry ``uri``/``cid`` without the quoted post body. Boost
    accounts wrap personal fundraisers this way while the outer text is just
    ``#MutualAid #HelpSky`` — without hydration we cannot see PayPal/Ko-fi in
    the quote, so mutual-aid + opaque quote is treated as solicit-shaped.
    """
    payload = _record_embed_payload(embed)
    if not payload:
        return False
    if _quoted_record_text(payload).strip():
        return False
    uri = payload.get('uri')
    cid = payload.get('cid')
    return bool(uri or cid)


def extract_alt_text(embed: object | None) -> str:
    """Pull alt text from common Bluesky embed shapes (dict or SDK-like)."""
    if not embed:
        return ''

    chunks: list[str] = []

    if isinstance(embed, dict):
        images = embed.get('images')
        if isinstance(images, list):
            for image in images:
                if not isinstance(image, dict):
                    continue
                alt = image.get('alt')
                if alt:
                    chunks.append(_clip_embed_text(alt))
        external = embed.get('external')
        if isinstance(external, dict):
            title = external.get('title')
            if title:
                chunks.append(_clip_embed_text(title))
            description = external.get('description')
            if description:
                chunks.append(_clip_embed_text(description))
        media = embed.get('media')
        if isinstance(media, dict):
            chunks.append(extract_alt_text(media))
        record_payload = _record_embed_payload(embed)
        if record_payload is not None:
            quoted = _quoted_record_text(record_payload)
            if quoted:
                chunks.append(_clip_embed_text(quoted))
            for key in ('value', 'record'):
                nested = record_payload.get(key)
                if isinstance(nested, dict):
                    chunks.append(extract_alt_text(nested.get('embed')))
                    break
            else:
                chunks.append(extract_alt_text(record_payload.get('embed')))
        return ' '.join(chunk for chunk in chunks if chunk)

    images = getattr(embed, 'images', None)
    if isinstance(images, list):
        for image in images:
            alt = getattr(image, 'alt', None)
            if alt:
                chunks.append(_clip_embed_text(alt))
    external = getattr(embed, 'external', None)
    if external is not None:
        title = getattr(external, 'title', None)
        if title:
            chunks.append(_clip_embed_text(title))
        description = getattr(external, 'description', None)
        if description:
            chunks.append(_clip_embed_text(description))
    return ' '.join(chunk for chunk in chunks if chunk)


def combine_text(text: str = '', *, alt_text: str = '', langs: Iterable[str] | None = None) -> str:
    del langs
    return _normalize(f'{text} {alt_text}')


def _normalize_langs(langs: Iterable[str] | None) -> list[str]:
    if not langs:
        return []
    out: list[str] = []
    for lang in langs:
        token = str(lang or '').strip().lower().replace('_', '-')
        if token:
            out.append(token)
    return out


def _haystack_without_handles(haystack: str) -> str:
    return _HANDLE_MENTION.sub(' ', haystack)


def _soft_prior_ambiguous(
    author_did: str | None,
    soft_prior_dids: set[str],
    term: str,
) -> MatchResult | None:
    if author_did and author_did in soft_prior_dids:
        return MatchResult(True, f'soft_prior_ambiguous:{term}')
    return None


def _match_local_event(haystack: str) -> MatchResult | None:
    if not _EVENT_CUE.search(haystack):
        return None
    match = _LOCAL_EVENT_VENUE.search(haystack)
    if not match:
        return None
    venue = re.sub(r'\s+', ' ', match.group(0).lower())
    return MatchResult(True, f'event_local_venue:{venue}')


def looks_like_solicit(
    haystack: str,
    *,
    embed: object | None = None,
    opaque_record_embed: bool | None = None,
) -> bool:
    """True when text/alt looks like a personal money-ask or fundraising boost.

    Also true for mutual-aid posts that quote another record without hydrated
    quote text (common Jetstream shape for HelpSky-style boost accounts).
    """
    if _SOLICIT_CUE.search(haystack or ''):
        return True
    opaque = is_opaque_record_embed(embed) if opaque_record_embed is None else opaque_record_embed
    return bool(opaque and _MUTUAL_AID_TOKEN.search(haystack or ''))


def _run_classifier(
    haystack: str,
    *,
    term: str | None,
    classifier: ClassifierBackend | None,
    allow_without_term: bool = False,
) -> ClassifierDecision | None:
    return classify_candidate(
        haystack,
        term=term,
        has_event_cue=bool(_EVENT_CUE.search(haystack)),
        has_local_venue=bool(_LOCAL_EVENT_VENUE.search(haystack)),
        classifier=classifier,
        allow_without_term=allow_without_term,
    )


def _classifier_keep(
    haystack: str,
    *,
    term: str | None,
    classifier: ClassifierBackend | None,
) -> MatchResult | None:
    decision = _run_classifier(haystack, term=term, classifier=classifier)
    if decision is None:
        return None
    if not decision.matched:
        return MatchResult(False, decision.reason)
    return MatchResult(True, decision.reason)


def _maybe_quality_gate(
    haystack: str,
    provisional: MatchResult,
    *,
    classifier: ClassifierBackend | None,
    embed: object | None = None,
) -> MatchResult:
    """Re-score solicit-shaped provisional keeps via the quality rubric."""
    if not provisional.matched or not looks_like_solicit(haystack, embed=embed):
        return provisional
    decision = _run_classifier(
        haystack,
        term=None,
        classifier=classifier,
        allow_without_term=True,
    )
    if decision is None:
        return MatchResult(False, f'solicit_cue_unscored:{provisional.reason}')
    if not decision.matched:
        return MatchResult(False, decision.reason)
    return provisional


def match_post(
    text: str,
    *,
    alt_text: str = '',
    langs: Iterable[str] | None = None,
    author_did: str | None = None,
    author_handle: str | None = None,
    allowlist_dids: set[str] | None = None,
    allowlist_handles: set[str] | None = None,
    blocklist_dids: set[str] | None = None,
    blocklist_handles: set[str] | None = None,
    soft_prior_dids: set[str] | None = None,
    classifier: ClassifierBackend | None = None,
    classifier_model: ClassifierBackend | None = None,
    gazetteer: Gazetteer | None = None,
    embed: object | None = None,
) -> MatchResult:
    """Return whether a post belongs in the prosocial anarchist feed.

    Decision order: blocklist → allowlist (+ solicit gate) → gazetteer
    other-entity → hard negative / gazetteer local / strong regex →
    event+venue → ambiguous+context → soft prior → quality rubric classifier
    → drop.

    Provisional regex/allowlist keeps that look like money asks are rechecked
    by the quality rubric when available; otherwise they are dropped.

    ``embed`` is the raw Bluesky embed object (Jetstream or AppView). Opaque
    quote refs paired with mutual-aid language are solicit-gated even when the
    quoted body is not hydrated yet.

    ``classifier`` (or legacy ``classifier_model``) is for tests; production
    uses the DeepSeek backend when ``CLASSIFIER_ENABLED`` is set.
    """
    allowlist_dids = allowlist_dids or set()
    allowlist_handles = {h.lower() for h in (allowlist_handles or set())}
    blocklist_dids = blocklist_dids or set()
    blocklist_handles = {h.lower() for h in (blocklist_handles or set())}
    soft_prior_dids = soft_prior_dids or set()
    places = gazetteer if gazetteer is not None else default_gazetteer()
    lang_tags = _normalize_langs(langs)
    backend = classifier if classifier is not None else classifier_model

    if author_did and author_did in blocklist_dids:
        return MatchResult(False, 'blocklist_did')
    if author_handle and author_handle.lower() in blocklist_handles:
        return MatchResult(False, 'blocklist_handle')

    haystack = combine_text(text, alt_text=alt_text, langs=lang_tags)

    if author_did and author_did in allowlist_dids:
        provisional = MatchResult(True, 'allowlist_did')
        return _maybe_quality_gate(haystack, provisional, classifier=backend, embed=embed)
    if author_handle and author_handle.lower() in allowlist_handles:
        provisional = MatchResult(True, 'allowlist_handle')
        return _maybe_quality_gate(haystack, provisional, classifier=backend, embed=embed)

    if not haystack:
        return MatchResult(False, 'empty')

    entity = places.lookup(haystack)
    strong_hit = _STRONG_POSITIVE.search(haystack)

    if entity is not None and entity.region == 'other' and not strong_hit:
        return MatchResult(False, f'entity_other:{entity.entity_id}')

    if _HARD_NEGATIVE.search(haystack):
        if strong_hit and not _HARD_NEGATIVE_BLOCKS_STRONG.search(haystack):
            return _maybe_quality_gate(
                haystack,
                MatchResult(True, 'strong_positive_over_negative'),
                classifier=backend,
                embed=embed,
            )
        return MatchResult(False, 'hard_negative')

    if entity is not None and entity.region == 'local':
        return _maybe_quality_gate(
            haystack,
            MatchResult(True, f'entity_local:{entity.entity_id}'),
            classifier=backend,
            embed=embed,
        )

    if strong_hit:
        return _maybe_quality_gate(
            haystack,
            MatchResult(True, 'strong_positive'),
            classifier=backend,
            embed=embed,
        )

    event_match = _match_local_event(haystack)
    if event_match is not None:
        return _maybe_quality_gate(haystack, event_match, classifier=backend, embed=embed)

    place_haystack = _haystack_without_handles(haystack)
    ambiguous_hits = _AMBIGUOUS_TERM.findall(place_haystack)
    if ambiguous_hits:
        distinct = {re.sub(r'\s+', ' ', h.lower()) for h in ambiguous_hits}
        term = sorted(distinct)[0]

        if _ANARCHIST_CONTEXT.search(place_haystack) or _STRONG_POSITIVE.search(haystack):
            return _maybe_quality_gate(
                haystack,
                MatchResult(True, f'ambiguous_with_context:{term}'),
                classifier=backend,
                embed=embed,
            )

        prior = _soft_prior_ambiguous(author_did, soft_prior_dids, term)
        if prior:
            return _maybe_quality_gate(haystack, prior, classifier=backend, embed=embed)

        clf = _classifier_keep(haystack, term=term, classifier=backend)
        return clf if clf else MatchResult(False, f'ambiguous_no_context:{term}')

    # No ambiguous latch → do not spend AI quota on every firehose post.
    return MatchResult(False, 'no_match')
