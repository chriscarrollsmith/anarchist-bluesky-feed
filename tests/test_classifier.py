"""Unit tests for the DeepSeek quality-rubric classifier (no network)."""

from __future__ import annotations

from server.classifier import (
    ClassifierModel,
    DeepSeekClassifier,
    FakeClassifier,
    RubricThresholds,
    admit_grades,
    classify_candidate,
    composite_score,
    extract_features,
    grades_from_payload,
    load_model,
)
from server.matcher import looks_like_solicit, match_post


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
    assert decision.grades is not None
    assert decision.grades.solicit < 0.35


def test_deepseek_classifier_uses_injected_judge() -> None:
    clf = DeepSeekClassifier(
        api_key='test',
        thresholds=RubricThresholds(composite_min=0.7),
        _judge=lambda _text: {
            'keep': True,
            'thematic_fit': 0.91,
            'positive_valence': 0.88,
            'wow': 0.80,
            'solicit': 0.05,
            'rationale': 'aligned',
        },
    )
    decision = clf.classify(
        'Horizontal assemblies without bosses',
        term='autonomous',
        has_event_cue=False,
        has_local_venue=False,
    )
    assert decision is not None
    assert decision.matched is True
    assert decision.score == composite_score(0.91, 0.88, 0.80)
    assert decision.reason == 'classifier:ambiguous:autonomous'


def test_deepseek_classifier_accepts_legacy_score_payload() -> None:
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
    assert decision.matched is True
    assert decision.score == 0.91


def test_deepseek_classifier_respects_thematic_gate() -> None:
    clf = DeepSeekClassifier(
        api_key='test',
        thresholds=RubricThresholds(thematic_min=0.8, composite_min=0.5),
        _judge=lambda _text: {
            'keep': True,
            'thematic_fit': 0.5,
            'positive_valence': 0.9,
            'wow': 0.9,
            'solicit': 0.0,
            'rationale': 'weak theme',
        },
    )
    decision = clf.classify(
        'maybe related',
        term='punk',
        has_event_cue=False,
        has_local_venue=False,
    )
    assert decision is not None
    assert decision.matched is False
    assert decision.reason == 'quality_reject:thematic_fit'


def test_deepseek_classifier_rejects_high_solicit() -> None:
    clf = DeepSeekClassifier(
        api_key='test',
        _judge=lambda _text: {
            'keep': True,
            'thematic_fit': 0.95,
            'positive_valence': 0.7,
            'wow': 0.6,
            'solicit': 0.9,
            'rationale': 'venmo ask',
        },
    )
    decision = clf.classify(
        'Mutual aid please Venmo me for rent',
        term=None,
        has_event_cue=False,
        has_local_venue=False,
    )
    assert decision is not None
    assert decision.matched is False
    assert decision.reason == 'quality_reject:solicit'


def test_admit_grades_composite_floor() -> None:
    grades = grades_from_payload(
        {
            'thematic_fit': 0.72,
            'positive_valence': 0.56,
            'wow': 0.46,
            'solicit': 0.1,
        }
    )
    # 0.45*0.72 + 0.25*0.56 + 0.30*0.46 = 0.324 + 0.14 + 0.138 = 0.602
    assert admit_grades(grades, RubricThresholds(composite_min=0.68)) == 'quality_reject:composite'
    assert admit_grades(grades, RubricThresholds(composite_min=0.60)) is None


def test_match_post_uses_classifier_for_ambiguous() -> None:
    fake = FakeClassifier(keep_terms=frozenset({'punk'}))
    strong = match_post('Anarchists without bosses build mutual aid networks.')
    assert strong.matched is True
    assert strong.reason == 'strong_positive'

    keep_ai = match_post('Local punk show was chaotic fun.', classifier=fake)
    assert keep_ai.matched is True
    assert keep_ai.reason == 'classifier:ambiguous:punk'


def test_solicit_cue_vetoes_strong_positive_without_classifier() -> None:
    assert looks_like_solicit('Mutual aid request — please Venmo @me for rent')
    result = match_post('Mutual aid request — please Venmo @me for rent')
    assert result.matched is False
    assert result.reason.startswith('solicit_cue_unscored:')


def test_solicit_cue_passes_when_classifier_clears() -> None:
    fake = FakeClassifier(keep_substrings=('Food Not Bombs',), solicit=0.1)
    result = match_post(
        'Food Not Bombs kitchen goal: donate via our collective PayPal.',
        classifier=fake,
    )
    assert result.matched is True
    assert result.reason == 'strong_positive'


def test_solicit_cue_drops_when_classifier_flags_solicit() -> None:
    fake = FakeClassifier(reject_substrings=('Venmo me',))
    result = match_post(
        'Anarchist mutual aid — Venmo me if you can spare anything for rent.',
        classifier=fake,
    )
    assert result.matched is False
    assert result.reason == 'quality_reject:solicit'


def test_allowlist_solicit_cue_still_gated() -> None:
    fake = FakeClassifier(reject_substrings=('CashApp',))
    result = match_post(
        'CashApp me for mutual aid please',
        author_did='did:plc:allowlisted000000000000001',
        allowlist_dids={'did:plc:allowlisted000000000000001'},
        classifier=fake,
    )
    assert result.matched is False
    assert result.reason == 'quality_reject:solicit'


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
