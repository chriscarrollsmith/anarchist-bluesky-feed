import json
from pathlib import Path
from typing import Any

import pytest
from server.allowlists import load_allowlist_dids, load_allowlist_handles
from server.classifier import FakeClassifier
from server.matcher import extract_alt_text, match_post

ALL_CASES = json.loads(
    (Path(__file__).resolve().parents[1] / 'data' / 'eval_cases.json').read_text(encoding='utf-8')
)
CASES = [c for c in ALL_CASES if c.get('regression', True)]

ALLOWLIST_HANDLES = load_allowlist_handles()
ALLOWLIST_DIDS = load_allowlist_dids()


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_eval_case(case: dict[str, Any]) -> None:
    soft_prior_dids: set[str] = set()
    if case.get('soft_prior') and case.get('author_did'):
        soft_prior_dids.add(str(case['author_did']))
    langs = case.get('langs')
    result = match_post(
        case.get('text', ''),
        alt_text=case.get('alt_text', ''),
        langs=langs if isinstance(langs, list) else None,
        author_did=case.get('author_did'),
        author_handle=case.get('author_handle'),
        allowlist_dids=ALLOWLIST_DIDS,
        allowlist_handles=ALLOWLIST_HANDLES,
        soft_prior_dids=soft_prior_dids,
    )
    assert result.matched is bool(case['expected']), (
        f'{case["id"]}: expected={case["expected"]} got={result.matched} '
        f'reason={result.reason} note={case.get("note")}'
    )


def test_soft_prior_unlocks_bare_ambiguous_not_hard_negative() -> None:
    did = 'did:plc:softpriortest0000000000001'
    priors = {did}
    keep = match_post(
        'Direct action works when neighbors show up.',
        author_did=did,
        soft_prior_dids=priors,
    )
    assert keep.matched is True
    assert keep.reason == 'soft_prior_ambiguous:direct action'

    drop = match_post(
        'Direct action works when neighbors show up.',
        author_did=did,
        soft_prior_dids=set(),
    )
    assert drop.matched is False
    assert drop.reason == 'ambiguous_no_context:direct action'

    blocked = match_post(
        'Ancap tip: privatization fixes everything.',
        author_did=did,
        soft_prior_dids=priors,
    )
    assert blocked.matched is False
    assert blocked.reason in {'hard_negative', 'entity_other:anarcho_capitalism'}


def test_allowlist_did_matches_without_handle_or_keywords() -> None:
    assert ALLOWLIST_DIDS, 'allowlist_dids.txt must be populated for production recall'
    did = next(iter(sorted(ALLOWLIST_DIDS)))
    result = match_post(
        'Thanks for reading — more updates tomorrow.',
        author_did=did,
        allowlist_dids=ALLOWLIST_DIDS,
        allowlist_handles=ALLOWLIST_HANDLES,
    )
    assert result.matched is True
    assert result.reason == 'allowlist_did'


def test_event_local_venue_requires_cue_and_venue() -> None:
    keep = match_post('Free skol workshop this Saturday — doors at 6, bring a dish.')
    assert keep.matched is True
    assert keep.reason.startswith('event_local_venue:')

    no_cue = match_post('The free skol building needs a new roof.')
    assert no_cue.matched is False

    off_topic = match_post('Tickets on sale for Saturday comedy night at The Fillmore. Doors at 7.')
    assert off_topic.matched is False


def test_critique_of_ancap_still_keeps() -> None:
    result = match_post(
        'Anarchism is not anarcho-capitalism. Anarchists abolish bosses and landlords.'
    )
    assert result.matched is True
    assert result.reason in {'strong_positive_over_negative', 'strong_positive'}


def test_classifier_can_keep_ambiguous_co_op() -> None:
    fake = FakeClassifier(keep_substrings=('co-op',))
    result = match_post(
        'Our co-op shares tools citywide and refuses landlords.',
        classifier=fake,
    )
    assert result.matched is True
    assert result.reason.startswith('classifier:')


def test_extract_alt_text_clips_external_description() -> None:
    embed = {
        'external': {
            'title': 'Mutual aid zine',
            'description': 'x' * 500,
        }
    }
    alt = extract_alt_text(embed)
    assert 'Mutual aid zine' in alt
    assert len(alt) < 500
