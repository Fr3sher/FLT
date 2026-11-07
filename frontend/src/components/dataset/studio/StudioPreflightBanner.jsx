// react-frontend/src/components/dataset/studio/StudioPreflightBanner.jsx
/**
 * Pipeline-cannot-run banner appears on launch 409 studio_missing (P0-a). List each missing model
 * with its expected relative path and each missing ComfyUI node, preventing new installations from
 * launching grids whose tiles all fail silently. Dismissible; another launch repeats it if still
 * unresolved. missing contains family, files [{path,kind}], nodes [class_type], and optional
 * node_packs [{class_type,pack,url,search}] identifying ComfyUI-Manager packages instead of
 * leaving users to interpret class names. archMismatch contains family, detected and checkpoint
 * when header-detected architecture conflicts with the Studio family. ComfyUI would otherwise
 * ignore that LoRA and render every tile without it. This is a separate, higher-priority blocker.
 */
import { FAMILY_LABELS } from './constants';
import { studioModelSettingsLink } from '../../../utils/studioFamilySettings';
import ComfyNodeRepair from '../../setup/ComfyNodeRepair';

export default function StudioPreflightBanner({ missing, archMismatch, onDismiss, onRefresh }) {
  if (archMismatch) {
    const fam = FAMILY_LABELS[archMismatch.family] || archMismatch.family || 'this';
    const det = FAMILY_LABELS[archMismatch.detected] || archMismatch.detected || 'a different';
    const name = (archMismatch.checkpoint || '').replace(/\\/g, '/').split('/').pop();
    return (
      <div role="alert"
        className="rounded-lg border border-amber-400/40 bg-amber-400/10 px-3 py-2.5 text-sm text-amber-200 flex items-start gap-2">
        <span aria-hidden className="text-base leading-none">⚠</span>
        <p className="m-0">
          <b className="font-semibold">“{name}” is a {det} LoRA</b>, but this is the {fam} Studio —
          ComfyUI would silently drop it and every tile would render as if the LoRA were off.
          Test it in the {det} Studio, or re-deploy it under the {det} family.
        </p>
        {onDismiss && (
          <button type="button" onClick={onDismiss} aria-label="Dismiss"
            className="ml-auto px-1.5 leading-none text-amber-200/70 hover:text-amber-100">×</button>
        )}
      </div>
    );
  }
  if (!missing) return null;
  const files = missing.files || [];
  const nodes = missing.nodes || [];
  const nodePacks = missing.node_packs || [];
  if (!files.length && !nodes.length) return null;
  const fam = FAMILY_LABELS[missing.family] || missing.family || 'This';
  const modelSettingsLink = studioModelSettingsLink(missing.family);

  return (
    <div role="alert"
      className="rounded-lg border border-red-400/40 bg-red-500/10 px-3 py-2.5 text-sm text-red-200 flex flex-col gap-2">
      <div className="flex items-start gap-2">
        <span aria-hidden className="text-base leading-none">⚠</span>
        <p className="m-0 font-semibold">
          The {fam} test pipeline can’t run — your ComfyUI is missing the assets below.
          Add them, then relaunch the test.
        </p>
        {onDismiss && (
          <button type="button" onClick={onDismiss} aria-label="Dismiss"
            className="ml-auto px-1.5 leading-none text-red-200/70 hover:text-red-100">×</button>
        )}
      </div>

      {files.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-red-200/80 text-[0.6875rem] uppercase tracking-wide">
            Missing model file{files.length > 1 ? 's' : ''} — place at
          </span>
          <ul className="m-0 flex flex-col gap-0.5">
            {files.map((f) => (
              <li key={f.path} className="flex flex-col gap-0.5">
                <span className="flex flex-wrap items-baseline gap-x-2">
                  <code className="text-red-100 text-[0.6875rem] break-all">{f.path}</code>
                  <span className="text-red-200/60 text-[0.625rem]">({f.kind})</span>
                </span>
                {/*
                 * hint reports what the resolver actually searched: accepted names and scanned
                 * roots. Without it, the shown path falsely implies one exact filename is
                 * mandatory despite multiple accepted spellings. (bobba84, GitHub #18)
                 */}
                {f.hint && (
                  <span className="text-red-200/60 text-[0.625rem] leading-snug">{f.hint}</span>
                )}
              </li>
            ))}
          </ul>
          {modelSettingsLink && (
            <a href={modelSettingsLink}
              className="self-start text-sm underline hover:text-red-100">
              Install {fam} test models in Settings →
            </a>
          )}
        </div>
      )}

      {nodes.length > 0 && (
        <ComfyNodeRepair nodes={nodes} nodePacks={nodePacks} onRefresh={onRefresh} />
      )}
    </div>
  );
}
