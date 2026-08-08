# Multi-engine Bank search with rank fusion — design

Date: 2026-08-08
Status: approved; slices 0 and 2 landed; slice 1 (measurement gate) not run.

## Why

Bank semantic search runs on SigLIP 2, trained on WebLI. WebLI applies a
pornographic image filter and an unsafe-text filter *before* training. The model
was never shown explicit concepts, so it cannot retrieve them — not by refusal,
but by absence. LDS is used heavily to triage NSFW datasets. Our newest search
engine is structurally blind to our most common use case.

The incumbent `ViT-L-14/openai` has the opposite profile: an older, weaker model
overall, but trained on a loosely filtered corpus. LAION's NSFW classifier takes
CLIP ViT-L/14 embeddings as input and works — proof that this embedding space
does separate explicit content.

Rather than pick a winner, give each model the job it is best at and fuse the
results. SigLIP 2 keeps fine-grained and multilingual semantics; a LAION-2B model
covers unfiltered and niche concepts; the fusion covers each one's blind spot.

Note on model choice: the highest-scoring open CLIP models of this generation
(DataComp-XL, 79.2% IN top-1) earn their gains by *filtering harder* — DataComp
is literally the output of a data-filtering network. On the axis that matters
here, ImageNet rank and corpus breadth are anti-correlated. LAION-2B is the
lineage that scales by size rather than by curation.

## What already exists (verified in code)

| Capability | Location |
|---|---|
| Engine registry with aliases, per-engine `model_key`/`dimension` | `backend/app/services/bank_semantic_engine.py:35-51` |
| Cache rejected on `model_key`/`dimension` mismatch | `backend/app/services/bank_semantic_engine.py:237` |
| SigLIP 2 pin (`google/siglip2-base-patch16-224`, dim 768) | `backend/app/services/bank_semantic_models.py:14-17` |
| SigLIP 2 indexing pass (atomic npz, resume, cancel) | `backend/infer/bank_semantic_infer.py` |
| CLIP text tower warm worker, pinned by module constants | `backend/infer/clip_text_infer.py:50-51` |
| CLIP image tower warm worker, pinned by module constants | `backend/infer/clip_image_embed_infer.py:51-52` |
| Score pass: one CLIP forward → aesthetic + NSFW + style embedding | `backend/infer/bank_score_infer.py` |
| Three-call-site model contract test | `backend/tests/test_clip_text_model_contract.py` |

## Hard constraint discovered during design

`bank_score_infer.py` runs the LAION improved-aesthetic MLP
(`sac+logos+ava1-l14-linearMSE.pth`, line 69) directly on the CLIP embedding
(`aes_head(emb)`, line 559). The `l14` in that filename means ViT-L/14 **OpenAI**
specifically — the MLP was trained on that exact embedding space.

`ViT-L-14/datacomp_xl` also outputs 768-d. Swapping only the `PRETRAINED`
constant therefore does **not** raise: the head runs, returns a plausible float,
and every aesthetic score in the Bank silently becomes noise.

The existing contract test does not catch this. It asserts the three CLIP
call-sites agree *with each other*, which stays true when all three are changed
together to a model that breaks the head.

Consequence: `ViT-L-14/openai` stays, pinned, serving the aesthetic head. It is
removed from search duty, not from the app. Concretely, the existing CLIP-L
engine stays registered and keeps answering searches on installs that already
have its cache (`bank_semantic_engine.py:35-51`, aliases `clip`/`open-clip`/
`score`) — what it is removed from is being the engine we invest in improving;
its constants stay pinned for the aesthetic head instead.

The NSFW score is unaffected — it uses `Marqo/nsfw-image-detection-384` on the
PIL image (lines 561-564), not the CLIP embedding.

## Why fusion cannot happen in vector space

`clip_image_embed_infer.py:20-22` already states the invariant: vectors from
different CLIP configurations are not comparable — the dot product still returns
a number, and that number is meaningless. Concatenating, averaging, or comparing
a SigLIP 2 score against a LAION score is invalid; the scales, distributions and
temperatures are unrelated.

