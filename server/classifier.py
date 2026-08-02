"""Second-pass values-alignment classifier (DeepSeek).

The regex floor in ``matcher.match_post`` keeps strong positives / hard
negatives / allowlists / soft priors / definitive event+venue hits. Remaining
ambiguous and near-miss candidates are scored here for prosocial anarchist
values alignment via ``deepseek-v4-flash``.

Network calls are optional: when the classifier is disabled or no API key is
configured, this module declines (``None``) so the matcher keeps its regex-floor
drop reason. Tests inject a ``ClassifierBackend``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

DEFAULT_MODEL = 'deepseek-v4-flash'
DEFAULT_API_URL = 'https://api.deepseek.com/v1/chat/completions'
DEFAULT_THRESHOLD = 0.72
DEFAULT_TIMEOUT_S = 8.0
DEFAULT_MAX_TEXT_CHARS = 1200

SYSTEM_PROMPT = """\
You score Bluesky posts for a prosocial anarchist feed.

Anarchism here means movements and projects that want to decentralize both
political power and capital: mutual aid, dual power, horizontal organizing,
worker autonomy, commons stewardship, anti-authoritarian and anti-capitalist
practice, and celebrations of those currents.

Return JSON only:
{"keep": true|false, "score": 0.0-1.0, "rationale": "<short reason>"}

keep=true when the post is substantially about or celebrating that anarchism
(including adjacent praxis like Food Not Bombs, IWW, infoshops, bookfairs,
CrimethInc, AK Press, social ecology) even if it never says "anarchism".

keep=false for:
- anarcho-capitalism / right-"libertarian" market fundamentalism
- chaos / entertainment "anarchy" with no political content
- crypto/Web3/DeFi "decentralized" jargon without anarchist values
- generic left slogans with no anarchist or anti-authoritarian signal
- authoritarian state-socialist celebration of centralized power

