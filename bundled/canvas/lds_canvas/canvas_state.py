"""Canvas-owned board geometry and named layout persistence."""
import logging
import json

from lds_sdk import training_data as fds
from lds_sdk.canvas import gallery_snapshots
from .models import db

logger = logging.getLogger(__name__)


def canvas_positions(user_id, dataset_ids=None) -> dict:
    """Every remembered card position of `user_id`, grouped by dataset id.

    One request for the whole board on purpose: the canvas opens on N lanes and
    N round-trips for a handful of tiny rows would be slower than the genealogy
    fetches they have to be ready before. `dataset_ids` narrows it when the
    caller already knows the lanes it wants."""
    from .models import CanvasNodePosition
    owned = {d.id for d in fds.list_datasets(user_id)}
    if dataset_ids is not None:
        owned &= {int(i) for i in dataset_ids}
    if not owned:
        return {'positions': {}}
    rows = (CanvasNodePosition.query
            .filter(CanvasNodePosition.dataset_id.in_(list(owned))).all())
    out = {}
    for r in rows:
        out.setdefault(str(r.dataset_id), []).append(
            {'record_id': r.record_id, 'x': float(r.x), 'y': float(r.y)})
    for lane in out.values():
        lane.sort(key=lambda p: p['record_id'])
    return {'positions': out}


def save_canvas_positions(user_id, dataset_id, positions) -> dict:
    """Upsert card positions for one lane. Returns how many rows the lane holds.

    Idempotent by (dataset_id, record_id) — the canvas re-sends a position on
    every drop and re-pins the same coordinates whenever a lane gains a run, so
    a second identical write must be a no-op rather than a duplicate row.
    Non-finite coordinates are rejected outright: one NaN stored here would make
    a card unreachable on every future load, and there is no UI to fix it."""
    from .models import CanvasNodePosition
    if not fds.get_dataset(user_id, dataset_id):
        raise LookupError('dataset not found')
    wanted = {}
    for p in (positions or []):
        try:
            rid = int(p['record_id'])
            x, y = float(p['x']), float(p['y'])
        except (KeyError, TypeError, ValueError):
            continue   # malformed client entry: dropped, the rest of the board lands
        if not (x == x and y == y and abs(x) != float('inf') and abs(y) != float('inf')):
            continue
        wanted[rid] = (x, y)
    if wanted:
        existing = {r.record_id: r for r in CanvasNodePosition.query.filter(
            CanvasNodePosition.dataset_id == dataset_id,
            CanvasNodePosition.record_id.in_(list(wanted))).all()}
        for rid, (x, y) in wanted.items():
            row = existing.get(rid)
            if row is None:
                db.session.add(CanvasNodePosition(
                    dataset_id=dataset_id, record_id=rid, x=x, y=y))
            else:
                row.x, row.y = x, y
        db.session.commit()
    return {'saved': len(wanted),
            'total': CanvasNodePosition.query.filter_by(dataset_id=dataset_id).count()}


def clear_canvas_positions(user_id, dataset_id) -> dict:
    """✦ Tidy up for one lane: drop every remembered position so the automatic
    tree takes over again. The escape hatch — an arrangement tangled over twenty
    runs has to have a way back that is not "edit the database"."""
    from .models import CanvasNodePosition
    if not fds.get_dataset(user_id, dataset_id):
        raise LookupError('dataset not found')
    removed = CanvasNodePosition.query.filter_by(
        dataset_id=dataset_id).delete(synchronize_session=False)
    db.session.commit()
    return {'cleared': int(removed or 0)}


# 🖼 Bounds for a pinned image node, in the board's WORLD units (a run card is
# CARD_W = 264 wide, for scale). The floor keeps a node grabbable at any zoom;
# the ceiling is the one that matters — a node resized to 8 000 px would blow
# up its lane's extent, and ✦ Fit would then collapse the whole board to a scale
# where nothing else is readable. Enforced here as well as in the browser: the
# clamp protects the NEXT load, not just the gesture.
CANVAS_IMAGE_MIN = 96.0


