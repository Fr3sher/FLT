// Launch test button, disabled until RunSetupPanel's canLaunch is true. Extracted unchanged from
// LoraTestStudio.jsx. Canvas supplies label/title to explain what will happen, such as deploying
// two checkpoints before generating, or why launch is blocked, such as mixed families. Without
// overrides, preserve the existing label.
export default function LaunchBar({ canLaunch, onLaunch, label = null, title = null }) {
  return (
    <button type="button" disabled={!canLaunch} onClick={onLaunch} title={title || undefined}
      className="ml-auto min-w-0 px-3 py-1.5 rounded-lg bg-gradient-primary text-gray-950 text-sm font-semibold disabled:opacity-40">
      <span aria-hidden>🚀</span> <span className="break-words">{label || 'Run test'}</span>
    </button>
  );
}