score is values-alignment / relevancy in [0,1]. Prefer precision when unsure.
"""


@dataclass(frozen=True)
class ClassifierDecision:
    matched: bool
    reason: str
    score: float


class ClassifierBackend(Protocol):
    def classify(
        self,
        haystack: str,
        *,
        term: str | None,
        has_event_cue: bool,
        has_local_venue: bool,
    ) -> ClassifierDecision | None: ...


JudgeFn = Callable[[str], dict[str, Any]]


@dataclass(frozen=True)
class ClassifierModel:
    """Compatibility shim / offline stub for tests that pass a local scorer."""

    version: str
    threshold: float
    weights: dict[str, float]

    def score(self, features: dict[str, float]) -> float:
        total = self.weights.get('bias', 0.0)
        for name, value in features.items():
            if name == 'bias':
                continue
            total += self.weights.get(name, 0.0) * value
        return total

    def classify(
        self,
        haystack: str,
        *,
        term: str | None,
        has_event_cue: bool,
        has_local_venue: bool,
    ) -> ClassifierDecision | None:
        del haystack, has_event_cue, has_local_venue
        # Offline stub: never keep unless tests override via FakeBackend.
        del term
        return None


@dataclass
class DeepSeekClassifier:
    """Live DeepSeek values-alignment scorer with a small in-process cache."""

    api_key: str
    model: str = DEFAULT_MODEL
    api_url: str = DEFAULT_API_URL
    threshold: float = DEFAULT_THRESHOLD
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS
    _cache: dict[str, ClassifierDecision | None] | None = None
    _judge: JudgeFn | None = None

    def __post_init__(self) -> None:
        if self._cache is None:
            self._cache = {}

    def classify(
        self,
        haystack: str,
        *,
        term: str | None,
        has_event_cue: bool,
        has_local_venue: bool,
    ) -> ClassifierDecision | None:
        text = (haystack or '').strip()
        if not text:
            return None
        clipped = text[: self.max_text_chars]
        cache_key = hashlib.sha256(
            f'{self.model}|{self.threshold}|{term}|{int(has_event_cue)}|'
            f'{int(has_local_venue)}|{clipped}'.encode()
        ).hexdigest()
        assert self._cache is not None
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            payload = self._judge(clipped) if self._judge else self._call_api(clipped, term=term)
        except urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError:
            self._cache[cache_key] = None
            return None

        decision = _decision_from_payload(payload, term=term, threshold=self.threshold)
        self._cache[cache_key] = decision
        return decision

    def _call_api(self, text: str, *, term: str | None) -> dict[str, Any]:
        user = {
            'text': text,
            'ambiguous_term': term,
            'instruction': 'Score values alignment for the prosocial anarchist feed.',
        }
        body = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': json.dumps(user, ensure_ascii=False)},
            ],
            'response_format': {'type': 'json_object'},
            'temperature': 0.0,
            'max_tokens': 256,
            'thinking': {'type': 'disabled'},
        }
        request = urllib.request.Request(
            self.api_url,
            data=json.dumps(body).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'anarchist-bluesky-feed-classifier/0.1',
            },
            method='POST',
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            raw = json.loads(response.read().decode('utf-8'))
        content = raw['choices'][0]['message']['content']
        return _parse_json_object(content)


@dataclass(frozen=True)
class FakeClassifier:
    """Deterministic backend for unit tests (no network)."""

    keep_terms: frozenset[str] = frozenset()
    keep_substrings: tuple[str, ...] = ()
    score: float = 0.9

    def classify(
        self,
        haystack: str,
        *,
        term: str | None,
        has_event_cue: bool,
        has_local_venue: bool,
    ) -> ClassifierDecision | None:
        del has_event_cue, has_local_venue
        lowered = haystack.lower()
        if term and term.lower() in self.keep_terms:
            return ClassifierDecision(True, f'classifier:ambiguous:{term.lower()}', self.score)
        for needle in self.keep_substrings:
            if needle.lower() in lowered:
                label = f'ambiguous:{term.lower()}' if term else 'values_align'
                return ClassifierDecision(True, f'classifier:{label}', self.score)
        return None


def _parse_json_object(content: str) -> dict[str, Any]:
    text = (content or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError('classifier response is not a JSON object')
    return data


def _decision_from_payload(
    payload: dict[str, Any],
    *,
    term: str | None,
    threshold: float,
) -> ClassifierDecision | None:
    keep = bool(payload.get('keep'))
    try:
        score = float(payload.get('score', 0.0))
    except TypeError, ValueError:
        score = 0.0
    if not keep or score < threshold:
        return None
    if term:
        label = f'ambiguous:{term}'
    else:
        label = 'values_align'
    return ClassifierDecision(True, f'classifier:{label}', score)


def classifier_enabled() -> bool:
    raw = os.environ.get('CLASSIFIER_ENABLED', 'true').strip().lower()
    return raw in {'1', 'true', 't', 'yes', 'y'}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)


def build_default_classifier() -> ClassifierBackend | None:
    if not classifier_enabled():
        return None
    api_key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    if not api_key:
        return None
    return DeepSeekClassifier(
        api_key=api_key,
        model=os.environ.get('CLASSIFIER_MODEL', DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        api_url=os.environ.get('DEEPSEEK_API_URL', DEFAULT_API_URL).strip() or DEFAULT_API_URL,
        threshold=_env_float('CLASSIFIER_THRESHOLD', DEFAULT_THRESHOLD),
        timeout_s=_env_float('CLASSIFIER_TIMEOUT_S', DEFAULT_TIMEOUT_S),
        max_text_chars=int(_env_float('CLASSIFIER_MAX_TEXT_CHARS', float(DEFAULT_MAX_TEXT_CHARS))),
    )


@lru_cache(maxsize=1)
def _cached_default_classifier() -> ClassifierBackend | None:
    return build_default_classifier()


def clear_model_cache() -> None:
    """Test helper: drop the cached default classifier."""
    _cached_default_classifier.cache_clear()


def load_model(path: Any = None) -> ClassifierModel:
    """Back-compat helper used by older tests; returns a no-op stub."""
    del path
    return ClassifierModel(version='deepseek_v4_flash', threshold=DEFAULT_THRESHOLD, weights={})


def extract_features(
    haystack: str,
    *,
    term: str | None,
    has_event_cue: bool,
    has_local_venue: bool,
) -> dict[str, float]:
    """Lightweight feature view for debugging / offline scripts."""
    return {
        'has_event_cue': 1.0 if has_event_cue else 0.0,
        'has_local_venue': 1.0 if has_local_venue else 0.0,
        'has_ambiguous': 1.0 if term else 0.0,
        'text_len': float(min(len(haystack or ''), 2000)),
    }


def classify_candidate(
    haystack: str,
    *,
    term: str | None,
    has_event_cue: bool,
    has_local_venue: bool,
    classifier: ClassifierBackend | None = None,
    model: ClassifierBackend | None = None,
) -> ClassifierDecision | None:
    """Score an ambiguous candidate; return a keep decision or None to drop.

    Production only reaches this for ambiguous-term leftovers after the regex
    floor. Without a latchable ``term`` (and no injected backend), decline so
    the firehose path never pays for open-ended AI scoring.
    """
    backend = classifier if classifier is not None else model
    if backend is None:
        if not term:
            return None
        backend = _cached_default_classifier()
    if backend is None:
        return None

    return backend.classify(
        haystack,
        term=term,
        has_event_cue=has_event_cue,
        has_local_venue=has_local_venue,
    )