CANVAS_IMAGE_MAX = 1400.0


# 🖼 How far from its lane's origin a pinned image may be parked, on either axis
# and in EITHER DIRECTION. Negative coordinates are legal: a picture is not a
# step of the lineage, and the wall at zero was what stopped a render from being
# dragged above its own lane or into the free margin beside the board. Mirrors
# IMG_REACH in frontend/src/utils/canvasImageNodes.js.
#
# A safety rail, not a design limit. The position axes had no ceiling at all
# until now — only the SIZE was bounded — so one corrupt row (1e9, a hand-edited
# database) could already blow a lane's extent up and collapse ✦ Fit to a scale
# where nothing on the board is readable. This bounds both directions at once.
CANVAS_IMAGE_REACH = 100000.0


def _clamp_image_box(x, y, w, h):
    """Lane-local geometry, clamped. Returns None for anything unusable —
    a NaN stored here would make a node unreachable on every future load and
    there is no UI to fix that.

    The position is bounded on both sides of zero rather than floored at it, so
    a picture the user parked above or left of its lane survives the round trip.
    Every row written before this read back and still reads back unchanged: the
    coordinates mean exactly what they always meant (lane-local world units) and
    every one of them is inside the rail."""
    try:
        x, y, w, h = float(x), float(y), float(w), float(h)
    except (TypeError, ValueError):
        return None
    for v in (x, y, w, h):
        if v != v or abs(v) == float('inf'):
            return None
    def reach(v):
        return min(CANVAS_IMAGE_REACH, max(-CANVAS_IMAGE_REACH, v))

    return (reach(x), reach(y),
            min(CANVAS_IMAGE_MAX, max(CANVAS_IMAGE_MIN, w)),
            min(CANVAS_IMAGE_MAX, max(CANVAS_IMAGE_MIN, h)))


# A LANE's own bounds, in board units. `h` is the room a lane reserves, header
# excluded: the floor keeps a lane grabbable (a lane shorter than its own title
# strip could never be dragged bigger again — the trap a resize handle must not
# be able to build), and the ceiling protects ✦ Fit exactly as the image one
# does. Mirrors LANE_MIN_H / LANE_MAX_H in frontend/src/utils/canvasLanePlacement.js.
CANVAS_LANE_MIN_H = 96.0


CANVAS_LANE_MAX_H = 40000.0


# …and how far from the board's ORIGIN a lane may be parked, in either
# direction on either axis. Board-absolute, unlike everything else on this
# board: a lane's position is what defines lane-local for its own contents, so
# it has nothing to be measured relative to. Mirrors LANE_REACH.
CANVAS_LANE_REACH = 100000.0


def _clamp_lane_placement(row) -> dict:
    """One lane placement, sanitised: {x?, y?, h?} — possibly empty.

    Absent, NaN and infinite all mean the SAME thing here and it is not zero:
    "let the board decide". A lane silently teleported to the origin would be
    worse than a lane the stack places itself, and there is no UI to fix a lane
    parked at NaN.

    x and y travel together: half a position is not a position."""
    def num(v):
        if v is None or v == '':
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if (f != f or abs(f) == float('inf')) else f

    def reach(v):
        return min(CANVAS_LANE_REACH, max(-CANVAS_LANE_REACH, v))

    src = row if isinstance(row, dict) else {}
    x, y, h = num(src.get('x')), num(src.get('y')), num(src.get('h'))
    out = {}
    if x is not None and y is not None:
        out['x'], out['y'] = reach(x), reach(y)
    if h is not None:
        out['h'] = min(CANVAS_LANE_MAX_H, max(CANVAS_LANE_MIN_H, h))
    return out


