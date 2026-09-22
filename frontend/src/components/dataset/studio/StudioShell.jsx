// react-frontend/src/components/dataset/studio/StudioShell.jsx
/**
 * Test Studio shell keeps LoraPicker visible and switches by selection count. Two or more LoRAs
 * use ComparisonStudio with run_id, LoRA-column/strength-row grid and rankings. One uses
 * LegacyDatasetStudio with the selected dataset and its full setup/results/best settings/base
 * comparisons/presets/checkpoint statistics. Zero uses legacy Studio for a URL-preselected
 * dataset, otherwise asks for a selection. Adding/removing a second LoRA changes branches.
 * Separate components call their own hooks unconditionally and remount to reset state cleanly.
 * Legacy /dataset/studio/:id supplies preselectDataset, immediately preserving the old full Studio
 * while the picker preselects that LoRA.
 */
import { useCallback, useEffect, useState } from 'react';
import { FlaskConical } from 'lucide-react';
import { HelpBadge } from '../../../help/HelpMode';
import LoraPicker from './LoraPicker';
import LegacyDatasetStudio from './LegacyDatasetStudio';
import ComparisonStudio from './ComparisonStudio';

export default function StudioShell({ preselectDataset = null, preselectFamily = null,
  preselectBase = null, datasetId = null }) {
  // Legacy datasetId is an alias of preselectDataset.
  const preselect = preselectDataset ?? datasetId;

  const [selection, setSelection] = useState([]);
  const onSelectionChange = useCallback((sel) => setSelection(sel), []);

  // Run train_type comes from the first selected LoRA, or null with no selection.
  const runType = selection.length > 0 ? (selection[0].train_type || 'zimage') : null;

  // Base list for current train_type; fetch /api/studio/base-models?type=... whenever runType
  // changes.
  const [baseModels, setBaseModels] = useState([]);
  // The SAME response supplies family CFG/steps choices under axes. Without them, comparison/blend
  // had no render-axis controls, causing the reported missing-steps setting.
  const [axes, setAxes] = useState(null);
  // The same call supplies PER-BASE CFG/steps defaults. Without them, comparison used Turbo's CFG
  // 1 / 8 steps on undistilled Z-Image Base or full Krea 2 Raw, yielding blurry sketches mistaken
  // for failed training. Single-LoRA Studio already received this same source through its payload.
  const [modelDefaults, setModelDefaults] = useState(null);
  // The same response reports unusual default-base conditions even when models is empty;
  // installations without alternatives need this most.
  const [baseNote, setBaseNote] = useState(null);
  useEffect(() => {
    if (!runType) { setBaseModels([]); setAxes(null); setModelDefaults(null); setBaseNote(null); return; }
    let cancelled = false;
    fetch(`/api/studio/base-models?type=${encodeURIComponent(runType)}`, { credentials: 'include' })
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d) => {
        if (cancelled) return;
        setBaseModels(d.models || []);
        setAxes(d.axes || null);
        setModelDefaults(d.model_defaults || null);
        setBaseNote(d.base_note || null);
      })
      .catch(() => {
        if (!cancelled) { setBaseModels([]); setAxes(null); setModelDefaults(null); setBaseNote(null); }
      });
    return () => { cancelled = true; };
  }, [runType]);

  const comparison = selection.length >= 2;
  // Single-LoRA branch uses its dataset. With no selection, fall back to the URL-preselected
  // dataset, or show the selection prompt.
  const soloDatasetId = selection.length === 1 ? selection[0].dataset_id : preselect;
  // Use the selected ROW's family so solo Studio opens the intended pipeline, such as Krea,
  // instead of the dataset's default train_type.
  const soloFamily = selection.length === 1 ? selection[0].family : preselectFamily;

  return (
    <div className="flex flex-col gap-3">
      <header data-probe-chrome="header"
        className="flex items-center gap-2 flex-wrap sticky top-0 z-10 bg-app/80 backdrop-blur py-2">
        <h1 className="text-content font-bold flex items-center gap-2"><FlaskConical aria-hidden="true" className="h-4 w-4" />Test Studio<HelpBadge topic="page-studio" /></h1>
        {comparison && (
          <span className="px-2 py-0.5 rounded-lg border border-amber-400/40 bg-amber-400/10 text-amber-200 text-[0.6875rem] font-semibold">
            {/*
             * Neutral wording: LoraStackPanel below chooses and displays Compare/Blend. Saying
             * Comparing here would be false during Blend.
             */}
            {selection.length} LoRAs checked
          </span>
        )}
      </header>

      {/* Anchor for the bottom StudioActionBar's LoRAs shortcut. */}
      <div id="st-loras" className="scroll-mt-16">
        <LoraPicker preselectDataset={preselect} preselectFamily={preselectFamily}
          onSelectionChange={onSelectionChange} />
      </div>

      {comparison ? (
        <ComparisonStudio selection={selection} baseModels={baseModels} axes={axes}
          modelDefaults={modelDefaults} runType={runType} baseNote={baseNote} />
      ) : soloDatasetId ? (
        // key forces a clean remount when the solo LoRA OR family changes, resetting full-Studio
        // hooks/state instead of retaining the previous grid.
        <LegacyDatasetStudio key={`${soloDatasetId}:${soloFamily ?? 'default'}`}
          datasetId={String(soloDatasetId)} initialFamily={soloFamily}
          initialBase={preselectBase} />
      ) : (
        <p className="text-content-subtle text-sm rounded-lg border border-border bg-surface px-3 py-6 text-center">
          Check a LoRA above to tune and test it. Check ≥2 to compare them side by side.
        </p>
      )}
    </div>
  );
}
