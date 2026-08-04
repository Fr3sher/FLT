"""One decode per clip, every metric out of it — and how per-frame numbers become
a per-clip verdict.

WHY ONE PASS. Decoding is roughly 85 % of this lane's cost, measured on a real
4.5-hour corpus once shot detection moved to the GPU. Motion, exposure, sharpness
and freeze detection are each nearly free once a frame is in hand, so writing them
as four passes would multiply the only expensive part by four. Everything below
consumes ONE list of per-frame readings.

WHY THE AGGREGATION IS NOT UNIFORM, WHICH IS THE SUBTLE PART. The model trains on
EVERY frame, so the useful question is rarely "what is the average?":

  exposure  → MIN. A half-second fade in the middle ruins the sample. An average
              of 0.87 hides a stretch of 0.02 completely.
  sharpness → p90. "Does real sharpness exist in this clip?" Legitimate motion
              blur drags a mean down, so a threshold on a mean rejects exactly the
              clips with the most interesting movement. p90 rather than the p75
              a first draft used, and the arithmetic decides it: a clip that is
              sharp for a fifth of its length is perfectly usable, and p75 sits
              inside the blurred four fifths and calls it soft. p90 finds it,
              while still ignoring a single fluke frame that a max would trust.
  motion    → mean AND a high percentile. "Does anything move at all?" and "is it
              thrashing?" are different questions and cannot share a number.
  freeze    → the SHARE of near-still frames. A frozen second inside a lively shot
              leaves the mean perfectly healthy; only the share reveals it.

WHY RAW SCORES ARE STORED AND VERDICTS ARE NOT. Same philosophy as the image
bank: retuning a threshold then re-sorts the bank with no rescan. It matters more
here than there, because the published thresholds DO NOT TRANSFER — the floor a
public pipeline uses lands at the 7th percentile of this machine's own test bank.
A cut belongs to the bank being worked on, not to a constant.
"""

# A frame counts as "still" below this normalised motion magnitude. Not a quality
# threshold — a near-zero test, used only to measure the SHARE of frozen frames.
# The value is a floor on numerical noise, not a judgement about movement.
_STILL_EPSILON = 1e-5

# Exposure band a frame must sit in to represent its clip (thumbnail, embedding).
# Outside it, violent local contrast comes from a flash or a dissolve edge, not
# from real detail. Deliberately loose — this guards against degenerate frames,
# it does not judge the clip (luma_min does that).
_LUMA_SANE_LOW = 0.06
_LUMA_SANE_HIGH = 0.97