Unification therefore lives *above* the scores. Reciprocal Rank Fusion combines
`Σ 1/(k + rank)` across engines, using only positions. Each engine compares its
own vectors against its own cache; only ranks cross the boundary.

RRF also degrades for free: fusing a single ranked list returns that list
unchanged, since `1/(k + rank)` is strictly decreasing in rank. An install that
never indexed LAION gets exactly today's results, through the same code path,
with no conditional branch. The degraded case is the general case at n=1.

## Architecture

```
NEW  backend/app/services/bank_search_fusion.py
     RRF over ranked lists. No torch, no I/O, unit-testable without a GPU.

NEW  backend/app/services/bank_semantic_laion_models.py
     MODEL_NAME='ViT-H-14', PRETRAINED='laion2b_s32b_b79k', DIMENSION=1024,
     MODEL_KEY='clip-vit-h-14-laion2b@<short HF revision>'
     The revision is resolved and hard-pinned during slice 4, the same way
     bank_semantic_models.py pins 75de2d55. It is not left floating.

NEW  backend/infer/laion_semantic_infer.py
     Bank indexing pass, mirroring bank_semantic_infer.py but via open_clip.

MOD  bank_semantic_engine.py       third engine in _ENGINE_ALIASES
MOD  clip_text_infer.py            --model/--pretrained, defaults UNCHANGED
MOD  clip_image_embed_infer.py     --model/--pretrained, defaults UNCHANGED
```

Parameterising `clip_image_embed_infer.py` is also where its module docstring's
"THE MODEL SPEC IS A CONTRACT, NOT A CHOICE" warning has to be rewritten: once
the defaults become overridable, that warning would mislead every later reader
into believing the constants can never change, while the strengthened
defaults-only contract test quietly passes around it. Rewriting it is part of
slice 3's scope, not a follow-up.

Workers are parameterised rather than duplicated. A caller passing nothing gets
today's behaviour bit-for-bit. This keeps a single execution path: duplicated
workers would diverge at the first fix applied to one side only, with nothing to
signal it.

### Search flow

```
query text
  ├─→ SigLIP 2   ─ cache ready? → encode → cosine → top-N ranked ─┐
  ├─→ LAION H/14 ─ cache ready? → encode → cosine → top-N ranked ─┤
  └─→ CLIP-L     ─ cache ready? → …                               ─┤
                                                                   ▼
                                                    bank_search_fusion.rrf()
                                                                   │
                                                     final list + provenance
```

## Caches

| File | model_key | dim |
|---|---|---|
| `semantic_siglip2_cache.npz` | `siglip2-base-p16-224@75de2d55` | 768 |
| `semantic_laion_cache.npz` | `clip-vit-h-14-laion2b@<rev>` | 1024 |

The differing dimension is deliberate. A mislabelled 768-d cache could load
silently and produce wrong results; 1024 fails immediately at the first matmul.
This is also why `ViT-L-14/laion2b` was rejected as the second engine — same
dimension as the incumbent, therefore silently interchangeable.

The indexing pass follows the existing pass contract: atomic writes via
`npz_atomic`, resume from a partial cache, cancel sentinel, `.count` sidecar for
an honest "N indexed (M remaining)" after a Stop. It shares the existing GPU
queue with scoring and captioning; it must not bypass that fence.

`capabilities.py` gets a `bank_laion` entry listing *every* import the worker
performs (`torch, open_clip, numpy, PIL`). A partial list turns the probe green
on installs where the pass will fail. Setup announces the ~4 GB download before
starting it.

## Error handling

| Condition | Behaviour |
|---|---|
| LAION cache absent | Search = SigLIP 2 alone, identical to today. Not an error. |
| Cache present, engine fails | Return other engines' results **and report which engine did not answer** |
| `dimension` / `model_key` mismatch | Hard refusal naming expected vs found model |
| No engine ready | Existing error path, unchanged |

