// react-frontend/src/components/dataset/studio/ResultCell.jsx
/**
 * One checkpoint/strength grid cell for a format/CFG/steps variant: a strip of seed tiles, one
 * aggregated score PER CONFIG and a star for the best configuration. Extracted unchanged from old
 * LoraTestStudio renderCell, preserving ckey and score/isBest calculations. list, score and isBest
 * remain computed HERE.
 */
import ResultTile from './ResultTile';
import { cellKeyFor } from './resultKeys';

export default function ResultCell({ row, strength, variant, cellList, scoreMap, best, datasetId, onRate, onOpen, fmt }) {
  // Use the SAME function that indexed cellList (see resultKeys). Duplicated manual keys
  // previously let one-sided axis additions produce empty cells without errors. The contract is
  // tested.
  const key = cellKeyFor(row.filename, strength, variant);
  const list = cellList.get(key);
  if (!list || !list.length) {
    return <td className="px-1 text-content-subtle text-[0.625rem] text-center">—</td>;
  }
  const zk = variant.zModel || '';
  const score = scoreMap.get(`${row.filename}|${strength}|${variant.aspect || ''}|${zk}|${variant.cfg ?? ''}|${variant.steps ?? ''}|${variant.steps2 ?? ''}`);
  const isBest = best && best.checkpoint === row.filename && best.strength === strength
    && (best.aspect || '') === (variant.aspect || '') && (best.z_model || '') === zk
    && (best.cfg ?? '') === (variant.cfg ?? '') && (best.steps ?? '') === (variant.steps ?? '')
    && (best.steps2 ?? '') === (variant.steps2 ?? '');
  return (
    <td className={`align-top rounded-lg p-1 ${isBest ? 'bg-amber-400/10 outline outline-1 outline-amber-400/50' : ''}`}>
      <div className="flex items-start gap-1">
        {list.map((c) => (
          <ResultTile key={c.id} cell={c} row={row} strength={strength} variant={variant}
            datasetId={datasetId} onRate={onRate} onOpen={onOpen} fmt={fmt} />
        ))}
      </div>
      {/* Aggregated score PER CONFIG across all seeds/runs, plus confidence. */}
      <div className="flex items-center justify-end gap-1 mt-0.5">
        <span className="text-content-muted text-[0.6875rem] tabular-nums"
          title={score ? `+${score.likes} / −${score.dislikes} on ${score.images} image(s)` : ''}>
          {score && score.score !== 0 ? (score.score > 0 ? `+${score.score}` : score.score) : '·'}
          {score && score.voted > 0 && (
            <span className="text-content-subtle"> · {score.voted}/{score.images}
              {score.like_rate != null ? ` · ${Math.round(score.like_rate * 100)}%👍` : ''}</span>
          )}
          {score && score.low_confidence && score.voted > 0 && (
            <span className="text-amber-400" title="Few votes — low reliability"> ⚠</span>
          )}
          {isBest && <span aria-label="best config" title="Best config"> ★</span>}
        </span>
      </div>
    </td>
  );
}
