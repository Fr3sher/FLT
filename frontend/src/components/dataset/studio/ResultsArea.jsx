// react-frontend/src/components/dataset/studio/ResultsArea.jsx
/**
 * LoRA Test Studio Results area owns showResults and selRun state. Recompute
 * run/configuration/variant groupings from d.cells and d.scores, preserving the old
 * LoraTestStudio.jsx behavior, then show the run selector and one grid per aspect/CFG/steps
 * variant.
 */
import { useCallback, useMemo, useState } from 'react';
import { fmt } from '../../../utils/studioFormat';
import { flipOrder } from './flipOrder';
import { runKey, variantKey, variantOf, cellKey, distinctPrompts } from './resultKeys';
import RunSelector from './RunSelector';
import ResultsGrid from './ResultsGrid';
import ExportGridModal from './ExportGridModal';

export default function ResultsArea({ datasetId, d, studio, vote, onOpen }) {
  // Collapse results grids to keep the page uncluttered.
  const [showResults, setShowResults] = useState(true);
  // Selected run; null defaults to the most recent run.
  const [selRun, setSelRun] = useState(null);
  // Export grid dialog combines the displayed run into ONE shareable image.
  const [exportOpen, setExportOpen] = useState(false);

  // Group by RUN: one launch shares seed, prompt and model setup. Show only the selected run,
  // newest by default, to avoid mixing previously voted tests with a new launch.
  const runs = useMemo(() => {
    const groups = new Map();
    for (const c of d?.cells || []) {
      // A launch is identified by run_id (see resultKeys.runKey), including all batch seeds, swept
      // base models and batch prompts. Model and prompt are VARIANT axes, not separate runs;
      // putting them in the run key split N prompts into N pseudo-runs, only one of which was
      // displayed.
      const key = runKey(c);
      let g = groups.get(key);
      if (!g) {
        g = { key, seed: c.run_seed ?? c.seed, prompt: c.prompt || '', models: new Set(),
              prompts: new Set(), cells: [], latestId: 0, likes: 0, dislikes: 0 };
        groups.set(key, g);
      }
      g.cells.push(c);
      if (c.z_model_label) g.models.add(c.z_model_label);
      g.prompts.add(c.prompt || '');
      if (c.id > g.latestId) g.latestId = c.id;
      if (c.rating === 1) g.likes += 1; else if (c.rating === -1) g.dislikes += 1;
    }
    return [...groups.values()].map((g) => ({
      ...g, modelLabel: g.models.size > 1 ? `${g.models.size} models` : ([...g.models][0] || ''),
      // Like models, a prompt batch announces its COUNT, not its first prompt; naming one of five
      // would misrepresent the selection.
      promptLabel: g.prompts.size > 1 ? `${g.prompts.size} prompts` : g.prompt,
    })).sort((a, b) => b.latestId - a.latestId);
  }, [d]);
  const activeRunKey = (runs.find((r) => r.key === selRun) ? selRun : runs[0]?.key) || null;
  const displayedCells = useMemo(() => {
    const r = runs.find((x) => x.key === activeRunKey);
    return r ? r.cells : [];
  }, [runs, activeRunKey]);

  // Index displayed-run configurations with resultKeys.cellKey: checkpoint, strength and variant
  // INCLUDING PROMPT, using the same function as ResultCell lookup. Include ALL batch seeds per
  // configuration, sorted into a seed strip.
  const cellList = useMemo(() => {
    const m = new Map();
    for (const c of displayedCells) {
      const k = cellKey(c);
      if (!m.has(k)) m.set(k, []);
      m.get(k).push(c);
    }
    for (const arr of m.values()) arr.sort((a, b) => (a.seed || 0) - (b.seed || 0));
    return m;
  }, [displayedCells]);

  // Lightbox navigation uses DISPLAYED cells from the current run. Keep strength variants of the
  // same rendering adjacent: variant (z_model/aspect/cfg/steps/prompt), checkpoint, seed, then
  // STRENGTH last. Prompt belongs with variant axes so navigation follows displayed grids instead
  // of jumping among prompts. A single prompt is constant, preserving previous ordering.
  const navImages = useMemo(
    () => flipOrder(displayedCells, (c) => [
      c.z_model_label || c.z_model || '', c.aspect || '', c.cfg ?? 0,
      c.steps ?? 0, c.steps2 ?? 0, c.prompt || '', c.label || '',
      c.seed ?? 0, c.strength ?? 0,
    ]),
    [displayedCells],
  );
  // Pass the ordered set ALONGSIDE the opened cell. The parent owns lightbox state but this
  // component owns ordering with displayedCells.
  const handleOpen = useCallback((cell) => onOpen(cell, navImages), [onOpen, navImages]);

  // Cross-run scores PER CONFIG include model, CFG and steps, matching the backend.
  const scoreMap = useMemo(() => {
    const m = new Map();
    for (const s of d?.scores || []) {
      m.set(`${s.checkpoint}|${s.strength}|${s.aspect || ''}|${s.z_model || ''}|${s.cfg ?? ''}|${s.steps ?? ''}|${s.steps2 ?? ''}`, s);
    }
    return m;
  }, [d]);

  // One grid per displayed-run variant: aspect, CFG, steps and PROMPT. Prompt is another axis: N
  // prompts produce N tables, just like N CFG values.
  const variantsInData = useMemo(() => {
    const m = new Map();
    for (const c of displayedCells) {
      const k = variantKey(c);
      if (!m.has(k)) m.set(k, variantOf(c));
    }
    // Do not sort by prompt text: batch variants differing only in prompt compare equal, so stable
    // sorting retains the user's selection order. Alphabetical sorting would discard that
    // meaningful order.
    return [...m.values()].sort((a, b) =>
      (a.zModelLabel || '').localeCompare(b.zModelLabel || '')
      || a.aspect.localeCompare(b.aspect) || ((a.cfg ?? 0) - (b.cfg ?? 0))
      || ((a.steps ?? 0) - (b.steps ?? 0)) || ((a.steps2 ?? 0) - (b.steps2 ?? 0)));
  }, [displayedCells]);

  // Single-prompt runs need no prompt labels repeating the same text on every table. Batches need
  // labels to distinguish prompts.
  const showPromptLabels = useMemo(() => distinctPrompts(displayedCells) > 1, [displayedCells]);

  const gridRows = useMemo(() => {
    const seen = new Map();
    for (const c of displayedCells) if (!seen.has(c.checkpoint)) seen.set(c.checkpoint, c.label);
    return [...seen.entries()].map(([filename, label]) => ({ filename, label }))
      .sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }));
  }, [displayedCells]);

  const gridCols = useMemo(() => {
    const set = new Set(displayedCells.map((c) => c.strength));
    return [...set].sort((a, b) => a - b);
  }, [displayedCells]);  // Depend on displayed cells, not d, or columns stay frozen when switching runs.
  // Active run object and available axes for the export dialog.
  const activeRun = useMemo(() => runs.find((r) => r.key === activeRunKey) || null, [runs, activeRunKey]);
  const exportAspects = useMemo(
    () => [...new Set(displayedCells.map((c) => c.aspect).filter(Boolean))].sort(),
    [displayedCells]);
  const canExport = displayedCells.some((c) => c.status === 'done' && c.filename);

  // Quick-vote mode steps through unvoted images with swipe, like and dislike.
  const unvoted = displayedCells.filter((c) => c.status === 'done' && c.filename && !c.rating);
  // Second pass: revote ONLY liked images to refine selection. Dislike turns
  // them red, like reconfirms them, and skipping leaves them green.
  const greens = displayedCells.filter((c) => c.status === 'done' && c.filename && c.rating === 1);

  if (gridRows.length === 0) return null;

  return (
    <div className="flex flex-col gap-1">
      <RunSelector
        runs={runs}
        activeRunKey={activeRunKey}
        onSelect={(key) => setSelRun(key)}
        unvotedCount={unvoted.length}
        onStartVote={() => vote.startVoting(unvoted)}
        greenCount={greens.length}
        onStartReVote={() => vote.startVoting(greens, '♻️ Reconfirm the 👍')}
        displayedCount={displayedCells.length}
        showResults={showResults}
        onToggleResults={() => setShowResults((v) => !v)}
        canExport={canExport}
        onExport={() => setExportOpen(true)}
      />
      {showResults && (
        <ResultsGrid
          gridRows={gridRows}
          gridCols={gridCols}
          variantsInData={variantsInData}
          showPromptLabels={showPromptLabels}
          cellList={cellList}
          scoreMap={scoreMap}
          best={d.best_cell}
          datasetId={datasetId}
          onRate={studio.rate}
          onOpen={handleOpen}
          fmt={fmt}
        />
      )}
      <ExportGridModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        datasetId={datasetId}
        family={d.family}
        run={activeRun}
        aspects={exportAspects}
        rows={gridRows.length}
        cols={gridCols.length}
      />
    </div>
  );
}
