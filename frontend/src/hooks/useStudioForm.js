import { useEffect, useRef, useState } from 'react';
import { DEFAULT_STRENGTHS } from '../components/dataset/studio/constants';
import { defaultCfgFor, defaultStepsFor, mixedModelDefaults } from '../utils/studioModelDefaults';
import { defaultModelSelection, modelSelectionError } from '../utils/studioFamilySettings';
import {
  addGuestCheckpoint, chosenCheckpoints, normalizeGuestCheckpoints,
  removeGuestCheckpoint,
} from '../utils/studioGuestCheckpoints';

const rollSeed = () => Math.floor(Math.random() * 2 ** 31);

/**
 * LoRA Test Studio form state, derived effective values, and toggles.
 * Extracted unchanged from the original LoraTestStudio.jsx.
 * Selections persist per dataset in localStorage (studioForm_v1_<id>):
 * checkpoints, strengths, prompt, model, formats/cfg/steps, seed lock,
 * generation settings. Refresh restores the last configuration.
 * d is the useLoraTestStudio payload (possibly null on initial render).
 * datasetId is the persistence namespace.
 */
/* Optional pinnedCheckpoints supplies the selection from the caller instead
   of the picker. LoRA Canvas alone differs here: clicking node chips can select
   checkpoints across datasets. Model, format, cfg, steps, seed, count and global
   settings use this same hook and component, keeping both screens consistent. */
