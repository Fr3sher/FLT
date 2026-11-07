// An install receipt describes what was repaired, not whether CUDA can compute.
export function installRuntimeNotice(notice) {
  if (!notice?.managed_installed || !['scoring', 'semantic'].includes(notice.profile)) return null
  const external = !notice.uses_managed
  const importFailed = notice.selected_imports_ok === false
  const selectionFailed = notice.selection_failed === true
  return {
    profile: notice.profile,
    managedPython: notice.managed_python,
    effectivePython: notice.effective_python,
    warn: external || selectionFailed,
    title: 'Managed environment installed / repaired',
    detail: selectionFailed
      ? 'The environment was repaired, but its Python could not be selected. Open the Python picker to choose it.'
      : external
        ? `The selected external Python was kept unchanged.${importFailed ? ' Its import check failed.' : ''} To use the repaired environment, choose the managed Python below.`
        : 'This pass uses the managed Python. Imports passed; calculation has not been tested.',
    validation: external && !selectionFailed
      ? importFailed
        ? 'The managed Python passed its import check. No calculation was tested.'
        : 'Both Python environments passed their import checks. No calculation was tested.'
      : '',
    errorIsSelection: external && importFailed && !selectionFailed,
  }
}

export function installCompletion(state, notice) {
  const result = installRuntimeNotice(notice)
  if (state === 'success') {
    return result
      ? { tone: result.warn ? 'info' : 'success', message: result.warn
        ? 'Managed environment repaired. The selected external Python is unchanged.'
        : 'Managed environment installed. Imports checked; calculation not tested.' }
      : { tone: 'success', message: 'Installed.' }
  }
  if (state === 'error') {
    return result?.errorIsSelection
      ? { tone: 'error', message: 'Managed environment repaired. Choose a Python: the selected external one failed its import check.' }
      : { tone: 'error', message: 'Install failed — click to try again.' }
  }
  return null
}
