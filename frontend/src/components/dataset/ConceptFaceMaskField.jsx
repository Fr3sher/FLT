/* Concept face masking — the Advanced training option and its preview.
   Reported by shivdbz2010 (GitHub issue #15): a concept LoRA also learns the faces
   of its dataset, so combining it with a character LoRA makes the two fight over
   the identity.

   Everything here is DECISION support, placed where the decision is made (next to
   the checkbox, before training), not in the image grid where it would be a
   curiosity. Three things are visible before you commit:
     - what the mask would actually cover, drawn on your own photos;
     - what the head-coverage setting does, redrawn live as you drag it;
     - how many images got no face at all, because a PARTLY masked set is the bad
       case: the faces left unmasked are then the only ones carrying loss weight.

   The overlay idiom (normalised coords -> percentage-positioned absolute divs over
   a relative wrapper) is the one WatermarkRegionEditor already uses; the geometry
   lives in utils/faceMaskBox.js, mirrored from the Python that paints the real mask. */
import { useState } from 'react';
import { postJson } from '../../hooks/useDataset';
import { HelpBadge } from '../../help/HelpMode';
import { boxStyle, coverageFraction, MAX_COVERAGE } from '../../utils/faceMaskBox';

const imageUrl = (datasetId, filename) =>
  `/api/dataset/${datasetId}/img/${encodeURIComponent(filename)}`;

/* One sample with its mask drawn over it. `expand` is applied here, in the
   browser, so dragging the slider is instant — the server pass ran once and
   returned the raw detected boxes. */
function SamplePreview({ datasetId, sample, expand }) {
  const boxes = sample.boxes || [];
  const covered = coverageFraction(boxes, expand);
  const tooLarge = covered > MAX_COVERAGE;
  return (
    <figure className="min-w-0">
      <div className="relative overflow-hidden rounded-lg border border-border bg-black">
        <img src={imageUrl(datasetId, sample.filename)} alt=""
          className="block w-full h-auto select-none" loading="lazy" />
        {boxes.map((b, i) => (
          <div key={i} aria-hidden style={boxStyle(b, expand)}
            className={`absolute rounded-[50%] border-2 ${tooLarge
              ? 'border-amber-300 bg-amber-400/25'
              : 'border-sky-300 bg-sky-400/35'}`} />
        ))}
        {!boxes.length && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="rounded-lg bg-black/75 px-2 py-1 text-[0.6875rem] font-semibold text-amber-200">
              no face found
            </span>
          </div>
        )}
      </div>
      <figcaption className="mt-1 text-[0.625rem] leading-tight text-content-subtle">
        {!boxes.length
          ? 'Trains unmasked — nothing was detected here.'
          : tooLarge
            ? `Covers ${Math.round(covered * 100)}% of the frame — left unmasked.`
            : `${boxes.length} face${boxes.length > 1 ? 's' : ''} · ${Math.round(covered * 100)}% of the frame`}
      </figcaption>
    </figure>
  );
}