def canvas_lane_placements(user_id, dataset_ids=None) -> dict:
    """Every arranged LANE of `user_id`. One request for the whole board, like
    the card positions it travels with — the lanes need their overrides before
    the first paint or the board lays itself out twice."""
    from .models import CanvasLanePlacement
    owned = {d.id for d in fds.list_datasets(user_id)}
    if dataset_ids is not None:
        owned &= {int(i) for i in dataset_ids}
    if not owned:
        return {'lanes': []}
    rows = (CanvasLanePlacement.query
            .filter(CanvasLanePlacement.dataset_id.in_(list(owned))).all())
    out = []
    for r in rows:
        placement = _clamp_lane_placement({'x': r.x, 'y': r.y, 'h': r.h})
        if placement:
            out.append({'dataset_id': r.dataset_id, **placement})
    out.sort(key=lambda p: p['dataset_id'])
    return {'lanes': out}


def save_canvas_lane_placement(user_id, dataset_id, placement) -> dict:
    """Remember where ONE lane sits and how much room it keeps.

    A MERGE, not a replace: moving a lane must not forget the height its owner
    set, and resizing it must not forget where they put it. The client sends
    only what its gesture changed, so a partial body is the normal case rather
    than an error. Sending nothing usable at all DELETES the row — that is what
    "back to automatic" means, and it keeps "no placement" a single state."""
    from .models import CanvasLanePlacement
    if not fds.get_dataset(user_id, dataset_id):
        raise LookupError('dataset not found')
    row = CanvasLanePlacement.query.filter_by(dataset_id=dataset_id).first()
    current = ({'x': row.x, 'y': row.y, 'h': row.h} if row is not None else {})
    merged = _clamp_lane_placement({**_clamp_lane_placement(current),
                                    **(placement if isinstance(placement, dict) else {})})
    if not merged:
        if row is not None:
            db.session.delete(row)
            db.session.commit()
        return {'saved': 0, 'placement': None}
    if row is None:
        row = CanvasLanePlacement(dataset_id=dataset_id)
        db.session.add(row)
    row.x, row.y = merged.get('x'), merged.get('y')
    row.h = merged.get('h')
    db.session.commit()
    return {'saved': 1, 'placement': merged}


def clear_canvas_lane_placement(user_id, dataset_id) -> dict:
    """✦ Tidy up for one lane: hand it back to the automatic stack."""
    from .models import CanvasLanePlacement
    if not fds.get_dataset(user_id, dataset_id):
        raise LookupError('dataset not found')
    removed = CanvasLanePlacement.query.filter_by(
        dataset_id=dataset_id).delete(synchronize_session=False)
    db.session.commit()
    return {'cleared': int(removed or 0)}


def _clean_group(node) -> tuple:
    """🖼🖼 One row's group membership, sanitised: (group_id, group_pos).

    The id is an opaque client key (``g<image id>``, with a suffix when that one
    is taken); it is length-capped and stripped, never parsed. An empty or
    unusable id means "in no group", and then the position is meaningless and
    goes with it — a row carrying a position and no group would be a state the
    board cannot draw."""
    gid = node.get('group_id')
    gid = str(gid).strip()[:40] if gid not in (None, '') else None
    if not gid:
        return (None, None)
    try:
        pos = int(node.get('group_pos') or 0)
    except (TypeError, ValueError):
        pos = 0
    return (gid, max(0, min(10_000, pos)))


