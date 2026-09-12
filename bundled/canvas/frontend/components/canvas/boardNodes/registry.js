import { externalLoraPayload } from '@lds/plugin-sdk/canvas';

export const normalizeLoraName = (s) =>
  String(s || '').replace(/\\/g, '/').trim().toLowerCase();

/* One entry per board-node type. `Card`/`AddFlow` are lazy loaders
   (`() => import(...)`) rather than direct component references: the real
   components live in JSX files (they render markup and pull in other JSX
   components like the LoRA combobox), and this module has to stay parseable
   by a bare `node --test` run with no JSX transform. A dynamic `import()`
   call is plain JS syntax — Node never has to parse the target file unless
   something actually invokes the loader, which the registry contract test
   never does. `BoardNodeLayer.jsx` (browser-only) resolves these with
   `React.lazy` + `Suspense`. */
export const BOARD_NODE_TYPES = {
  'external-lora': {
    type: 'external-lora',
    edge: { gradient: 'lds-edge-external', side: 'right' },
    payload: (nodes, checked) => ({ external_loras: externalLoraPayload(nodes, checked) }),
    Card: () => import('../ExternalLoraNodes.jsx').then((m) => ({ default: m.ExternalLoraCard })),
    AddFlow: () => import('../ExternalLoraNodes.jsx').then((m) => ({ default: m.ExternalLoraAddFlow })),
  },
};

export function nodeKey(type, node) {
  if (type === 'external-lora') return `ext:${normalizeLoraName(node?.filename)}`;
  return `${type}:${node?.id ?? ''}`;
}

export const knownType = (t) => Boolean(BOARD_NODE_TYPES[t]);
