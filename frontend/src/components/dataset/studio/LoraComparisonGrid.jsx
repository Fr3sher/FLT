// react-frontend/src/components/dataset/studio/LoraComparisonGrid.jsx
/**
 * Multi-LoRA comparison grid: one COLUMN per lora_label and one ROW per strength. Each
 * LoRA/strength cell stacks one reusable, votable ResultTile per seed. Single-LoRA
 * checkpoint/strength grids belong to ResultsArea; this view compares multiple LoRAs side by side.
 */
import { useMemo } from 'react';
import { fmt } from '../../../utils/studioFormat';
import ResultTile from './ResultTile';

export default function LoraComparisonGrid({ loras, cells, onRate, onOpen }) {
  // Index cells by dataset_id | strength, with tiles sorted by seed.
  const byKey = useMemo(() => {
    const m = new Map();
    for (const c of cells || []) {
      const k = `${c.dataset_id}|${c.strength}`;
      if (!m.has(k)) m.set(k, []);
      m.get(k).push(c);
    }
    for (const arr of m.values()) arr.sort((a, b) => (a.seed || 0) - (b.seed || 0));
    return m;
  }, [cells]);

  // Rows are available strengths in ascending order; LoRA columns preserve payload order.
  const strengths = useMemo(() => {
    const set = new Set((cells || []).map((c) => c.strength));
    return [...set].sort((a, b) => a - b);
  }, [cells]);

  if (!loras?.length || strengths.length === 0) return null;

  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-1">
        <caption className="sr-only">
          Multi-LoRA comparison: columns = LoRA, rows = strength
        </caption>
        <thead>
          <tr>
            <th scope="col" className="text-content-subtle text-[0.625rem] font-normal text-left px-1">
              strength \ LoRA
            </th>
            {loras.map((l) => (
              <th key={l.dataset_id} scope="col"
                className="text-content text-[0.6875rem] font-semibold px-1 max-w-[160px] truncate"
                title={`${l.lora_label} — ${l.dataset_name || ''}`}>
                {l.lora_label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {strengths.map((s) => (
            <tr key={s}>
              <th scope="row" className="text-content-muted text-[0.6875rem] tabular-nums text-left px-1 whitespace-nowrap">
                {fmt(s)}
              </th>
              {loras.map((l) => {
                const list = byKey.get(`${l.dataset_id}|${s}`) || [];
                return (
                  <td key={l.dataset_id} className="align-top p-1">
                    {list.length === 0 ? (
                      <span className="text-content-subtle text-[0.625rem]">—</span>
                    ) : (
                      <div className="flex items-start gap-1 flex-wrap">
                        {list.map((c) => (
                          <ResultTile key={c.id} cell={c}
                            row={{ label: l.lora_label }} strength={s}
                            variant={{ aspect: c.aspect || '' }}
                            datasetId={c.dataset_id} onRate={onRate} onOpen={onOpen} fmt={fmt} />
                        ))}
                      </div>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