def percentile(values, p):
    """Linear-interpolation percentile. None for an empty list — never 0.0, which
    would be a measurement rather than the absence of one."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = p * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    return float(ordered[low] * (1 - frac) + ordered[high] * frac)


def summarise(frames, fps):
    """Collapse per-frame readings into the numbers stored on a clip.

    `frames` is a list of {'luma', 'sharp', 'motion'} in decode order. An empty
    list is `unreadable`, NOT a clip of zeros: collapsing the two would make a
    file we could not open look like a perfectly black, perfectly still clip, and
    it would then be filtered out for the wrong reason.
    """
    if not frames:
        return {'metrics_state': 'unreadable', 'motion_mean': None,
                'motion_p95': None, 'luma_min': None, 'luma_mean': None,
                'sharpness_p90': None, 'freeze_ratio': None,
                'sharpest_frame_s': None, 'first_frame_sharpness': None}

    lumas = [f['luma'] for f in frames]
    sharps = [f['sharp'] for f in frames]
    motions = [f['motion'] for f in frames]
    # The ambassador frame: sharpest AMONG frames with sane exposure. The score
    # uses p90 so one lucky frame cannot vouch for the clip, but the frame CHOICE
    # is an argmax — and an overexposed flash or a dissolve-to-black edge carries
    # huge local contrast while being useless to look at or to embed. When every
    # frame violates the constraint (a clip that is all flash), the plain argmax
    # returns: a bad thumbnail beats no thumbnail, and the flags tell the story.
    candidates = [i for i in range(len(frames))
                  if _LUMA_SANE_LOW <= lumas[i] <= _LUMA_SANE_HIGH]
    pool = candidates or range(len(frames))
    sharpest = max(pool, key=sharps.__getitem__)

    return {
        'metrics_state': 'ok',
        # Two numbers for two questions — see the module docstring.
        'motion_mean': sum(motions) / len(motions),
        'motion_p95': percentile(motions, 0.95),
        # The WORST moment, because that is the one the model also learns.
        'luma_min': min(lumas),
        'luma_mean': sum(lumas) / len(lumas),
        # "Is there real sharpness anywhere", not "is it sharp on average".
        'sharpness_p90': percentile(sharps, 0.90),
        'freeze_ratio': sum(1 for m in motions if m <= _STILL_EPSILON) / len(motions),
        # Frame 0 measured on its own: for image-to-video targets it IS the
        # conditioning image, and nobody chooses it — it is whatever the cut
        # starts on. A gorgeous clip with a blurred first frame is a bad i2v
        # clip; the number was already computed, storing it is free.
        'first_frame_sharpness': sharps[0],
        # Free, since every frame was measured anyway, and a better thumbnail than
        # the middle frame — a shot boundary is where a cut just happened, so the
        # middle is a guess while this is a measurement.
        'sharpest_frame_s': sharpest / float(fps) if fps else None,
    }


def verdicts(scores, thresholds):
    """The flags a clip carries RIGHT NOW, given the cuts in force. Computed at
    read time from the raw scores, so moving a cut re-sorts the bank instantly.

    An unmeasured score never produces a flag. Absence of measurement must not
    read as a defect — that is how a scan that failed quietly becomes a bank that
    appears to have filtered half its clips.
    """
    flags = set()

    motion = scores.get('motion_mean')
    floor = thresholds.get('motion_floor')
    if motion is not None and floor is not None and motion < floor:
        flags.add('still')

    luma = scores.get('luma_min')
    luma_floor = thresholds.get('luma_floor')
    if luma is not None and luma_floor is not None and luma < luma_floor:
        flags.add('black')

    freeze = scores.get('freeze_ratio')
    freeze_max = thresholds.get('freeze_max')
    if freeze is not None and freeze_max is not None and freeze > freeze_max:
        # Deliberately its own flag, not a stillness one: a still clip is useless,
        # while a clip with a frozen stretch can be re-cut around it. Different
        # defects, different remedies.
        flags.add('freeze')

    agitated = scores.get('motion_p95')
    ceiling = thresholds.get('motion_ceiling')
    if agitated is not None and ceiling is not None and agitated > ceiling:
        flags.add('agitated')

    sharp = scores.get('sharpness_p90')
    sharp_floor = thresholds.get('sharpness_floor')
    if sharp is not None and sharp_floor is not None and sharp < sharp_floor:
        flags.add('soft')

    first = scores.get('first_frame_sharpness')
    first_floor = thresholds.get('first_frame_floor')
    if first is not None and first_floor is not None and first < first_floor:
        # Advisory like every flag, and mostly meaningful when the target is
        # image-to-video — the first frame is that lane's conditioning image.
        flags.add('soft_start')

    return flags


def dry_run(bank_scores, thresholds):
    """How many clips EACH cut would remove, plus how many would be removed in
    total — before anything is committed.

    Never a silent filter, and the count is per RULE rather than a lump sum: a
    public dataset pipeline once kept 47 clips out of 1493 with one mis-set
    threshold and only discovered it afterwards. A single total would have looked
    equally alarming for a filter that was working correctly.

    `total_flagged` counts CLIPS, not flags, so a clip caught by two rules is not
    counted twice — otherwise the preview overstates the damage.
    """
    counts = {}
    flagged_clips = 0
    for scores in bank_scores:
        flags = verdicts(scores, thresholds)
        if flags:
            flagged_clips += 1
        for flag in flags:
            counts[flag] = counts.get(flag, 0) + 1
    counts['total_flagged'] = flagged_clips
    return counts
