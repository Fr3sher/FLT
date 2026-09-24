"""Queue camera views of one picture — the Gallery (Test Studio) lane and the
dataset lane, and the caption phrase a dataset view keeps.

The plugin owns the camera policy; SDK repositories preserve ownership,
historical tables, completion linking and activity across host versions.
"""
from __future__ import annotations

import logging
import os
import random

from lds_sdk.images import DatasetImages, GalleryImages, generation_metadata

from . import camera_angles as ca
from . import qwen_camera_helper as qch

logger = logging.getLogger(__name__)

# Written into existing databases; the plugin keeps its historical spelling.
CAMERA_ANGLE = 'camera_angle'


def camera_views_for_canvas_image(user_id, image_id, poses):
    """Queue one render per requested camera position, from ONE library picture.

    Returns ``{'views': [{'candidate_id', 'job_id', 'pose', 'label'}], 'queued'}``
    or ``None`` when the image is not the caller's.

    Shape follows ✨ improve deliberately — separate rows, source never touched,
    each result landing in the same gallery next to the picture it came from —
    with one difference that matters: **one job per view.** A single job
    rendering eight poses would share a seed, a queue slot and a failure; one
    bad pose would take the other seven with it, and nothing would appear until
    the last one finished. Eight jobs means the first picture arrives in about
    twelve seconds and a failure costs one view.

    Unlike improve there is NO idempotency guard. Two presses of ✨ on the same
    picture would produce two indistinguishable upscales, so the second is
    refused; two presses here are a legitimate request for a second take of the
    same angle (a different seed, a different guess at the hidden side), which
    is exactly what someone building a dataset does. The cost is bounded by
    camera_angles.MAX_VIEWS_PER_RUN instead.
    """
    gallery = GalleryImages(user_id)
    row = gallery.get(image_id)
    if row is None:
        return None
    if row.derivation_kind == CAMERA_ANGLE:
        # A view of a view compounds two invented backdrops: the second pass
        # re-invents what the first pass already invented, and the result is
        # sold as a photograph of the original scene.
        raise ValueError(ca.ALREADY_DERIVED)
    # ✨ An improve result is NOT refused, and the distinction is the point: an
    # upscale is the SAME scene from the SAME viewpoint, only cleaner — which
    # makes it the best source this lane can get, not a compounded guess. The
    # first version of this guard refused every `derivation_kind`, and pointed
    # at a real library it was wrong on sight: the newest six tiles were all
    # improve results, so the verb read as broken on the pictures people
    # actually keep.
    if row.status != 'done' or not row.filename:
        raise ValueError(ca.SOURCE_NOT_DONE)
    source_path = gallery.path(image_id)
    if not source_path or not os.path.isfile(source_path):
        raise ValueError(ca.SOURCE_FILE_GONE)

    wanted = ca.normalize_requested(poses)      # raises on empty / unknown / too many

    # Refuse BEFORE creating any row when the weights are absent, so a missing
    # model cannot leave a dataset full of failed tiles — the lesson the Klein
    # lane already paid for (preflight in generate_variations).
    missing = qch.camera_missing_assets()
    if not qch.camera_ready(missing):
        raise qch.CameraModelsMissing(missing)

    views = []
    for azimuth, elevation, distance in wanted:
        pose = ca.pose_id(azimuth, elevation, distance)
        prompt = ca.pose_prompt(azimuth, elevation, distance)
        # Same checkpoint/step and parent, outside the training timeline. The
        # row exists BEFORE admission so a job always has somewhere to land.
        candidate = gallery.create_derivative(
            row.id, derivation_kind=CAMERA_ANGLE, prompt=prompt)
        if candidate is None:                  # source deleted during the batch
            break
        candidate_id = candidate.id
        try:
            job_id = qch.enqueue_camera_view(
                user_id=str(user_id), source_filename=row.filename,
                source_path=source_path, pose_prompt=prompt,
                # `is_lora_test` is what routes the finished job back to
                # link_completed_test_image — without it the completion looks the
                # result up as a dataset image that does not exist.
                extra_metadata={
                    'is_lora_test': True,
                    'dataset_id': str(row.dataset_id),
                    'cell_id': candidate_id,
                    'derivation_kind': CAMERA_ANGLE,
                    'parent_image_id': row.id,
                    'action': 'camera_angle',
                    'camera_pose': pose,
                })
        except Exception:
            # No ghost row: a candidate left pending with no file is exactly what
            # _active_run_count counts, so a failed enqueue that kept its row
            # would read as "a test run is already in progress" forever.
            gallery.discard_unqueued(candidate_id)
            # Views already queued keep theirs — they are real work in flight,
            # and dropping them would waste GPU already spent.
            if views:
                logger.warning('camera angles: %s queued before %s failed',
                               len(views), pose)
                break
            raise
        if not gallery.attach_job(candidate_id, job_id, camera_pose=pose):
            continue
        views.append({'candidate_id': candidate_id, 'job_id': job_id,
                      'pose': pose,
                      'label': ca.pose_label(azimuth, elevation, distance)})
    return {'views': views, 'queued': len(views)}


