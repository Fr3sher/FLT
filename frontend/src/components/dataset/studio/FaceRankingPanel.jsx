// react-frontend/src/components/dataset/studio/FaceRankingPanel.jsx
/**
 * FaceRankingPanel finds an OBJECTIVE best epoch using the automated jandordoe method. Score faces
 * asks the server to compare completed Studio cells against the dataset REFERENCE using
 * InsightFace antelopev2 in a CPU subprocess, leaving GPU/ComfyUI untouched. Rank checkpoints by
 * mean similarity; first is the measured best epoch. Match Dataset Maker thresholds: at least 0.50
 * green/match, 0.45 orange/borderline, otherwise red. As jandordoe notes, overtrained epochs can
 * score higher while looking worse from artifacts: scores rank, visual judgment decides.
 */
const scoreCls = (avg) => (avg >= 0.50 ? 'text-emerald-300'
  : avg >= 0.45 ? 'text-amber-300' : 'text-red-300');

export default function FaceRankingPanel({ ranking = [], onScore, scoring, hasCells }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface px-3 py-2.5">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-content font-semibold text-sm">🎯 Best epoch (face score)</span>
        <span className="text-content-subtle text-[0.625rem]">
          fixed-seed cells scored vs the dataset reference (InsightFace, CPU)
        </span>
        <button type="button" onClick={onScore} disabled={scoring || !hasCells}
          title={hasCells
            ? 'Score every finished cell against the reference photo, then rank the checkpoints'
            : 'Run a test first — there is nothing to score yet'}
          className="ml-auto px-3 py-1.5 rounded-lg bg-gradient-primary text-gray-950 text-xs font-semibold disabled:opacity-40">
          {scoring ? 'Scoring…' : '🎯 Score faces'}
        </button>
      </div>
      {ranking.length > 0 ? (
        <ol className="flex flex-col gap-1">
          {ranking.map((r, i) => (
            <li key={r.checkpoint}
              className={`flex items-center gap-2 rounded-md px-2 py-1 text-[0.75rem] ${i === 0
                ? 'border border-amber-400/40 bg-amber-400/10'
                : 'bg-app/40'}`}>
              <span aria-hidden="true" className="shrink-0 w-5 text-center">
                {i === 0 ? '🏆' : `${i + 1}.`}
              </span>
              <span className="text-content truncate min-w-0" title={r.checkpoint}>{r.label}</span>
              <span className={`ml-auto shrink-0 tabular-nums font-semibold ${scoreCls(r.avg)}`}>
                {r.avg.toFixed(3)}
              </span>
              <span className="shrink-0 text-content-subtle text-[0.625rem]">({r.n} img)</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="m-0 text-content-subtle text-[0.6875rem]">
          No scores yet — run a test with several checkpoints (same seed), then hit “🎯 Score faces”
          to rank the epochs objectively.
        </p>
      )}
    </div>
  );
}
