# API 1.22 — dataset creation and video imports

The Datasets **New dataset** form renders `datasets.create` contributions on
the `datasets` surface. Each contribution supplies `{ id, label, panel }`.
The panel creates its own dataset and navigates to its workspace; the existing
image creation form remains available as **Images**.

`sources.panel` also supports `videoDataset`. Its host passes `datasetId`,
`busy`, `sliceLong` and `onDone`. The video owner provides the import API;
source providers remain optional and file upload works without them.

New contributions require `compatibility.api: ">=1.22,<2"`. Existing slots,
routes and image dataset creation are unchanged.