def canvas_image_nodes(user_id, dataset_ids=None) -> dict:
    """🖼 Every image pinned on the board, grouped by dataset id — geometry AND
    the image row itself, so a lane can draw its pinned pictures without a
    second round-trip per node.

    Rows whose image no longer exists are DELETED here rather than returned.
    That is the answer to the ghost node: an image deleted from a gallery (or
    with its whole dataset) leaves a row pointing at nothing, and a node that
    renders a broken picture forever is a bug that only shows up weeks later.
    The board simply loses it, silently, which is what "the picture is gone"
    should look like.

    ``visible: false`` rows ARE returned: that is the closed-but-remembered
    state, and the panel needs it to re-open an image exactly where it was."""
    from .models import CanvasImageNode
    owned = {d.id for d in fds.list_datasets(user_id)}
    if dataset_ids is not None:
        owned &= {int(i) for i in dataset_ids}
    if not owned:
        return {'nodes': {}, 'pruned': 0}
    rows = (CanvasImageNode.query
            .filter(CanvasImageNode.dataset_id.in_(list(owned))).all())
    if not rows:
        return {'nodes': {}, 'pruned': 0}
    imgs = gallery_snapshots(user_id, [r.image_id for r in rows], completed=True)
    out, pruned = {}, 0
    for r in rows:
        img = imgs.get(r.image_id)
        if img is None:
            db.session.delete(r)
            pruned += 1
            continue
        out.setdefault(str(r.dataset_id), []).append({
            'image_id': r.image_id,
            'x': float(r.x), 'y': float(r.y),
            'w': float(r.w), 'h': float(r.h),
            'visible': bool(r.visible),
            # 🖼🖼 The side-by-side strip this picture belongs to, if any. Null
            # on every row of a board that has never grouped anything — and on
            # every row of a database that predates the columns.
            'group_id': r.group_id or None,
            'group_pos': None if r.group_pos is None else int(r.group_pos),
            'image': img,
        })
    if pruned:
        db.session.commit()
    for lane in out.values():
        lane.sort(key=lambda n: n['image_id'])
    return {'nodes': out, 'pruned': pruned}


def save_canvas_image_nodes(user_id, dataset_id, nodes) -> dict:
    """Upsert pinned-image geometry for one lane.

    Body rows are {image_id, x, y, w, h, visible}. Idempotent by
    (dataset_id, image_id): a drag re-sends the node on every drop, and closing
    one re-sends it with ``visible: false`` — the row and its geometry survive,
    which is the entire point (re-opening restores where and how big it was).

    An image that does not belong to this dataset is refused, so a pinned node
    can never smuggle another dataset's render into this lane."""
    from .models import CanvasImageNode
    if not fds.get_dataset(user_id, dataset_id):
        raise LookupError('dataset not found')
    wanted = {}
    for n in (nodes or []):
        try:
            iid = int(n['image_id'])
        except (KeyError, TypeError, ValueError):
            continue   # malformed client entry: dropped, the rest of the board lands
        box = _clamp_image_box(n.get('x'), n.get('y'), n.get('w'), n.get('h'))
        if box is None:
            continue
        # 🖼🖼 Group membership travels with the row. A row that does not MENTION
        # the fields keeps whatever it had — a plain drag or resize sent by an
        # older client (or by any code path that only knows about geometry) must
        # never quietly dissolve a group.
        group = _clean_group(n) if ('group_id' in n or 'group_pos' in n) else None
        wanted[iid] = (box, bool(n.get('visible', True)), group)
    if not wanted:
        return {'saved': 0,
                'total': CanvasImageNode.query.filter_by(dataset_id=dataset_id).count()}
    legit = set(gallery_snapshots(user_id, list(wanted), dataset_id=dataset_id))
    existing = {r.image_id: r for r in CanvasImageNode.query.filter(
        CanvasImageNode.dataset_id == dataset_id,
        CanvasImageNode.image_id.in_(list(wanted))).all()}
    saved = 0
    for iid, ((x, y, w, h), visible, group) in wanted.items():
        if iid not in legit:
            continue
        gid, gpos = group if group is not None else (None, None)
        row = existing.get(iid)
        if row is None:
            db.session.add(CanvasImageNode(
                dataset_id=dataset_id, image_id=iid, x=x, y=y, w=w, h=h,
                visible=visible, group_id=gid, group_pos=gpos))
        else:
            row.x, row.y, row.w, row.h, row.visible = x, y, w, h, visible
            if group is not None:
                row.group_id, row.group_pos = gid, gpos
        saved += 1
    db.session.commit()
    return {'saved': saved,
            'total': CanvasImageNode.query.filter_by(dataset_id=dataset_id).count()}


