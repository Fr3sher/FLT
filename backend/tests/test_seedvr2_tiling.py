"""SeedVR2 high-resolution lane — tiling, and the ceiling that warns first.

WHY THIS EXISTS. SurpassHR (GitHub #32) hit a real CUDA OOM upscaling full-frame
on an 11.6 GB card and shipped a tiled workflow on his fork that reaches >4K on
the same machine. Two things came out of that report, and both are tested here:
the tiled lane itself, and the fact that a user must be TOLD where the limit is
before a run dies rather than discovering it in a PyTorch traceback.

WHAT WAS DELIBERATELY NOT PORTED. His graph chains three node packs; two of them
only do arithmetic (normalise a pixel count, divide by 1024 to count tiles), and
one of those two is GPL-3.0 while this repo is MIT and has refused a dependency
over its licence before. The arithmetic lives in `tile_plan` instead, so the
lane needs TTP alone — MIT, two classes. These tests pin that reduction: if
someone re-adds a pack, `test_the_tiled_graph_needs_only_the_two_TTP_nodes`
fails.
"""
import pytest


def _plan(**over):
    from app.services import seedvr2_helper as svr
    base = dict(width=2000, height=3000, short_edge=2160)
    base.update(over)
    return svr.tile_plan(base['width'], base['height'], base['short_edge'])


# --- The geometry his graph computed with two extra node packs --------------

def test_a_single_tile_target_yields_no_grid():
    """A frame that fits inside one tile has no grid to describe. Whether a
    2-tile grid is WORTH cutting is a different question, and it belongs to
    choose_lane, which knows the card — see the 'does not tile what needs no
    tiling' test below."""
    from app.services import seedvr2_helper as svr
    assert svr.tile_plan(1024, 1024, 1024) is None
    assert svr.tile_plan(512, 512, 800) is None
    # ...and just past one tile, the geometry is honest about needing two.
    assert svr.tile_plan(512, 768, 720)['tiles'] == 2


def test_a_big_target_is_cut_into_overlapping_tiles():
    plan = _plan()
    # 2000x3000 asked for a 2160 short edge -> 2160x3240 out.
    assert (plan['output_width'], plan['output_height']) == (2160, 3240)
    assert plan['tile_width'] == plan['tile_height'] == 1024
    # Overlap is SHARED between neighbours, so columns count on the step
    # (1024 * 0.9 = 922), not on the full tile side.
    assert plan['columns'] == 3 and plan['rows'] == 4
    assert plan['tiles'] == 12


def test_more_overlap_means_more_tiles_never_fewer():
    from app.services import seedvr2_helper as svr
    lean = svr.tile_plan(2000, 3000, 2160, overlap_rate=0.0)
    fat = svr.tile_plan(2000, 3000, 2160, overlap_rate=0.4)
    assert fat['tiles'] > lean['tiles']


def test_absurd_overlap_cannot_explode_the_tile_count():
    """A config value of 0.99 would make the step 10 px and the grid enormous —
    a clamp, because a bad setting must degrade the pass, never hang the GPU."""
    from app.services import seedvr2_helper as svr
    plan = svr.tile_plan(2000, 3000, 2160, overlap_rate=0.99)
    assert plan['tiles'] <= svr.tile_plan(2000, 3000, 2160, overlap_rate=0.45)['tiles']


def test_junk_geometry_returns_no_plan_rather_than_raising():
    from app.services import seedvr2_helper as svr
    for args in [(0, 100, 1024), (100, 0, 1024), (100, 100, 0),
                 (None, None, None), ('a', 'b', 'c')]:
        assert svr.tile_plan(*args) is None


# --- The ceiling that speaks before the GPU dies ---------------------------

def test_the_ceiling_scales_with_the_card_and_stays_quiet_when_unknown():
    from app.services import seedvr2_helper as svr
    assert svr.full_frame_ceiling_mp(24) > svr.full_frame_ceiling_mp(12)
    # An unseen card gets NO number: inventing one is the false promise this
    # replaces.
    for unknown in (None, 0, -1, 'nope'):
        assert svr.full_frame_ceiling_mp(unknown) is None


def test_the_reported_case_lands_on_the_right_side_of_the_ceiling():
    """The report that opened this: full-frame OOM at roughly 4K on 11.6 GB."""
    from app.services import seedvr2_helper as svr
    ceiling = svr.full_frame_ceiling_mp(11.6)
    four_k_mp = svr.output_megapixels(2000, 3000, 2160)   # ~7.0 MP
    assert four_k_mp > ceiling, (
        'the ceiling must classify the reported OOM as over budget, or it warns '
        'about nothing')


