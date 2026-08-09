"""ONE output-size dial for BOTH local variation engines.

Klein and Krea framed their shots by two unrelated rules: Klein rescaled the
SOURCE to a hardcoded 2 MP and kept the reference's shape, Krea asked for the
card's shape but capped the budget at the reference's own pixel count — so a
1024x832 reference produced 0.84 MP Krea tiles next to 2 MP Klein ones, in
different shapes, in the same dataset. This pins the replacement:

  * one shared calculation (services/output_geometry.fit_output_size),
  * the CARD's ratio on both engines,
  * `variations.output_megapixels` decides the budget — upscale included,
  * the free reference edit (no card ratio) keeps its no-upscale rule.

The Klein assertions read the workflow that would be submitted, on the nodes
that actually decide the canvas: 91 EmptyFlux2LatentImage takes its width and
height from the PrimitiveInt nodes 119/120, which used to be wired to the
GetImageSize of the rescaled source.
"""
import pytest
from PIL import Image
from unittest.mock import patch


CARD_RATIOS = ['1:1', '3:4', '16:9', '9:16']


# --- the shared calculation --------------------------------------------------

def test_both_engines_import_the_same_sizing_function():
    """"Same size" has to be structural. Two engines computing the same answer
    from two copies is a coincidence that lasts until the next edit."""
    from app.services import klein_edit_helper as kleh
    from app.services import krea_edit_helper as keh
    from app.services import output_geometry

    assert keh.fit_output_size is output_geometry.fit_output_size
    assert kleh.fit_output_size is output_geometry.fit_output_size


def test_the_dial_may_ask_for_more_pixels_than_the_reference_holds():
    """DECIDED: the setting wins, upscale included.

    This REPLACES the previous no-upscale rule of the card path, which is what
    produced 0.84 MP variations from a 1024x832 reference while the dial said 2.
    """
    from app.services.output_geometry import fit_output_size

    ow, oh = fit_output_size(1024, 832, max_mp=2.0, requested_aspect='1:1')
    assert ow * oh > 1024 * 832, 'the card budget must not be capped by the source'
    assert 1_900_000 <= ow * oh <= 2_000_000
    assert ow == oh


def test_a_free_reference_edit_still_refuses_to_invent_detail():
    """Only the CARD path changed. A free edit (no requested ratio) keeps the
    source frame and the historical no-upscale rule."""
    from app.services.output_geometry import fit_output_size

    assert fit_output_size(512, 512) == (512, 512)
    assert fit_output_size(512, 512, max_mp=2.0) == (512, 512)


@pytest.mark.parametrize('ratio', CARD_RATIOS)
@pytest.mark.parametrize('budget', [0.5, 1.0, 2.0])
def test_the_card_canvas_honours_the_budget_at_the_card_ratio(ratio, budget):
    from app.services.output_geometry import fit_output_size

    aw, ah = (float(x) for x in ratio.split(':'))
    ow, oh = fit_output_size(1024, 832, max_mp=budget, requested_aspect=ratio)
    assert ow % 16 == 0 and oh % 16 == 0
    assert ow * oh <= budget * 1_000_000
    assert ow * oh >= budget * 900_000, 'the budget must be nearly spent, not approached'
    assert abs((ow / oh) - (aw / ah)) / (aw / ah) < 0.02


@pytest.mark.parametrize(('budget', 'ratio', 'canvas'), [
    (2.0, '3:4', (1216, 1632)),
    (2.0, '1:1', (1408, 1408)),
    (1.0, '3:4', (864, 1152)),
    (0.5, '16:9', (944, 528)),
])
def test_the_canvas_the_panel_announces_is_the_canvas_we_render(budget, ratio, canvas):
    """The dial's caption states a pixel size. frontend/tests/
    variation-output-size-contract.test.mjs pins the SAME pairs on the JS twin of
    this calculation, so a drift on either side turns one of the two red instead
    of quietly making the panel lie."""
    from app.services.output_geometry import fit_output_size
    assert fit_output_size(1024, 832, max_mp=budget, requested_aspect=ratio) == canvas


# --- the setting -------------------------------------------------------------

def test_the_setting_ships_at_two_megapixels(app):
    """Klein's historical value: an untouched install must frame exactly as
    before, so nobody's first run after the update looks different."""
    from app import config as cfg
    with app.app_context():
        assert cfg.defaults()['variations']['output_megapixels'] == 2.0


@pytest.mark.parametrize(('stored', 'expected'), [
    (0.5, 0.5), (1.25, 1.25), (2.0, 2.0),
    (9.0, 2.0),          # above the edit model's drift threshold
    (0.05, 0.5),         # below anything usable
    ('nonsense', 2.0), (None, 2.0), ([], 2.0),
])
def test_a_hand_edited_config_still_yields_a_usable_budget(app, stored, expected):
    from app import config as cfg
    from app.services.output_geometry import variation_output_megapixels
    with app.app_context():
        cfg.save_config({'variations': {'output_megapixels': stored}})
        assert variation_output_megapixels() == expected


# --- Klein: the card ratio reaches the graph ---------------------------------