Row 2 is the one that matters. An engine that was deliberately indexed and then
fails is information for the user, not something to absorb silently.

## Testing

New guard for the pre-existing gap, declared next to the checkpoint URL so it is
visible at the point of risk:

```python
_AESTHETIC_URL = '.../sac+logos+ava1-l14-linearMSE.pth'
# This MLP was trained on embeddings from THIS exact pair. It accepts any 768-d
# vector without complaint and returns a wrong number.
_AESTHETIC_EXPECTS = ('ViT-L-14', 'openai')
```

The test is written red-first: flip `PRETRAINED` to `laion2b_s32b_b79k`, confirm
failure, revert. A test that cannot go red manufactures confidence without
guaranteeing anything.

| Test | What it prevents |
|---|---|
| Aesthetic head pin matches score-pass model | Silently wrong aesthetic scores |
| RRF: single list → identical order | Fusion changing results on single-index installs |
| RRF: fusion maths, deterministic ties | Rankings that vary between calls |
| Contract: **defaults** of the three call-sites agree | A worker drifting once parameterised |
| Wrong-dimension cache → hard refusal | A LAION npz read as a SigLIP 2 npz |
| Failing engine → results + report | Silent skip |

### Acceptance criterion (not a unit test)

Real-data probe: ~200 images from an already-captioned bank, ~15 queries split
between SFW and explicit, recall@10 measured for SigLIP 2 alone, LAION alone, and
the fusion, with captions as ground truth.

**This measurement decides whether we ship.** If the fusion does not beat SigLIP 2
alone on explicit queries, the WebLI reasoning is right on paper and wrong in
practice, and we would have added 4 GB and an indexing pass for nothing.

## Out of scope

- **Replacing the aesthetic head.** `ViT-L-14/openai` stays in the app for it.
- **Style clustering.** Not migrated, not fixed. `_cluster_style`
  (`bank_score_infer.py:262`) is single-link union-find: cosine ≥ threshold then
  transitive merge, so a single chain of near-neighbours collapses a homogeneous
  bank into one bucket. That is an algorithmic defect — a better embedding makes the
  chains more reliable and can accelerate the collapse. Separate work.
- **Changing the default engine.** No engine is added to an install automatically:
  the LAION model is downloaded and its cache built only when the user explicitly
  starts that indexing pass. Until then RRF runs at n=1 and existing installs
  behave exactly as today.
- **bigG/14.** ~10 GB, 1280-d, unusable on much of the install base.
- **Fine-tuning our own CLIP** on captioned banks. The real long-term answer to
  the NSFW retrieval gap, and a different project.

## Delivery order

| # | Slice | Depends on | Rationale |
|---|---|---|---|
| 0 | Aesthetic head guard (`_AESTHETIC_EXPECTS` + red-first test) | — | Fixes an existing gap, independent of everything else |
| 1 | Real-data probe | — | **Decides** whether slices 3-5 are worth building |
| 2 | RRF module + pure tests | — | No GPU, no model; valid even if slice 1 says no |
| 3 | Parameterised workers + strengthened contract test | 1 (gate) | |
| 4 | LAION engine + indexing pass + capability probe | 3 | The only expensive slice |
| 5 | UI wiring + provenance display | 4 | |

Slices 0 and 2 are unconditional. Slice 1 is a decision point, not a step: if the
probe disproves the WebLI hypothesis, we stop having spent half a day rather than
after wiring an engine, an indexing pass and a UI.

## Sources

- open_clip pretrained tags — https://github.com/mlfoundations/open_clip/blob/main/docs/PRETRAINED.md
- SigLIP 2 (WebLI filtering) — https://arxiv.org/html/2502.14786v1
- LAION-5B (optional NSFW tagging, CLIP ViT-L/14 classifier) — https://arxiv.org/pdf/2210.08402
- CLIP-filtering excludes marginal content in DataComp — https://dl.acm.org/doi/fullHtml/10.1145/3689904.3694702
- ViT-bigG/14 at 80.1% — https://laion.ai/blog/giant-openclip/