def test_a_modest_upscale_on_the_same_card_is_NOT_flagged():
    """A ceiling that cried wolf on every run would be turned off on day one."""
    from app.services import seedvr2_helper as svr
    lane = svr.choose_lane(1024, 1024, short_edge=1080, tiling_ok=False,
                           ceiling_mp=svr.full_frame_ceiling_mp(11.6))
    assert lane['capped'] is False and lane['notice'] is None


# --- Which lane runs -------------------------------------------------------

def test_without_the_pack_the_run_still_happens_and_says_what_would_help():
    """The ceiling is guidance, not a gate: real headroom moves with the build
    and block swapping, so refusing would refuse runs that would have worked."""
    from app.services import seedvr2_helper as svr
    lane = svr.choose_lane(2000, 3000, short_edge=2160, tiling_ok=False,
                           ceiling_mp=svr.full_frame_ceiling_mp(11.6))
    assert lane['lane'] == 'full'
    assert lane['capped'] is True
    assert 'Comfyui_TTP_Toolset' in lane['notice']
    assert 'run out of memory' in lane['notice']


def test_with_the_pack_the_same_request_is_tiled_instead():
    from app.services import seedvr2_helper as svr
    lane = svr.choose_lane(2000, 3000, short_edge=2160, tiling_ok=True,
                           ceiling_mp=svr.full_frame_ceiling_mp(11.6))
    assert lane['lane'] == 'tiled'
    assert lane['capped'] is False
    assert lane['plan']['tiles'] == 12
    assert 'tiles' in lane['notice']


def test_the_pack_being_present_does_not_tile_what_needs_no_tiling():
    from app.services import seedvr2_helper as svr
    lane = svr.choose_lane(768, 1024, short_edge=1080, tiling_ok=True,
                           ceiling_mp=svr.full_frame_ceiling_mp(24))
    assert lane['lane'] == 'full' and lane['plan'] is None


# --- The graph itself ------------------------------------------------------

def test_the_tiled_graph_needs_only_the_two_TTP_nodes():
    """The reduction that dropped a GPL-3.0 dependency. If a third pack creeps
    back in, this is where it is caught."""
    from app.services import seedvr2_helper as svr
    g = svr.build_tiled_workflow('src.png', dit='d.safetensors', vae='v.safetensors',
                                 seed=42, plan=_plan(), filename_prefix='pfx')
    classes = {n['class_type'] for n in g.values()}
    foreign = {c for c in classes
               if c.startswith('TTP_') or '+' in c or c.startswith('easy ')}
    assert foreign == {'TTP_Image_Tile_Batch', 'TTP_Image_Assy'}, (
        f'the tiled lane must depend on TTP alone; found {sorted(foreign)}')
    assert classes == {'SeedVR2LoadDiTModel', 'SeedVR2LoadVAEModel', 'LoadImage',
                       'ImageScale', 'TTP_Image_Tile_Batch',
                       'SeedVR2VideoUpscaler', 'TTP_Image_Assy', 'SaveImage'}


def test_the_tiled_graph_is_wired_tiles_in_tiles_out():
    from app.services import seedvr2_helper as svr
    g = svr.build_tiled_workflow('src.png', dit='d', vae='v', seed=42, plan=_plan())
    tiler = next(k for k, n in g.items() if n['class_type'] == 'TTP_Image_Tile_Batch')
    up = next(k for k, n in g.items() if n['class_type'] == 'SeedVR2VideoUpscaler')
    assy = next(k for k, n in g.items() if n['class_type'] == 'TTP_Image_Assy')
    # The upscaler eats the tile BATCH...
    assert g[up]['inputs']['image'] == [tiler, 0]
    # ...and the assembler takes the upscaled tiles plus the tiler's own
    # positions / original size / grid, which is what puts them back in place.
    assert g[assy]['inputs']['tiles'] == [up, 0]
    assert g[assy]['inputs']['positions'] == [tiler, 1]
    assert g[assy]['inputs']['original_size'] == [tiler, 2]
    assert g[assy]['inputs']['grid_size'] == [tiler, 3]
    assert g[next(k for k, n in g.items() if n['class_type'] == 'SaveImage')]['inputs']['images'] == [assy, 0]