@pytest.fixture()
def klein_workflow(app, tmp_path):
    """Enqueue a Klein edit and hand back the workflow ComfyUI would receive."""
    def run(source_size=(1024, 832), **kwargs):
        from app import config as cfg
        from app.services import klein_edit_helper as kleh
        seen = {}
        src = tmp_path / 'src.png'
        Image.new('RGB', source_size, (10, 20, 30)).save(src, format='PNG')
        comfy_in = tmp_path / 'comfy_input'
        comfy_in.mkdir(exist_ok=True)
        comfy = tmp_path / 'comfy'
        (comfy / 'models' / 'loras' / 'klein').mkdir(parents=True, exist_ok=True)
        cfg.save_config({'comfyui': {'base_dir': str(comfy)}})
        with patch.object(kleh.queue_manager, 'add_job',
                          side_effect=lambda **kw: seen.update(kw)), \
             patch.object(kleh, '_comfy_input_dir', return_value=str(comfy_in)), \
             patch.object(kleh, 'resolve_klein_unet', return_value='unet.safetensors'), \
             patch.object(kleh, 'resolve_klein_vae', return_value='vae.safetensors'), \
             patch.object(kleh, 'resolve_klein_text_encoder', return_value='te.safetensors'), \
             patch.object(kleh, 'klein_missing_assets', return_value=[]):
            kleh.enqueue_klein_edit(user_id='local', source_filename='src.png',
                                    source_path=str(src), edit_prompt='a shot',
                                    **kwargs)
        return seen['workflow_data']
    with app.app_context():
        yield run


@pytest.mark.parametrize('ratio', CARD_RATIOS)
def test_klein_frames_the_card_and_not_the_reference(klein_workflow, ratio):
    """Klein used to follow the REFERENCE's shape whatever the card asked for."""
    from app.services.output_geometry import fit_output_size

    w = klein_workflow(aspect_ratio=ratio)
    expected = fit_output_size(1024, 832, max_mp=2.0, requested_aspect=ratio)
    assert (w['119']['inputs']['value'], w['120']['inputs']['value']) == expected
    # The latent the sampler fills IS the result: the widths must reach it, not
    # sit in an unread node.
    assert w['91']['inputs']['width'] == ['119', 0]
    assert w['91']['inputs']['height'] == ['120', 0]


def test_klein_and_krea_frame_the_same_card_identically(klein_workflow):
    """The point of the whole change: two engines, one geometry."""
    from app.services.output_geometry import fit_output_size

    for ratio in CARD_RATIOS:
        w = klein_workflow(aspect_ratio=ratio)
        krea = fit_output_size(1024, 832, max_mp=2.0, requested_aspect=ratio)
        assert (w['119']['inputs']['value'], w['120']['inputs']['value']) == krea, ratio


def test_the_klein_reference_is_encoded_at_the_chosen_budget(klein_workflow):
    """Node 174 rescales the source before the VAE encode. Leaving it at a fixed
    2 MP while the canvas drops to 0.5 would burn the time the dial exists to
    save."""
    w = klein_workflow(aspect_ratio='3:4', output_megapixels=0.5)
    assert w['174']['inputs']['megapixels'] == 0.5


def test_the_klein_setting_applies_without_the_caller_repeating_it(app, klein_workflow):
    from app import config as cfg
    from app.services.output_geometry import fit_output_size
    with app.app_context():
        cfg.save_config({'variations': {'output_megapixels': 1.0}})
        w = klein_workflow(aspect_ratio='3:4')
    assert (w['119']['inputs']['value'], w['120']['inputs']['value']) == \
        fit_output_size(1024, 832, max_mp=1.0, requested_aspect='3:4')


def test_the_upscale_and_improve_lane_is_untouched(klein_workflow):
    """It asks for a pixel budget and NO card ratio — 2 to 8 MP on the source's
    own shape. Its canvas must keep coming from the rescaled source."""
    w = klein_workflow(output_megapixels=6.0)
    assert w['174']['inputs']['megapixels'] == 6.0
    assert w['119']['inputs']['value'] == ['175', 0]
    assert w['120']['inputs']['value'] == ['175', 1]


# --- both lanes of both engines pass the card --------------------------------

def test_klein_batch_and_regenerate_forward_the_catalog_card_aspect(app, monkeypatch):
    """The twin of the Krea proof in test_krea_edit.py. ``Body, wide urban shot``
    overrides the body's usual 3:4 with 16:9, so a missing lookup and a silent
    fallback to the source geometry both fail here."""
    from app.extensions import db
    from app.models import FaceDatasetImage
    from app.services import face_dataset_service as svc
    from app.services import klein_edit_helper as kleh

    calls = []
    monkeypatch.setattr(kleh, 'klein_missing_assets', lambda: [])
    monkeypatch.setattr(kleh, 'klein_missing_nodes', lambda: [])

    def enqueue(**kwargs):
        calls.append(kwargs)
        return f'klein-aspect-{len(calls)}'

    monkeypatch.setattr(kleh, 'enqueue_klein_edit', enqueue)
    shot = {'label': 'Body, wide urban shot', 'framing': 'body',
            'prompt': 'full body shot, wide environmental framing'}
    with app.app_context():
        ds = svc.create_dataset('local', 'Klein aspect', 'klein_aspect')
        ds.ref_filename = 'ref.png'
        db.session.commit()
        assert svc.generate_variations('local', ds.id, [shot], 1)
        row = FaceDatasetImage(dataset_id=ds.id, source='generated', status='failed',
                               variation_label=shot['label'], framing=shot['framing'],
                               variation_prompt=shot['prompt'], klein_model=None)
        db.session.add(row)
        db.session.commit()
        assert svc.regenerate_image('local', row.id) == 'klein-aspect-2'

    assert [c.get('aspect_ratio') for c in calls] == ['16:9', '16:9']