def clear_canvas_image_nodes(user_id, dataset_id) -> dict:
    """Forget every pinned image of one lane — geometry included.

    NOT what ✦ Tidy up calls. Tidy up hands a lane back to the automatic tree,
    and there is no automatic position for a pinned image to fall back to, so
    "tidying" one could only mean throwing it away. This exists as the deliberate
    escape hatch, and nothing invokes it by accident."""
    from .models import CanvasImageNode
    if not fds.get_dataset(user_id, dataset_id):
        raise LookupError('dataset not found')
    removed = CanvasImageNode.query.filter_by(
        dataset_id=dataset_id).delete(synchronize_session=False)
    db.session.commit()
    return {'cleared': int(removed or 0)}


# How many presets one user may keep. Not a technical limit: a picker with
# fifty entries in it is a picker nobody reads, and this is a board with a
# handful of useful arrangements, not an archive.
CANVAS_PRESET_MAX = 24


CANVAS_PRESET_NAME_MAX = 80


def _preset_payload(positions, images, lanes=None) -> dict:
    """The stored shape, sanitised on the way IN as well as on the way out.

    Sanitising here is belt and braces — the restore re-validates everything
    through save_canvas_positions / save_canvas_image_nodes — but it keeps a
    single fat row from being written at all, and it means the listing can
    report honest counts without parsing arbitrary client JSON."""
    out_pos, out_img = {}, {}
    for ds_id, rows in (positions or {}).items():
        lane = []
        for p in (rows or []):
            try:
                lane.append({'record_id': int(p['record_id']),
                             'x': float(p['x']), 'y': float(p['y'])})
            except (KeyError, TypeError, ValueError):
                continue   # malformed client entry: dropped, the rest of the lane lands
        if lane:
            out_pos[str(int(ds_id))] = lane
    for ds_id, rows in (images or {}).items():
        lane = []
        for n in (rows or []):
            try:
                iid = int(n['image_id'])
            except (KeyError, TypeError, ValueError):
                continue   # malformed client entry: dropped, the rest of the lane lands
            box = _clamp_image_box(n.get('x'), n.get('y'), n.get('w'), n.get('h'))
            if box is None:
                continue
            gid, gpos = _clean_group(n)
            lane.append({'image_id': iid, 'x': box[0], 'y': box[1],
                         'w': box[2], 'h': box[3],
                         'visible': bool(n.get('visible', True)),
                         'group_id': gid, 'group_pos': gpos})
        if lane:
            out_img[str(int(ds_id))] = lane
    # 🛝 And where each LANE sat. A preset that put the cards and the pictures
    # back on a board whose lanes had since been rearranged would restore an
    # arrangement into the wrong room — the geometry is only half the memory.
    out_lanes = {}
    for ds_id, placement in (lanes or {}).items():
        clean = _clamp_lane_placement(placement)
        if clean:
            try:
                out_lanes[str(int(ds_id))] = clean
            except (TypeError, ValueError):
                continue   # malformed client key: dropped, the rest of the board lands
    return {'positions': out_pos, 'images': out_img, 'lanes': out_lanes}


