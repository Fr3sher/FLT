import { Card, TextField } from '@lds/plugin-sdk/ui';
import Fp8QuantizeTool from './Fp8QuantizeTool.jsx';
import ModelRuntimeCard from './ModelRuntimeCard.jsx';

/** The body of the Model tools settings group.
 *
 *  The SAME component the full-model recipe card and the dense cards render —
 *  imported, not copied, so the refusals (already quantized, LoRA, overwriting
 *  the source) and the read-back verification can never differ between the
 *  doors. It is here because its other doors sit inside a dense dataset,
 *  which somebody who downloaded a 26 GB model from Hugging Face and has no
 *  dataset at all never opens — and "this file is too big" is a disk question,
 *  asked on this tab. `framed={false}` drops the tool's own accent box and
 *  title: the Card already says both. The Card's id is the help registry's
 *  focus target for the `storage.fp8_quantize` topic. */
export default function StorageQuantizeGroup({ config, setField }) {
  return (
    <Card id="storage-fp8-quantize" title="Quantize an existing model to fp8"
      help="A full-precision model — downloaded from Hugging Face, or delivered by a full-model run — is about 2.5× the size ComfyUI needs to generate with it. Point this at one and it writes the ~10 GB fp8 version next to the original, on this machine, without ever modifying the source.">
      <ModelRuntimeCard />
      <Fp8QuantizeTool framed={false} />
      <details className="rounded-lg border border-border p-3">
        <summary className="min-h-10 cursor-pointer text-sm font-medium text-content">Advanced Python override</summary>
        <TextField id="quantize-python" label="Python interpreter override" value={config?.quantize?.python}
          onChange={(value) => setField('quantize', 'python', value)} placeholder="Automatic — Model tools CPU engine"
          help="Leave blank to use this plugin’s managed CPU engine. Override only with an existing Python interpreter that provides torch. Installing the managed engine does not change your override. Save changes, then check the engine again." />
      </details>
    </Card>
  );
}