export function useStudioForm(d, datasetId, family = null,
  { pinnedCheckpoints = null, preselectBase = null } = {}) {
  // Persist separately by dataset AND family: ZIT/SDXL/Krea each retains its own
  // checkpoints, strengths and models. Changing family remounts the studio, so
  // this hook reads the correct key on mount.
  const [persistKey] = useState(() => `studioForm_v1_${datasetId || 'x'}_${family || 'default'}`);
  // Lazy read once on mount to restore the last settings.
  const [initial] = useState(() => {
    try { return JSON.parse(localStorage.getItem(`studioForm_v1_${datasetId || 'x'}_${family || 'default'}`)) || {}; }
    catch { return {}; }
  });

  const [selCps, setSelCps] = useState(initial.selCps ?? null);              // null = all selected
  // Guest files are separate from the dataset pool.
  // null selCps still means "all of mine", without selecting every guest.
  const [guestCps, setGuestCps] = useState(() => normalizeGuestCheckpoints(initial.guestCps));
  const [selGuests, setSelGuests] = useState(initial.selGuests ?? null);
  const [selSts, setSelSts] = useState(initial.selSts ?? DEFAULT_STRENGTHS);
  const [seed, setSeed] = useState(() => initial.seed ?? rollSeed());
  const [seedLocked, setSeedLocked] = useState(initial.seedLocked ?? false);
  const [genCount, setGenCount] = useState(initial.genCount ?? 1);
  const [promptText, setPromptText] = useState(initial.promptText ?? null);  // null = follow d.prompt
  const [selModels, setSelModels] = useState(initial.selModels ?? null);
  const [selAspects, setSelAspects] = useState(initial.selAspects ?? null);
  const [selCfgs, setSelCfgs] = useState(initial.selCfgs ?? null);
  const [selSteps, setSelSteps] = useState(initial.selSteps ?? null);
  const [selSteps2, setSelSteps2] = useState(initial.selSteps2 ?? null);  // SDXL : pass 2 (detail daemon)

  /* `preselectBase` — a base named in the URL (`/studio?base=…`), used by the
     full-model card to open ON the model you asked to test.

     Three deliberate choices:
       • it wins over the persisted selection, ONCE. Same rule as the LoRA
         picker's URL preselection: an explicit navigation is a fresher intent
         than what localStorage remembers, but only for the arrival, so the very
         next click of the user is never fought over;
       • it clears the persisted CFG/steps, and that is the whole point for an
         undistilled base. A session spent on a Turbo checkpoint leaves cfg 1 /
         8 steps behind; inherited by a Raw full model they render a blurry
         sketch that reads as "the training failed". Cleared, the axes re-seed
         from `model_defaults` — the run's OWN sample settings;
       • it waits for the base to actually be in `z_models`. Selecting a value
         the payload does not know would be silently dropped by the backend
         whitelist and fall back to the first base, i.e. generate on the WRONG
         model while the UI claims otherwise. */
  const preselectedBaseRef = useRef(false);
  useEffect(() => {
    if (preselectedBaseRef.current || !preselectBase) return;
    if (!(d?.z_models || []).some((m) => m.value === preselectBase)) return;
    preselectedBaseRef.current = true;
    setSelModels([preselectBase]);
    setSelCfgs(null);
    setSelSteps(null);
  }, [preselectBase, d?.z_models]);

  // Persist every selection change per dataset so it survives refresh.
  useEffect(() => {
    try {
      localStorage.setItem(persistKey, JSON.stringify({
        selCps, guestCps, selGuests, selSts, seed, seedLocked, genCount, promptText,
        selModels, selAspects, selCfgs, selSteps, selSteps2,
      }));
    } catch { /* quota / private mode: persistence is best-effort */ }
  }, [persistKey, selCps, guestCps, selGuests, selSts, seed, seedLocked, genCount, promptText, selModels, selAspects, selCfgs, selSteps, selSteps2]);

  const checkpoints = d?.checkpoints || [];
  const allFns = checkpoints.map((c) => c.filename);
  // Filter saved checkpoints that no longer exist after a dataset change.
  // Canvas pinned checkpoints are the exact selection: do NOT filter by allFns
  // because they span datasets while d.checkpoints covers only one. Guests are
  // a separate list: null selCps means all of mine, never all guests too.
  const chosenCps = chosenCheckpoints({
    mineFns: allFns, selCps, guests: guestCps, selGuests, pinned: pinnedCheckpoints,
  });
  const effectivePrompt = promptText ?? (d?.prompt || '');
  // Default to the first entry, including Krea Official (value empty string),
  // so the default chip appears selected; the backend maps it to its wired default.
  const effectiveModels = selModels ?? defaultModelSelection(d?.z_models, d?.default_model);
  const modelError = modelSelectionError(d?.z_models,
    !preselectedBaseRef.current && preselectBase ? [preselectBase] : effectiveModels);
  const resetModels = () => {
    preselectedBaseRef.current = true;
    setSelModels(d?.z_models?.length ? [d.z_models[0].value] : null);
    setSelCfgs(null);
    setSelSteps(null);
  };
  const effectiveAspects = selAspects ?? (d?.default_aspect ? [d.default_aspect] : ['9:16']);
  // Base-model CFG/steps (bobba84, GitHub #18): undistilled Z-Image Base must not
  // inherit Turbo settings (cfg 1, 8 steps), which ruin its output. Non-null
  // selCfgs/selSteps reflect user choices and are never overwritten. Per-model
  // defaults apply only to untouched axes.
  const modelDefaultCfg = defaultCfgFor(d, effectiveModels);
  const modelDefaultSteps = defaultStepsFor(d, effectiveModels);
  const effectiveCfgs = selCfgs ?? [modelDefaultCfg];
  const effectiveSteps = selSteps ?? [modelDefaultSteps];
  // Detail daemon pass 2 is SDXL-only. Z-Image default_steps2 is null: empty axis
  // (counted as x1, omitted from the backend payload).
  const effectiveSteps2 = d?.default_steps2 != null ? (selSteps2 ?? [d.default_steps2]) : [];
  // Everything the axes multiply EXCEPT the checkpoints and the strength sweep.
  // 🧬 Blend collapses those two into one configuration (each LoRA carries its own
  // weight, they all load in the same image), so its cell count is exactly this —
  // exposed rather than divided back out of `total`, which would be a lie the
  // moment one of the two factors is zero.
  const axisTotal = effectiveAspects.length * effectiveCfgs.length * effectiveSteps.length
    * Math.max(1, effectiveSteps2.length) * Math.max(1, effectiveModels.length);
  const total = chosenCps.length * selSts.length * axisTotal;

  const toggleCp = (fn) =>
    setSelCps((cur) => {
      const base = cur ?? allFns;
      return base.includes(fn) ? base.filter((f) => f !== fn) : [...base, fn];
    });
  const addGuest = (filename) => {
    const fn = String(filename || '').trim();
    if (!fn) return;
    if (allFns.includes(fn)) {
      setSelCps((cur) => {
        const base = cur ?? allFns;
        return base.includes(fn) ? base : [...base, fn];
      });
      return;
    }
    setGuestCps((cur) => addGuestCheckpoint(cur, fn, allFns));
    setSelGuests((cur) => {
      if (cur == null) return null;
      return cur.includes(fn) ? cur : [...cur, fn];
    });
  };
  const removeGuest = (filename) => {
    setGuestCps((cur) => removeGuestCheckpoint(cur, filename));
    setSelGuests((cur) => (cur == null ? null : cur.filter((f) => f !== filename)));
  };
  const toggleGuest = (fn) =>
    setSelGuests((cur) => {
      const fns = guestCps.map((g) => g.filename);
      const base = cur ?? fns;
      return base.includes(fn) ? base.filter((f) => f !== fn) : [...base, fn];
    });
  const toggleSt = (s) =>
    setSelSts((cur) => (cur.includes(s) ? cur.filter((v) => v !== s) : [...cur, s].sort((a, b) => a - b)));
  // Toggle while retaining at least one value (formats/cfg/steps).
  const _toggleKeep = (setter, getEff) => (v) =>
    setter((cur) => {
      const base = cur ?? getEff();
      const next = base.includes(v) ? base.filter((x) => x !== v) : [...base, v].sort((a, b) => a - b);
      return next.length ? next : base;
    });
  const toggleAspect = (a) =>
    setSelAspects((cur) => {
      const base = cur ?? effectiveAspects;
      const next = base.includes(a) ? base.filter((v) => v !== a) : [...base, a];
      return next.length ? next : base;
    });
  const toggleCfg = _toggleKeep(setSelCfgs, () => effectiveCfgs);
  const toggleStep = _toggleKeep(setSelSteps, () => effectiveSteps);
  const toggleStep2 = _toggleKeep(setSelSteps2, () => effectiveSteps2);
  // Models are strings, not numbers; keep at least one model selected.
  const toggleModel = (m) => {
    preselectedBaseRef.current = true;
    setSelModels((cur) => {
      const base = cur ?? effectiveModels;
      const next = base.includes(m) ? base.filter((x) => x !== m) : [...base, m];
      return next.length ? next : base;
    });
  };

  // Generate a seed for each launch unless locked; return the seed to use.
  const nextSeed = () => {
    const s = seedLocked ? seed : rollSeed();
    if (!seedLocked) setSeed(s);
    return s;
  };

  return {
    selSts, seed, seedLocked, genCount, promptText, selModels,
    chosenCps, effectivePrompt, effectiveModels, effectiveAspects, effectiveCfgs, effectiveSteps, effectiveSteps2, total, axisTotal,
    // Selected MODEL defaults for the picker default-value labels.
    modelDefaultCfg, modelDefaultSteps,
    mixedModelDefaults: mixedModelDefaults(d, effectiveModels),
    guestCps, modelError, resetModels,
    setSelSts, setSeed, setSeedLocked, setGenCount, setPromptText,
    toggleCp, addGuest, removeGuest, toggleGuest,
    toggleSt, toggleAspect, toggleCfg, toggleStep, toggleStep2, toggleModel, rollSeed, nextSeed,
  };
}
