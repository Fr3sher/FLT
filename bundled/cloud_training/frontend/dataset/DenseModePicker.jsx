import { TRAINING_MODE_FULL_TRANSFORMER, TRAINING_MODE_LORA } from '../lib/trainingModel.js';
export default function DenseModePicker({ fullMode, fullTransformerEligible, fullTransformerReason,
  trainingModeError, trainingModeBusy, trainingModeRadioRefs, onTrainingModeKeyDown,
  onTrainingModeChange, denseBaseSummary }) {
  return (<>        <div role="radiogroup" aria-label="Training mode"
          aria-describedby={[
            !fullTransformerEligible ? 'full-transformer-disabled-reason' : '',
            trainingModeError ? 'training-mode-save-error' : '',
          ].filter(Boolean).join(' ') || undefined}
          className="inline-flex max-w-full rounded-lg border border-border bg-app/50 p-0.5">
          <button type="button" role="radio" aria-checked={!fullMode}
            ref={(node) => { trainingModeRadioRefs.current[TRAINING_MODE_LORA] = node; }}
            tabIndex={!fullMode || !fullTransformerEligible ? 0 : -1}
            disabled={trainingModeBusy}
            aria-describedby={trainingModeError ? 'training-mode-save-error' : undefined}
            onKeyDown={onTrainingModeKeyDown}
            onClick={() => onTrainingModeChange(TRAINING_MODE_LORA)}
            className={`px-2.5 py-1 rounded-md text-[0.75rem] font-semibold transition-colors disabled:opacity-50 ${
              !fullMode ? 'bg-indigo-500/25 text-indigo-100' : 'text-content-muted hover:text-content'}`}>
            LoRA
          </button>
          <button type="button" role="radio" aria-checked={fullMode}
            ref={(node) => { trainingModeRadioRefs.current[TRAINING_MODE_FULL_TRANSFORMER] = node; }}
            tabIndex={fullMode && fullTransformerEligible ? 0 : -1}
            disabled={trainingModeBusy || !fullTransformerEligible}
            aria-describedby={[
              !fullTransformerEligible ? 'full-transformer-disabled-reason' : '',
              trainingModeError ? 'training-mode-save-error' : '',
            ].filter(Boolean).join(' ') || undefined}
            onKeyDown={onTrainingModeKeyDown}
            onClick={() => onTrainingModeChange(TRAINING_MODE_FULL_TRANSFORMER)}
            title={fullTransformerReason || `Experimental · ${denseBaseSummary} · cloud-only`}
            className={`px-2.5 py-1 rounded-md text-[0.75rem] font-semibold transition-colors disabled:opacity-40 ${
              fullMode ? 'bg-sky-500/25 text-sky-100' : 'text-content-muted hover:text-content'}`}>
            Full model
          </button>
        </div>
        {!fullTransformerEligible && (
          <span id="full-transformer-disabled-reason"
            className="basis-full text-amber-300 text-[0.6875rem] leading-relaxed">
            Full model unavailable: {fullTransformerReason}
          </span>
        )}
  </>);
}
