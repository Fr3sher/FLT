"""Dependency consent resolves real manifest constraints before changing files."""
from pathlib import Path

import pytest

from app.plugins.manifest import parse_manifest
from app.plugins.store.catalog import Release, plan_digest, resolve
from app.plugins.store.client import StoreError
from public_store_fixtures import contract


def release(pid, version='1.0.0', dependencies=None, **over):
    deps = dependencies or {}
    manifest = parse_manifest(contract(id=pid, version=version, requires=list(deps),
                              dependency_versions=deps, **over), Path('.'), official=True)
    return Release(manifest, f'{pid}/{version}.ldsplugin', '0' * 64, (), {'kind': 'free'})


def versions(plan):
    return [(r.manifest.id, r.manifest.version) for r in plan]


def test_latest_compatible_release_and_dependencies_in_install_order():
    a = release('camera_angles', dependencies={'video': '>=1,<2'})
    video = [release('video', '2.0.0'), release('video', '1.2.0')]
    assert versions(resolve({'camera_angles': [a], 'video': video}, 'camera_angles', {})) == [
        ('video', '1.2.0'), ('camera_angles', '1.0.0')]


def test_reverse_dependency_constrains_requested_update_and_conflict_is_explicit():
    cloud = release('cloud_training', dependencies={'video': '<2'})
    video = [release('video', '2.0.0'), release('video', '1.0.0')]
    catalog = {'cloud_training': [cloud], 'video': video}
    installed = {'cloud_training': cloud.manifest, 'video': video[1].manifest}
    assert dict(versions(resolve(catalog, 'video', installed)))['video'] == '1.0.0'
    with pytest.raises(StoreError, match='No compatible set'):
        resolve(catalog, 'video', installed, version='2.0.0')
    assert versions(resolve(catalog, 'video', installed, version='2.0.0', active=set())) == [('video', '2.0.0')]


def test_installed_dependency_can_be_retained_after_withdrawal_from_catalog():
    camera = release('camera_angles', dependencies={'video': '>=1,<2'})
    old = release('video', '1.4.0')
    plan = resolve({'camera_angles': [camera]}, 'camera_angles', {'video': old.manifest}, active=set())
    assert plan[0].manifest is old.manifest and plan[0].target == ''


def test_prereleases_require_explicit_selection_or_dependency_range():
    prerelease, stable = release('video', '2.0.0rc1'), release('video')
    catalog = {'video': [prerelease, stable]}
    assert versions(resolve(catalog, 'video', {})) == [('video', '1.0.0')]
    assert versions(resolve(catalog, 'video', {}, version='2.0.0rc1')) == [('video', '2.0.0rc1')]
    camera = release('camera_angles', dependencies={'video': '>=2.0.0rc1,<3'})
    assert dict(versions(resolve({**catalog, 'camera_angles': [camera]}, 'camera_angles', {})))['video'] == '2.0.0rc1'


def test_search_backtracks_past_a_cyclic_release():
    camera = release('camera_angles', dependencies={'video': '>=1'})
    cyclic = release('video', '2.0.0', dependencies={'camera_angles': '>=1'})
    stable = release('video')
    assert versions(resolve({'camera_angles': [camera], 'video': [cyclic, stable]}, 'camera_angles', {})) == [
        ('video', '1.0.0'), ('camera_angles', '1.0.0')]
    with pytest.raises(StoreError, match='No compatible set'):
        resolve({'camera_angles': [camera], 'video': [cyclic]}, 'camera_angles', {})


def test_consent_digest_binds_permissions_versions_receipts_and_store():
    a, b = release('camera_angles'), release('camera_angles', '2.0.0')
    base = plan_digest([a], {}, 'trusted-store')
    assert base != plan_digest([b], {}, 'trusted-store')
    assert base != plan_digest([a], {}, 'other-store')
    assert base != plan_digest([a], {'video': release('video').manifest}, 'trusted-store')


@pytest.mark.parametrize('pid', [None, [], {}, 42, 'missing'])
def test_invalid_requested_identity_is_a_public_error(pid):
    with pytest.raises(StoreError):
        resolve({}, pid, {})


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.parametrize('owns', [
    {'engines': ['seedvr2']}, {'install_actions': ['seedvr2_model']},
    {'config_keys_in_shared_sections': {'seedvr2': ['tiling']}},
])
def test_product_split_updates_the_previous_owner_even_when_disabled(enabled, owns):
    old = release('image_upscale', owns=owns)
    split = release('image_upscale', '1.1.0')
    new = release('model_tools', owns=owns)
    plan = resolve({'image_upscale': [split, old], 'model_tools': [new]}, 'model_tools',
                   {'image_upscale': old.manifest}, active={'image_upscale'} if enabled else set())
    assert dict(versions(plan)) == {'image_upscale': '1.1.0', 'model_tools': '1.0.0'}
    assert all(not item.manifest.requires for item in plan), 'ownership transfer is not a product dependency'
    assert len(plan) == 2, 'both archives belong to one consented plan'


def test_split_can_install_alone_without_acquiring_the_old_owner():
    new = release('model_tools', owns={'engines': ['seedvr2']})
    assert versions(resolve({'model_tools': [new]}, 'model_tools', {})) == [('model_tools', '1.0.0')]


def test_split_refuses_an_unresolvable_disabled_owner_without_silently_removing_it():
    old = release('image_upscale', owns={'engines': ['seedvr2']})
    new = release('model_tools', owns={'engines': ['seedvr2']})
    with pytest.raises(StoreError, match='ownership'):
        resolve({'model_tools': [new]}, 'model_tools', {'image_upscale': old.manifest}, active=set())


def test_disabled_unrelated_products_keep_missing_dependencies_and_remain_untouched():
    old = release('image_upscale', dependencies={'video': '>=1'})
    new = release('model_tools')
    assert versions(resolve({'model_tools': [new]}, 'model_tools', {'image_upscale': old.manifest}, active=set())) == [
        ('model_tools', '1.0.0')]


def test_split_cannot_break_an_active_reverse_dependency_to_update_ownership():
    old = release('image_upscale', owns={'engines': ['seedvr2']})
    split = release('image_upscale', '1.1.0')
    new = release('model_tools', owns={'engines': ['seedvr2']})
    dependent = release('video', dependencies={'image_upscale': '<1.1'})
    with pytest.raises(StoreError, match='No compatible set'):
        resolve({'image_upscale': [split, old], 'model_tools': [new]}, 'model_tools',
                {'image_upscale': old.manifest, 'video': dependent.manifest})