def _preset_row(row) -> dict:
    try:
        payload = json.loads(row.payload or '{}')
    except (TypeError, ValueError):
        payload = {}
    positions = payload.get('positions') or {}
    images = payload.get('images') or {}
    lanes = payload.get('lanes') or {}
    return {
        'id': row.id,
        'name': row.name,
        # The counts are what the picker shows: "3 lanes · 12 cards · 8 pictures"
        # says whether this is the arrangement you meant far better than a name
        # typed in a hurry three weeks ago.
        'lanes': len(set(positions) | set(images) | set(lanes)),
        'cards': sum(len(v) for v in positions.values()),
        'images': sum(len(v) for v in images.values()),
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


def canvas_layout_presets(user_id) -> dict:
    """Every named arrangement this user has kept, newest first."""
    from .models import CanvasLayoutPreset
    rows = (CanvasLayoutPreset.query.filter_by(user_id=user_id)
            .order_by(CanvasLayoutPreset.updated_at.desc(),
                      CanvasLayoutPreset.id.desc()).all())
    return {'presets': [_preset_row(r) for r in rows], 'max': CANVAS_PRESET_MAX}


def save_canvas_layout_preset(user_id, name, positions=None, images=None,
                              lanes=None) -> dict:
    """Keep the board as it is, under a name.

    Saving under a name that already exists OVERWRITES it, deliberately: "save"
    on a board you have just adjusted means "this is the arrangement now", and
    a second entry with the same name would leave the user to guess which of
    the two the picker will hand back."""
    from .models import CanvasLayoutPreset
    clean = (name or '').strip()[:CANVAS_PRESET_NAME_MAX]
    if not clean:
        raise ValueError('a preset needs a name')
    payload = _preset_payload(positions, images, lanes)
    if not (payload['positions'] or payload['images'] or payload['lanes']):
        raise ValueError('there is nothing arranged on the board to save')
    row = CanvasLayoutPreset.query.filter_by(user_id=user_id, name=clean).first()
    if row is None:
        if CanvasLayoutPreset.query.filter_by(user_id=user_id).count() >= CANVAS_PRESET_MAX:
            raise ValueError(
                f'{CANVAS_PRESET_MAX} layout presets is the limit — delete one first')
        row = CanvasLayoutPreset(user_id=user_id, name=clean)
        db.session.add(row)
    row.payload = json.dumps(payload)
    db.session.commit()
    return {'preset': _preset_row(row)}


def apply_canvas_layout_preset(user_id, preset_id) -> dict:
    """Put a remembered arrangement back on the board.

    Every lane goes through the LIVE writers, so the ownership checks, the
    geometry clamps and the "this image is not in that lane" refusal all apply
    exactly as they do to a drag. What is missing (a run deleted since, a
    dataset the user no longer has) is simply not put back, and the counts say
    so rather than the restore failing on the first gap."""
    from .models import CanvasLayoutPreset
    row = CanvasLayoutPreset.query.filter_by(user_id=user_id, id=preset_id).first()
    if row is None:
        raise LookupError('preset not found')
    try:
        payload = json.loads(row.payload or '{}')
    except (TypeError, ValueError):
        payload = {}
    cards = pictures = 0
    for ds_id, rows in (payload.get('positions') or {}).items():
        try:
            cards += save_canvas_positions(user_id, int(ds_id), rows).get('saved', 0)
        except (LookupError, ValueError):
            continue          # that lane is gone; the rest of the board still lands
    for ds_id, rows in (payload.get('images') or {}).items():
        try:
            pictures += save_canvas_image_nodes(user_id, int(ds_id), rows).get('saved', 0)
        except (LookupError, ValueError):
            continue   # that lane is gone: the rest of the board still lands
    placed = 0
    for ds_id, placement in (payload.get('lanes') or {}).items():
        try:
            placed += save_canvas_lane_placement(
                user_id, int(ds_id), placement).get('saved', 0)
        except (LookupError, ValueError):
            continue   # that dataset is gone: the rest of the board still lands
    return {'applied': {'cards': cards, 'images': pictures, 'lanes': placed},
            'preset': _preset_row(row)}


def delete_canvas_layout_preset(user_id, preset_id) -> dict:
    from .models import CanvasLayoutPreset
    removed = CanvasLayoutPreset.query.filter_by(
        user_id=user_id, id=preset_id).delete(synchronize_session=False)
    db.session.commit()
    if not removed:
        raise LookupError('preset not found')
    return {'deleted': int(removed)}
