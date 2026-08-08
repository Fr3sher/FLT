/**
 * 🏷️ The caption tags of the current SELECTION, as filter chips.
 *
 * Moved out of BankWorkspace.jsx by the Encre redesign. In structure B it has
 * ONE mount instead of two: it lives at the foot of the filter rail, with every
 * other way of narrowing the grid. The old screen mounted it twice — once in the
 * filter zone for phones, once as a sticky desktop inspector — and hid one of
 * them with `xl:hidden`. The rail is the responsive answer to the same problem,
 * so the duplicate mount is gone rather than carried over.
 *
 * The counting itself is unit-tested in bankTags.test.js; this file only renders.
 */
import { Chip, GroupLabel } from './BankAtoms.jsx'
import { selectionTagsNotes, tagCountLabel, tagFilterSummary } from './bankTags.js'

export default function SelectionTagsPanel({ tagRow, tagPicked, onToggle, onClear }) {
  return (
    <div className="space-y-1.5 rounded-lg border border-emerald-400/30 bg-emerald-500/5 px-2.5 py-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <GroupLabel>
          {tagRow.kind === 'image' ? `🏷️ Tags of ${tagRow.name}`
            : tagRow.size === 1 ? '🏷️ Tags of the selected image'
              : `🏷️ Tags across ${tagRow.size} selected images`}
        </GroupLabel>
        <span className="text-[11px] text-content-subtle">
          attributes you pick — unlike 🎯 Similar, which matches the look
        </span>
        {tagRow.frozen && (
          <span className="rounded border border-border px-1.5 text-[11px] text-content-subtle">
            held from the selection you filtered on
          </span>
        )}
        <button type="button" onClick={onClear}
          className="ml-auto rounded border border-border px-2 py-0.5 text-[11px] text-content-muted hover:text-content">
          ✕ Close
        </button>
      </div>
      {tagRow.rows.length === 0 ? (
        <p className="m-0 text-xs text-content-muted">
          {tagRow.uncaptioned > 0 && tagRow.counted === 0
            ? (tagRow.size === 1
              ? 'This image has no caption yet — run 🏷️ Caption and its tags appear here.'
              : `None of these ${tagRow.size} images has a caption yet — run 🏷️ Caption on them and their tags appear here.`)
            : 'No caption here has a word worth filtering on.'}
        </p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {tagRow.rows.map(({ tag, count }) => {
            const n = tagCountLabel(count, tagRow.counted)
            return (
              <Chip key={tag} active={tagPicked.has(tag)}
                onClick={() => onToggle(tag)}
                title={tagPicked.has(tag)
                  ? `Stop requiring “${tag}”`
                  : `Show only images whose caption mentions “${tag}”`
                    + (n ? ` — cited by ${count} of the ${tagRow.counted} captioned images you selected` : '')}>
                {tag}
                {n && <span className="ml-1 text-[10px] text-content-subtle">{n}</span>}
              </Chip>
            )
          })}
        </div>
      )}
      {selectionTagsNotes(tagRow, tagRow.unread).map((note) => (
        <p key={note} className="m-0 text-[11px] leading-snug text-content-subtle">{note}</p>
      ))}
      {tagPicked.size > 0 && (
        <p className="m-0 text-[11px] text-content-muted">
          {tagFilterSummary(tagPicked)} Matched as whole words, in captions and file names.
        </p>
      )}
    </div>
  )
}
