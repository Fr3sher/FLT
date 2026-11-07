import { DenseBasePicker, FullTransformerAdvancedRecipe } from './FullTransformerRecipe';
import { denseQuantizeTarget } from '../lib/trainingModel.js';
import { looksAbsoluteBase } from '../lib/trainingFamily.js';
export default function DenseRecipePanel({ variant, setVariant, base, setBase, customBase, setCustomBase,
  currentBases, customSupported, baseNote, denseBaseSummary, trainingModeBusy, stepsOverride, setStepsOverride,
  adv, saveAdv, samplePromptsText, setSamplePromptsText, saveSamplePrompts, advSampleDefault,
  advMaxPrompts, datasetImages, applySamplePrompts, cloudLastHere, cloudActiveHere }) {
  const quantizeTarget = denseQuantizeTarget(cloudLastHere || {});
  return (<>
            {/* DENSE_BASE_PICKER_START — the control the owner could not find.
                Its markup lives in the DenseBasePicker component above so a
                test can execute it; what has to stay HERE is the fact that the
                full-model arm renders it at all. */}
            <DenseBasePicker
              variant={variant} setVariant={setVariant}
              base={base} setBase={setBase}
              customBase={customBase} setCustomBase={setCustomBase}
              currentBases={currentBases} customSupported={customSupported}
              baseNote={baseNote} baseSummary={denseBaseSummary}
              busy={trainingModeBusy} />
            {/* DENSE_BASE_PICKER_END */}
            <FullTransformerAdvancedRecipe
              stepsOverride={stepsOverride}
              setStepsOverride={setStepsOverride}
              adv={adv} saveAdv={saveAdv}
              samplePromptsText={samplePromptsText}
              setSamplePromptsText={setSamplePromptsText}
              saveSamplePrompts={saveSamplePrompts}
              samplePromptsDefault={advSampleDefault}
              maxSamplePrompts={advMaxPrompts}
              datasetImages={datasetImages}
              applySamplePrompts={applySamplePrompts}
              quantizeTarget={quantizeTarget}
              suggestedQuantizePath={looksAbsoluteBase(base) ? String(base).trim() : ''}
              baseSummary={denseBaseSummary}
              disabled={trainingModeBusy || cloudActiveHere} />
  </>);
}
