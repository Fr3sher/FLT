"""Installed packages and historical host mappings share one public database."""
import pytest


def test_installed_video_fields_exist_on_a_fresh_public_host(app):
    from sqlalchemy import inspect
    from app.extensions import db
    from app.models import VideoTestClip
    from lds_sdk.database import for_plugin
    with app.app_context():
        table = for_plugin('video', tables=['video_test_clip']).table('video_test_clip')
        assert table is VideoTestClip.__table__
        columns = {item['name'] for item in inspect(db.engine).get_columns('video_test_clip')}
        assert {'references_json', 'end_image', 'generation_settings', 'user_id'} <= columns
        assert inspect(db.engine).has_table('video_checkpoint_preview')
        assert inspect(db.engine).has_table('video_civitai_link')
        # Older public packages keep their mapped fields and existing defaults.
        clip = VideoTestClip(prompt='fixture')
        db.session.add(clip)
        db.session.commit()
        assert db.session.get(VideoTestClip, clip.id).status == 'pending'


def test_new_persistent_fields_do_not_grant_other_plugins_table_ownership():
    from lds_sdk.database import for_plugin
    with pytest.raises(ValueError, match='does not belong'):
        for_plugin('example.other', tables=['video_checkpoint_preview'])


def test_original_public_sdk_names_remain_available():
    from app.routes import _common
    from lds_sdk.video_host import http
    from lds_sdk import h3_render
    assert http._map_error is _common._map_error
    assert callable(http.map_error)
    assert callable(h3_render.build_workflow)
    assert callable(h3_render.graft_reference_accel)


def test_reference_guides_keep_both_frame_positions_and_conditioning_chain():
    from lds_sdk import h3_render as h3, h3_reference_graph as refs
    workflow = h3.load_base_workflow()
    refs.graft(workflow, references=[{'kind': 'image', 'name': 'identity.png'}],
               image='first.png', end_image='last.png')
    assert workflow[h3.N_COND]['class_type'] == 'MiniMaxH3ReferenceToVideo'
    assert workflow['951']['inputs']['frame_idx'] == 0
    assert workflow['953']['inputs']['frame_idx'] == -1
    assert workflow['953']['inputs']['positive'] == ['951', 0]
    assert workflow[h3.N_GUIDER]['inputs']['conditioning'] == ['953', 0]
