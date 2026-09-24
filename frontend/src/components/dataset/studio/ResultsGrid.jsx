// react-frontend/src/components/dataset/studio/ResultsGrid.jsx
/**
 * Results grids: one table per aspect/CFG/steps/prompt variant. Rows are checkpoints, columns
 * strengths, and cells are ResultCell tile strips with score and best marker. Preserve the old
 * LoraTestStudio table's Tailwind classes and checkpoint/strength header. Prompt batches reuse
 * existing sweep geometry: N prompts produce N tables, each labeled with its prompt.
 * showPromptLabels adds that row only when multiple prompts need distinguishing.
 */
import { useMemo } from 'react';
import ResultCell from './ResultCell';
import useBatchThumbs from '../../../hooks/useBatchThumbs';
import { promptLabel } from './resultKeys';

export default function ResultsGrid({ gridRows, gridCols, variantsInData, showPromptLabels, cellList, scoreMap, best, datasetId, onRate, onOpen, fmt }) {
  // Batch-prefetch every finished tile's thumbnail so the densest surface in the
  // app pays one round trip per batch on a high-RTT link, not one per tile.
  // Done filenames are unique per dataset, so a plain list is a safe key.
  const doneFiles = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const list of cellList.values()) {
      for (const c of list) {
        if (c.status === 'done' && c.filename && !seen.has(c.filename)) {
          seen.add(c.filename);
          out.push(c.filename);
        }
      }
    }
    return out;
  }, [cellList]);
  const { getBlobUrl: thumbUrlFor } = useBatchThumbs(
    doneFiles,
    (files) => ({ url: `/api/dataset/${datasetId}/thumbs?s=256`, body: JSON.stringify({ files }) }),
  );
  return variantsInData.map((variant) => (
    <div key={variant.key} className="flex flex-col gap-1">
      {showPromptLabels && variant.prompt && (
        // Keep the full prompt in title, but the visible label must fit one line even at 400 px.
        // Test prompts contain hundreds of characters and would otherwise push the grid off
        // screen.
        <span className="text-content text-[0.6875rem] font-medium truncate max-w-full"
          title={variant.prompt}>
          <span aria-hidden>📝</span> {promptLabel(variant.prompt)}
        </span>
      )}
      {variantsInData.length > 1 && (
        <span className="text-content-muted text-[0.625rem] uppercase">
          {variant.zModelLabel ? `${variant.zModelLabel} · ` : ''}Format {variant.aspect || '—'}{variant.cfg != null ? ` · CFG ${fmt(variant.cfg)}` : ''}{variant.steps != null ? ` · ${variant.steps}${variant.steps2 != null ? '/' + variant.steps2 : ''} steps` : ''}
        </span>
      )}
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-1">
          {/*
           * Read the label, not variant.key: the technical identifier now contains the ENTIRE
           * prompt and is unhelpful as an accessible table name.
           */}
          <caption className="sr-only">
            Test grid{variant.prompt ? ` for prompt “${promptLabel(variant.prompt)}”` : ''}:
            rows = checkpoint, columns = strength
          </caption>
          <thead>
            <tr>
              <th scope="col" className="text-content-subtle text-[0.625rem] font-normal text-left px-1">ckpt \ strength</th>
              {gridCols.map((s) => (
                <th key={s} scope="col" className="text-content-muted text-[0.6875rem] tabular-nums px-1">{fmt(s)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {gridRows.map((row) => (
              <tr key={row.filename}>
                <th scope="row" className="text-content text-[0.6875rem] font-medium text-left px-1 whitespace-nowrap">{row.label}</th>
                {gridCols.map((s) => (
                  <ResultCell key={s} row={row} strength={s} variant={variant}
                    cellList={cellList} scoreMap={scoreMap} best={best} datasetId={datasetId}
                    thumbUrlFor={thumbUrlFor} onRate={onRate} onOpen={onOpen} fmt={fmt} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  ));
}