def test_the_tiled_lane_asks_for_a_TILE_sized_target_not_the_frames():
    """Each tile is already ~1024 px of source. Passing the frame's 2160 here
    would upscale every tile to the whole frame's size — the OOM this lane
    exists to avoid, only worse."""
    from app.services import seedvr2_helper as svr
    plan = _plan()
    g = svr.build_tiled_workflow('src.png', dit='d', vae='v', seed=42, plan=plan,
                                 resolution=min(2160, plan['tile_width']))
    up = next(n for n in g.values() if n['class_type'] == 'SeedVR2VideoUpscaler')
    assert up['inputs']['resolution'] == 1024
    assert up['inputs']['batch_size'] == 1


def test_both_lanes_offload_and_the_tiled_one_tiles_its_VAE():
    """The two VRAM wins taken from SurpassHR's graph, independent of tiling."""
    from app.services import seedvr2_helper as svr
    full = svr.build_workflow('s.png', dit='d', vae='v', seed=42, tiled_vae=True)
    dit = next(n for n in full.values() if n['class_type'] == 'SeedVR2LoadDiTModel')
    vae = next(n for n in full.values() if n['class_type'] == 'SeedVR2LoadVAEModel')
    assert dit['inputs']['offload_device'] == 'cpu'
    assert vae['inputs']['encode_tiled'] is True and vae['inputs']['decode_tiled'] is True
    assert vae['inputs']['decode_tile_size'] == 1024
    tiled = svr.build_tiled_workflow('s.png', dit='d', vae='v', seed=42, plan=_plan())
    tvae = next(n for n in tiled.values() if n['class_type'] == 'SeedVR2LoadVAEModel')
    assert tvae['inputs']['encode_tiled'] is True


def test_the_tiled_graph_is_pure(monkeypatch):
    from app.services import seedvr2_helper as svr
    monkeypatch.setattr(svr.cfg, 'get', lambda *a, **k: pytest.fail('config read'))
    svr.build_tiled_workflow('s.png', dit='d', vae='v', seed=1, plan=_plan())


# --- The probe -------------------------------------------------------------

def test_the_TTP_names_are_the_ones_the_pack_registers():
    """Read from TTP_toolsets.py NODE_CLASS_MAPPINGS, not the README — in this
    very pack `TTP_Tile_image_size` maps to a class called `Tile_imageSize`, so
    the two spellings do not even agree."""
    from app.services import seedvr2_helper as svr
    assert svr.TTP_NODE_CLASSES == ('TTP_Image_Tile_Batch', 'TTP_Image_Assy')
    assert svr.TTP_NODE_PACK['license'] == 'MIT'


def test_tiling_probe_fails_closed_when_comfyui_is_unreachable(app, monkeypatch):
    """The OPPOSITE of the SeedVR2 asset probe, on purpose. There, failing open
    avoids blocking a run over a transient blip. Here failing open would promise
    a lane whose nodes may not exist — so an unreachable ComfyUI means no tiling."""
    from app.services import seedvr2_helper as svr
    svr.clear_nodes_cache()
    monkeypatch.setattr('app.utils.comfyui.fetch_object_info_classes', lambda: None)
    with app.app_context():
        assert svr.tiling_available(comfy_ok=False) is False


def test_tiling_is_available_only_when_both_classes_are_there(app, monkeypatch):
    from app.services import seedvr2_helper as svr
    svr.clear_nodes_cache()
    monkeypatch.setattr('app.utils.comfyui.fetch_object_info_classes',
                        lambda: {'TTP_Image_Tile_Batch'})
    with app.app_context():
        assert svr.ttp_missing_nodes() == ['TTP_Image_Assy']
        assert svr.tiling_available(True) is False
    svr.clear_nodes_cache()
    monkeypatch.setattr('app.utils.comfyui.fetch_object_info_classes',
                        lambda: set(svr.TTP_NODE_CLASSES) | {'LoadImage'})
    with app.app_context():
        assert svr.tiling_available(True) is True
    svr.clear_nodes_cache()


def test_capabilities_publishes_the_lane_and_the_ceiling(app, monkeypatch):
    from app import capabilities
    from app.services import seedvr2_helper as svr
    monkeypatch.setattr(svr, 'ttp_missing_nodes', lambda: list(svr.TTP_NODE_CLASSES))
    monkeypatch.setattr(svr, 'seedvr2_missing_nodes', lambda: [])
    with app.app_context():
        caps = capabilities.probe(force=True)['comfyui']
    for key in ('seedvr2_tiling_ready', 'seedvr2_tiling_nodes_missing',
                'seedvr2_ceiling_mp'):
        assert key in caps
    assert caps['seedvr2_tiling_ready'] is False