def camera_views_for_dataset_image(user_id, image_id, poses):
    """📷 Queue camera views of ONE dataset image — the dataset twin of the
    canvas lane, and a separate function for the same reason ✨ improve keeps
    separate routes: ``image_id`` here is a ``face_dataset_image.id``.

    The rows are PENDING candidates of the same dataset, born with:
      * ``derivation_kind = camera_angle`` and their ``camera_pose``;
      * a generation_meta stamp naming the engine, the base model, the LoRA
        and the seed that actually ran;
      * the caption starts as the pose's angle phrase (origin NULL, so the
        captioner completes it rather than being locked out) — and the captioner
        re-injects that phrase on every later pass (with_camera_pose_phrase),
        because a back view left undescribed binds "back-facing" to the trigger.

    An ✨ improve result and an import are valid sources; a camera view is not
    (a view of a view compounds two invented backdrops). Returns
    ``{'views': [{'candidate_id','job_id','pose','label'}], 'queued'}``, or
    None when the image is not the caller's.
    """
    dataset = DatasetImages(user_id)
    img = dataset.get(image_id)
    if img is None:
        return None
    dataset.require_editable(img.dataset_id)
    if img.derivation_kind == CAMERA_ANGLE:
        raise ValueError(ca.ALREADY_DERIVED)
    if not img.filename:
        raise ValueError(ca.SOURCE_NOT_DONE)
    source_path = dataset.path(image_id)
    if not source_path or not os.path.isfile(source_path):
        raise ValueError(ca.SOURCE_FILE_GONE)

    wanted = ca.normalize_requested(poses)   # raises on empty / unknown

    # Weights BEFORE rows — the Klein lane's lesson, already paid for once: a
    # preflight that ran too late left a dataset full of failed tiles.
    missing = qch.camera_missing_assets()
    if not qch.camera_ready(missing):
        raise qch.CameraModelsMissing(missing)

    # Same anti-DoS shape as generate_variations: the fan-out shares one GPU.
    in_flight = dataset.pending_count(img.dataset_id)
    if in_flight + len(wanted) > dataset.max_fanout:
        raise ValueError(f'too many generations in flight ({in_flight}), wait or cancel')

    # ⚙ Resolved ONCE for the whole run, before the loop: every view of one
    # press renders with the same weights, and the stamp says which. The seed
    # is drawn HERE and handed to the enqueue, so the row can record the seed
    # the render actually uses — the one number a "why do these two differ"
    # question always starts with.
    stamp_unet = qch.resolve_camera_unet()
    stamp_angles_lora = qch.resolve_camera_lora()[0]
    views = []
    try:
        for azimuth, elevation, distance in wanted:
            pose = ca.pose_id(azimuth, elevation, distance)
            view_seed = random.randint(0, 2 ** 64 - 1)
            row = dataset.create_derivative(
                img.id,
                derivation_kind=CAMERA_ANGLE,
                camera_pose=pose,
                generation_meta=generation_metadata(
                    engine='camera', base_model=stamp_unet,
                    loras=[{'filename': stamp_angles_lora, 'strength': 1.0}],
                    seed=view_seed),
                # The LoRA's own sentence — what regenerate would re-send, and
                # what the tile's ✏️ bubble shows as the real prompt.
                variation_prompt=ca.pose_prompt(azimuth, elevation, distance),
                # The angle phrase seeds the caption from birth (origin NULL →
                # the captioner may complete or rewrite it; its own passes then
                # re-inject the phrase). front/eye poses phrase to None and
                # that is correct: nothing worth binding, nothing written.
                caption=ca.pose_caption_phrase(pose),
            )
            if row is None:                 # source deleted during the batch
                break
            candidate_id = row.id
            try:
                job_id = qch.enqueue_camera_view(
                    user_id=str(user_id), source_filename=img.filename,
                    source_path=source_path,
                    pose_prompt=ca.pose_prompt(azimuth, elevation, distance),
                    seed=view_seed,
                    model_name='qwen_camera_dataset',
                    extra_metadata={'is_dataset': True,
                                    'dataset_id': img.dataset_id,
                                    'camera_pose': pose})
            except Exception:
                dataset.fail_unqueued(candidate_id, 'The camera view could not be queued.')
                if views:
                    logger.warning('camera dataset: %d queued before %s failed',
                                   len(views), pose)
                    break
                raise
            if not dataset.attach_job(candidate_id, job_id):
                continue                    # ⏹ Stop removed it mid-enqueue
            views.append({'candidate_id': candidate_id, 'job_id': job_id,
                          'pose': pose,
                          'label': ca.pose_label(azimuth, elevation, distance)})
    finally:
        dataset.sync_activity(img.dataset_id)
    return {'views': views, 'queued': len(views)}


def with_camera_pose_phrase(img, text):
    """The caption a camera view gets to keep: the model's words PLUS the angle.

    Applied at the VLM stamp sites through the core's ``caption.stamp`` hook,
    so the phrase survives every re-caption — seeding it only at row creation
    would last exactly until the first batch pass overwrote it. Idempotent
    (never doubled), inert for every row without a pose, and it prefixes
    rather than appends: the angle is the one fact the captioner cannot see,
    so it must not end up trailing a sentence that reads as complete without
    it."""
    phrase = ca.pose_caption_phrase(getattr(img, 'camera_pose', None))
    if not phrase:
        return text
    body = (text or '').strip()
    if phrase.lower() in body.lower():
        return body or phrase
    return f'{phrase}, {body}' if body else phrase
