"""Rank fusion is the only place two search engines meet.

They cannot meet in vector space: embeddings from different CLIP
configurations are not comparable, and their cosines are not on a shared
scale. So the engines hand up ORDER, and these tests pin what happens to it.
"""
from app.services import bank_search_fusion


def test_a_single_ranked_list_comes_back_in_the_same_order():
    """The load-bearing property. Most installs will only ever have one index,
    and they must get exactly today's results through this new code path —
    which holds because 1/(k + rank) is strictly decreasing in rank."""
    items = [f'img{i:03d}.png' for i in range(50)]
    fused = bank_search_fusion.rrf({'siglip2': items})
    assert [row[0] for row in fused] == items


def test_no_engine_at_all_returns_nothing():
    assert bank_search_fusion.rrf({}) == []
    assert bank_search_fusion.rrf({'siglip2': []}) == []


def test_an_item_both_engines_rank_well_beats_items_only_one_engine_knows():
    fused = bank_search_fusion.rrf({
        'siglip2': ['both', 'solo_a', 'tail_a'],
        'laion': ['both', 'solo_b', 'tail_b'],
    })
    assert fused[0][0] == 'both'


def test_an_item_only_one_engine_knows_still_surfaces():
    """This is the entire point of fusing. SigLIP 2 was trained on
    porn-filtered WebLI and cannot retrieve explicit concepts at all, so an
    image LAION ranks first and SigLIP 2 never ranks must still outrank an
    image SigLIP 2 ranks poorly."""
    fused = bank_search_fusion.rrf({
        'siglip2': ['a', 'b', 'siglip_tail'],
        'laion': ['explicit', 'a', 'b'],
    })
    names = [row[0] for row in fused]
    assert 'explicit' in names
    assert names.index('explicit') < names.index('siglip_tail')


def test_ties_are_broken_deterministically():
    """Two items each ranked 1st by one engine and 2nd by the other score
    identically. The order must not depend on dict iteration or float noise."""
    lists = {'siglip2': ['b', 'a'], 'laion': ['a', 'b']}
    first = bank_search_fusion.rrf(lists)
    assert first == bank_search_fusion.rrf(lists)
    assert [row[0] for row in first] == ['a', 'b']


def test_each_row_reports_which_engines_ranked_it():
    """The UI has to be able to say an engine answered — a result set that
    hides which engine produced it cannot report one engine failing."""
    fused = bank_search_fusion.rrf({'siglip2': ['a'], 'laion': ['a', 'b']})
    engines = {row[0]: row[2] for row in fused}
    assert engines['a'] == ('laion', 'siglip2')
    assert engines['b'] == ('laion',)


def test_a_repeated_item_within_one_list_is_counted_once_at_its_best_rank():
    """A malformed engine result must not let an item buy extra score by
    appearing twice."""
    honest = bank_search_fusion.rrf({'siglip2': ['a', 'b']})
    repeated = bank_search_fusion.rrf({'siglip2': ['a', 'b', 'a']})
    assert repeated == honest


def test_limit_truncates_the_fused_list():
    fused = bank_search_fusion.rrf({'siglip2': ['a', 'b', 'c']}, limit=2)
    assert [row[0] for row in fused] == ['a', 'b']


def test_a_non_positive_k_is_refused():
    """k <= 0 divides by zero at rank k, or flips the ranking sign. Neither
    should be discoverable in production."""
    import pytest
    with pytest.raises(ValueError):
        bank_search_fusion.rrf({'siglip2': ['a']}, k=0)
