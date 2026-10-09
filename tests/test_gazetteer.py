"""Gazetteer entity disambiguation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from server.gazetteer import default_gazetteer, load_gazetteer
from server.matcher import match_post


def test_default_gazetteer_other_beats_local_substring() -> None:
    gaz = default_gazetteer()
    hit = gaz.lookup('Rewatching Sons of Anarchy season 3 tonight.')
    assert hit is not None
    assert hit.region == 'other'
    assert hit.entity_id == 'sons_of_anarchy'


def test_match_post_entity_other_and_local() -> None:
    other = match_post('Who still plays Anarchy Online in 2026?')
    assert other.matched is False
    assert other.reason in {'entity_other:anarchy_online', 'hard_negative'}

    sibling = match_post('Black Rose Anarchist Federation published a new primer.')
    assert sibling.matched is False
    assert sibling.reason == 'entity_other:black_rose_anarchist_federation'

    local = match_post('New C4SS essay on left-wing market anarchism.')
    assert local.matched is True
    assert local.reason in {'entity_local:c4ss', 'strong_positive'}


def test_load_gazetteer_rejects_unknown_region(tmp_path: Path) -> None:
    path = tmp_path / 'bad.json'
    path.write_text(
        '{"entities":[{"id":"x","region":"mars","surfaces":["x"]}]}',
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='unknown region'):
        load_gazetteer(path)