export default function ConceptFaceMaskField({
  datasetId, enabled, supported, conceptConflict, faceCapability, expandDefault, onToggle,
}) {
  const [preview, setPreview] = useState(null);
  const [expand, setExpand] = useState(expandDefault ?? 2);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  if (!supported) return null;          // concept datasets only

  const runPreview = async () => {
    setBusy(true);
    setErr(null);
    try {
      const d = await postJson(`/api/dataset/${datasetId}/train/face-mask-preview`, { limit: 6 });
      if (d && d.ok) {
        setPreview(d);
        if (typeof d.expand === 'number') setExpand(d.expand);
      } else {
        setErr((d && d.error) || 'preview failed');
      }
    } catch {
      setErr('preview failed');
    } finally {
      setBusy(false);
    }
  };

  const cov = preview?.coverage;
  // A partially masked set is worse than a consistently unmasked one, so this is a
  // warning, not a statistic. Only meaningful once at least one face was found.
  const partial = cov && cov.masked > 0 && cov.masked < cov.total;

  return (
    <div className="flex flex-col gap-0.5">
      <label className="flex items-center gap-2 flex-wrap cursor-pointer">
        <span className="text-content text-[0.75rem] w-28 shrink-0 inline-flex items-center gap-1">
          Mask faces<HelpBadge topic="training.mask_faces" />
        </span>
        <input type="checkbox" checked={Boolean(enabled)} disabled={faceCapability === false}
          onChange={(e) => onToggle(e.target.checked)}
          aria-label="Mask faces while training this concept"
          className="h-4 w-4 rounded border-border bg-surface accent-indigo-500 disabled:opacity-40" />
        <span className="text-content-muted text-[0.75rem]">keep the act, drop the identities</span>
      </label>

      {faceCapability === false && (
        <span className="text-amber-300 text-[0.6875rem]">
          ⚠️ Face detection isn&apos;t installed, so faces can&apos;t be found or masked. Install the
          ML extras from the Setup tab (Face-similarity scoring) to enable this.
        </span>
      )}

      <span className="text-content-subtle text-[0.6875rem] leading-relaxed">
        <b className="text-content-muted font-medium">Why:</b> a concept LoRA also picks up the
        faces it was trained on, and then pulls against a character LoRA over whose face to
        render. This weighs the detected faces down in the training loss, so the concept
        binds to the act rather than to the people in your photos. Your images are never
        altered — nothing is blurred or painted over, only the loss is re-weighted.
        <b className="text-content-muted font-medium"> How:</b> turn it on, then preview it on
        your own shots. Adjust the head coverage in Settings ▸ Training if the mask sits too
        tight or too wide.
      </span>

      {/* The maintainers' answer, stated where the decision is taken. Without it we
          ship a patch people reach for INSTEAD of fixing the dataset. */}
      <span className="text-content-subtle text-[0.6875rem] leading-relaxed">
        <b className="text-content-muted font-medium">Worth knowing:</b> the people who maintain
        these trainers consider dataset variety to matter more than masking here. A concept shown
        by ten different people already dilutes identity; with two, the faces are as constant as
        the concept itself and no mask fully makes up for it. Nobody has published a measured
        before/after of face masking on a concept LoRA — this gives you the lever, not a promise.
      </span>

      {conceptConflict && (
        <span className="text-amber-300 text-[0.6875rem] leading-relaxed">
          ⚠️ Your concept description mentions the face, mouth or gaze. If the face is where your
          concept actually happens, masking it can erase the thing you are teaching. Preview it
          before you train — you know your dataset, so this is a heads-up, not a block.
        </span>
      )}

      {enabled && faceCapability !== false && (
        <div className="mt-1">
          <button type="button" onClick={runPreview} disabled={busy}
            className="min-h-8 rounded-lg border border-border bg-surface px-2.5 text-[0.6875rem] font-semibold text-content hover:bg-surface-raised disabled:opacity-50">
            {busy ? 'Looking for faces…' : preview ? 'Refresh preview' : '👁 Preview the mask'}
          </button>
          {err && <span className="ml-2 text-amber-300 text-[0.6875rem]">{err}</span>}

          {preview && (
            <div className="mt-2 rounded-lg border border-border bg-app/40 p-2">
              {cov && (
                <p className={`text-[0.6875rem] ${partial ? 'text-amber-300' : 'text-content-muted'}`}>
                  {partial && '⚠️ '}
                  Masked on {cov.masked} of {cov.total} image{cov.total > 1 ? 's' : ''}
                  {cov.no_face > 0 && ` · ${cov.no_face} with no face found`}
                  {cov.too_large > 0 && ` · ${cov.too_large} too close-up to mask`}
                  {cov.failed > 0 && ` · ${cov.failed} unreadable`}
                  {partial && ' — the unmasked faces are the only ones the LoRA still learns from, '
                    + 'so they end up over-represented.'}
                </p>
              )}
              <label className="mt-2 flex items-center gap-2 flex-wrap text-[0.6875rem] text-content-muted">
                <span className="shrink-0">Head coverage</span>
                <input type="range" min="1" max="3" step="0.1" value={expand}
                  onChange={(e) => setExpand(parseFloat(e.target.value))}
                  aria-label="Preview head coverage"
                  className="w-32 accent-indigo-500" />
                <span className="tabular-nums text-content">×{expand.toFixed(1)}</span>
                <span className="text-content-subtle">
                  preview only — save it in Settings ▸ Training
                </span>
              </label>
              {/* 400px-first: one column on a phone, more as the panel widens. */}
              <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-2">
                {preview.samples.map((s) => (
                  <SamplePreview key={s.image_id} datasetId={datasetId} sample={s} expand={expand} />
                ))}
              </div>
              <p className="mt-1.5 text-[0.625rem] leading-tight text-content-subtle">
                Images where no face was found are shown first — those are the ones worth looking at.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
