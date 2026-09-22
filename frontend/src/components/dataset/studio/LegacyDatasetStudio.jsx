// react-frontend/src/components/dataset/studio/LegacyDatasetStudio.jsx
/**
 * Full per-dataset single-LoRA Test Studio, preserving the original: RunSetupPanel, ResultsArea,
 * live BestPresetCard, persisted BestSettingsBanner, BestPerModelList, ModelComparison,
 * QuickVoteModal and StudioResultViewer. Extracted unchanged from the old StudioShell before
 * multi-LoRA support. This is StudioShell's one-selected-LoRA branch, receiving that LoRA's
 * datasetId; useLoraTestStudio/useStudioForm still manage axes, presets and applying settings to
 * Generate.
 */
import { useEffect, useState } from 'react';
import { useLoraTestStudio } from '../../../hooks/useLoraTestStudio';
import { useStudioForm } from '../../../hooks/useStudioForm';
import { useQuickVote } from '../../../hooks/useQuickVote';
import { fmt } from '../../../utils/studioFormat';
import FamilySelector from './FamilySelector';
import RunSetupPanel from './RunSetupPanel';
import FaceRankingPanel from './FaceRankingPanel';
import BestSettingsBanner from './BestSettingsBanner';
import BestPresetCard from './BestPresetCard';
import BestPerModelList from './BestPerModelList';
import ModelComparison from './ModelComparison';
import ResultsArea from './ResultsArea';
import QuickVoteModal from './QuickVoteModal';
import StudioResultViewer from './StudioResultViewer';

export default function LegacyDatasetStudio({ datasetId, initialFamily = null,
  initialBase = null }) {
  // Selected family/pipeline: null lets the server resolve the default. initialFamily comes from
  // the selected picker ROW, such as a KREA entry opening krea. Changing family REMOUNTS the
  // Studio body via key, resetting hooks and form so another pipeline's checkpoints/settings
  // cannot linger.
  const [family, setFamily] = useState(initialFamily);
  useEffect(() => { setFamily(initialFamily); }, [datasetId, initialFamily]);  // Reset on row changes.
  return (
    <StudioBody key={`${datasetId}:${family ?? 'default'}`}
      datasetId={datasetId} family={family} onFamilyChange={setFamily}
      initialBase={initialBase} />
  );
}

function StudioBody({ datasetId, family, onFamilyChange, initialBase = null }) {
  const studio = useLoraTestStudio(datasetId, family);
  const d = studio.data;
  const form = useStudioForm(d, datasetId, d?.family || family,
    { preselectBase: initialBase });
  const vote = useQuickVote(studio.rate);
  const [lbImg, setLbImg] = useState(null);
  // Ordered lightbox set is frozen on opening from ResultsArea (see flipOrder). Keep a snapshot
  // instead of live data so polling cannot reorder images during comparison.
  const [lbItems, setLbItems] = useState([]);
  const openLightbox = (cell, items) => { setLbImg(cell); setLbItems(items || []); };

  // Lightbox delegates votes here. Update both the displayed image and navigation snapshot so vote
  // controls reflect changes immediately, including when returning to an image, matching the old
  // local setLbImg behavior.
  const rateLightbox = (id, nv) => {
    studio.rate(id, nv);
    setLbImg((p) => (p && p.id === id ? { ...p, rating: nv } : p));
    setLbItems((arr) => arr.map((c) => (c.id === id ? { ...c, rating: nv } : c)));
  };

  if (!d || !d.checkpoints?.length) {
    return (
      <div className="flex flex-col gap-3">
        {d && <FamilySelector families={d.available_families} active={d.family} onSelect={onFamilyChange} />}
        <p className="text-content-subtle text-sm rounded-lg border border-border bg-surface px-3 py-6 text-center">
          {d ? 'No testable checkpoint for this pipeline (train it first).' : 'Loading…'}
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <FamilySelector families={d.available_families} active={d.family} onSelect={onFamilyChange} />
      {d?.trigger_word && (
        <div className="flex items-center gap-2 flex-wrap">
          <code className="px-2 py-0.5 rounded-lg border border-indigo-400/40 bg-indigo-500/10 text-indigo-300 text-[0.6875rem] font-semibold">
            {d.trigger_word}
          </code>
          {d?.best_settings && (
            <span className="text-amber-300 text-[0.6875rem]" title="Saved winning settings">
              ★ {fmt(d.best_settings.strength)}
            </span>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-4 items-start">
        <aside className="flex flex-col gap-2 lg:sticky lg:top-16 lg:max-h-[calc(100vh-7rem)] lg:overflow-auto">
          <RunSetupPanel d={d} studio={studio} form={form} datasetId={datasetId} />
        </aside>
        <main id="st-results" className="flex flex-col gap-3 min-w-0 scroll-mt-16">
          {/*
           * OBJECTIVE best epoch: InsightFace checkpoint ranking complements the vote-based
           * best_preset directly below.
           */}
          <FaceRankingPanel ranking={d.face_ranking} onScore={studio.scoreFaces}
            scoring={studio.scoring}
            hasCells={(d.cells || []).some((c) => c.status === 'done')} />
          <BestPresetCard preset={d.best_preset} onMemorize={studio.setBest} fmt={fmt} />
          <BestSettingsBanner best={d.best_settings} onClear={() => studio.clearBest(d.family)} fmt={fmt} />
          <BestPerModelList items={d.best_per_model} breakdown={d.checkpoint_breakdown} datasetId={datasetId}
            onMemorize={studio.setBest} fmt={fmt} />
          <ModelComparison items={d.model_comparison} />
          <ResultsArea datasetId={datasetId} d={d} studio={studio} vote={vote} onOpen={openLightbox} />
        </main>
      </div>

      <QuickVoteModal vote={vote} datasetId={datasetId} fmt={fmt} />
      {lbImg && (
        <StudioResultViewer img={lbImg} items={lbItems}
          onRate={rateLightbox} onNavigate={setLbImg} onClose={() => setLbImg(null)} />
      )}
    </div>
  );
}
