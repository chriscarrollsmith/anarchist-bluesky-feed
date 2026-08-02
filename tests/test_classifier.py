"""Unit tests for the DeepSeek values-alignment classifier (no network)."""

from __future__ import annotations

from server.classifier import (
    ClassifierModel,
    DeepSeekClassifier,
    FakeClassifier,
    classify_candidate,
    extract_features,
    load_model,
)
from server.matcher import match_post


def test_load_default_model_stub() -> None:
    model = load_model()
    assert model.version == 'deepseek_v4_flash'
    assert model.threshold > 0


def test_extract_features_ambiguous_term() -> None:
    feats = extract_features(
        'Our co-op refuses landlords',
        term='co-op',
        has_event_cue=False,
        has_local_venue=False,
    )
    assert feats['has_ambiguous'] == 1.0
    assert feats['has_event_cue'] == 0.0


def test_fake_classifier_keeps_substring() -> None:
    fake = FakeClassifier(keep_substrings=('refuses landlords',))
    decision = classify_candidate(
        'Our co-op shares tools and refuses landlords.',
        term='co-op',
        has_event_cue=False,
        has_local_venue=False,
        classifier=fake,
    )
    assert decision is not None
    assert decision.matched is True
    assert decision.reason.startswith('classifier:')


def test_deepseek_classifier_uses_injected_judge() -> None:
    clf = DeepSeekClassifier(
        api_key='test',
        threshold=0.7,
        _judge=lambda _text: {'keep': True, 'score': 0.91, 'rationale': 'aligned'},
    )
    decision = clf.classify(
        'Horizontal assemblies without bosses',
        term='autonomous',
        has_event_cue=False,
        has_local_venue=False,
    )
    assert decision is not None
    assert decision.score == 0.91
    assert decision.reason == 'classifier:ambiguous:autonomous'


def test_deepseek_classifier_respects_threshold() -> None:
    clf = DeepSeekClassifier(
        api_key='test',
        threshold=0.8,
        _judge=lambda _text: {'keep': True, 'score': 0.5, 'rationale': 'weak'},
    )
    assert (
        clf.classify(
            'maybe related',
            term='punk',
            has_event_cue=False,
            has_local_venue=False,
        )
        is None
    )


def test_match_post_uses_classifier_for_ambiguous() -> None:
    fake = FakeClassifier(keep_terms=frozenset({'punk'}))
    strong = match_post('Anarchists without bosses build mutual aid networks.')
    assert strong.matched is True
    assert strong.reason == 'strong_positive'

    keep_ai = match_post('Local punk show was chaotic fun.', classifier=fake)
    assert keep_ai.matched is True
    assert keep_ai.reason == 'classifier:ambiguous:punk'


def test_classifier_model_stub_never_keeps() -> None:
    stub = ClassifierModel(version='x', threshold=0.5, weights={'bias': 10.0})
    assert (
        stub.classify(
            'anything',
            term='anarchy',
            has_event_cue=False,
            has_local_venue=False,
        )
        is None
    )
