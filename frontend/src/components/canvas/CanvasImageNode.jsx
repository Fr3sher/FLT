import { nudgeImageNode } from '../../utils/canvasImageNodes';
import { imageFactsLine } from '../../utils/generatedImageFacts';

/* 🖼 One generated image, pinned ON the board.

   The board compares checkpoints and the thing being compared is the picture —
   so a picture that can only be seen one at a time, in a modal, cannot be
   compared at all. Pinned, it becomes a node like any other: draggable,
   resizable, joined by an edge to the checkpoint pill that produced it (that
   edge is drawn by the lane, with the SAME connector a continuation uses — see
   utils/canvasImageNodes.imageNodeEdges).

   Closing is a ✕ on the node and it does NOT forget anything: the geometry is
   kept and re-opening the same image from its gallery puts it back exactly
   here, at exactly this size. That is the feature; the storage side of it is
   `visible: false` on the canvas_image_node row.

   ⚠️ Touch. Dragging a node and panning the board are the same physical
   gesture, and this file inherits the board's answer to that (LineageCanvas):
   with a mouse the press hit-tests onto the node and moves it; with a finger
   the board pans until a LONG PRESS picks the node up. The resize corner is the
   exception — it is hit-tested first on any pointer type, because a finger that
   lands on a 28-px corner handle can only mean one thing.

   ⌨ Keyboard. The node itself is focusable: arrows move it, Shift+arrows move
   it faster, +/− resize it, Esc closes it. Moving and resizing by mouse alone
   would put the whole feature out of reach of anyone who does not use one. The
   arithmetic is nudgeImageNode(), unit-tested; this file only routes keys. */

export default function CanvasImageNode({ node, datasetId, laneName, onGeometry,
  onClose, onOpen }) {
  const img = node.image || {};
  const stepLabel = img.step == null ? 'step unknown' : `step ${img.step}`;
  const facts = imageFactsLine(img);

  const onKeyDown = (e) => {
    if (e.key === 'Escape') { e.stopPropagation(); onClose?.(node); return; }
    const next = nudgeImageNode(node, e.key, e.shiftKey);
    if (!next) return;                    // never swallow a key we do not handle
    e.preventDefault();
    e.stopPropagation();
    onGeometry?.(node, next);
  };

  return (
    <div
      // The hit-test handles. The frame's pointer handlers read the dataset and
      // the image off these rather than every node carrying its own listeners —
      // the same arrangement the run cards use (data-canvas-node).
      data-canvas-image=""
      data-dataset-id={datasetId}
      data-image-id={node.imageId}
      role="group"
      tabIndex={0}
      onKeyDown={onKeyDown}
      aria-label={`Pinned image from ${laneName || 'this dataset'}, ${stepLabel}. `
        + 'Arrow keys move it, plus and minus resize it, Escape closes it.'}
      title={`${stepLabel} · ${facts}`}
      style={{ position: 'absolute', left: node.x, top: node.y,
        width: node.w, height: node.h }}
      className="lds-canvas-image group flex flex-col overflow-hidden rounded-lg border border-indigo-400/40 bg-surface-overlay shadow-lg
                 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
      <header className="flex shrink-0 items-center gap-1 border-b border-border bg-app/70 px-1.5 py-0.5">
        <span className="min-w-0 flex-1 truncate text-content-muted text-[0.5625rem] font-semibold tabular-nums">
          {stepLabel}
        </span>
        {/* Opens the full record — every setting, the prompt, the copy buttons.
            The node is the picture; the facts stay one click away rather than
            being crammed onto a thumbnail. */}
        <button type="button" onClick={(e) => { e.stopPropagation(); onOpen?.(node); }}
          title="Open this image full-screen with all its settings"
          aria-label={`Open ${stepLabel} full-screen`}
          className="shrink-0 rounded px-1 text-content-subtle text-[0.625rem] leading-none hover:text-content">🔍</button>
        {/* ✕ closes the node and REMEMBERS where it was. Re-pinning the same
            image from its gallery brings it back here, this size. */}
        <button type="button" onClick={(e) => { e.stopPropagation(); onClose?.(node); }}
          data-testid="canvas-image-close"
          title="Close this image — re-opening it from its gallery puts it back here, at this size"
          aria-label={`Close the pinned image at ${stepLabel}`}
          className="shrink-0 rounded px-1 text-content-subtle text-[0.75rem] leading-none hover:text-content">✕</button>
      </header>
      <div className="relative min-h-0 flex-1 bg-black/30">
        <img src={img.url} alt={`Generated at ${stepLabel}`} draggable={false}
          className="h-full w-full select-none object-contain" />
      </div>
      {/* The resize corner. 28 px on purpose — a hairline handle is a desktop-only
          affordance, and this board is used on a phone. Hit-tested BEFORE the
          drag/pan decision, so a finger landing here always resizes. */}
      <span data-canvas-image-resize="" aria-hidden
        title="Drag to resize"
        style={{ position: 'absolute', right: 0, bottom: 0, width: 28, height: 28 }}
        className="cursor-nwse-resize touch-none rounded-tl-md border-l border-t border-indigo-400/40 bg-app/80 text-content-subtle after:absolute after:bottom-1 after:right-1 after:text-[0.625rem] after:content-['◢']" />
    </div>
  );
}
