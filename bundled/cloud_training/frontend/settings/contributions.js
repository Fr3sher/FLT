// The Cloud product keeps rental, delivery and local staging preferences together.
// Legacy section/placement ids remain available for saved deep links.
export const cloudSettingsSlots = {
  'settings.group': [
    { id: 'cloud', section: 'training', after: 'defaults',
      title: 'Cloud training (vast.ai)', icon: 'cloud',
      blurb: 'The API key and training guardrails on spend and stalls.',
      keywords: ['cloud', 'vast', 'budget', 'price', 'stall', 'gpu',
        'verified host', 'secure cloud', 'community cloud', 'offer filter', 'hf cloud token'],
      panel: () => import('./CloudTrainingGroup.jsx') },
    { id: 'cloud-location', section: 'storage', placement: 'locations',
      title: 'Run staging folder', blurb: 'Where Cloud keeps datasets, logs and samples for each run.',
      keywords: ['cloud runs', 'staging'],
      panel: () => import('./CloudStorageLocation.jsx') },
    { id: 'cloud-housekeeping', section: 'storage', placement: 'housekeeping',
      title: 'Clean up run staging', blurb: 'Review and remove local Cloud run folders that no run uses.',
      keywords: ['cloud runs', 'orphan', 'staging', 'cleanup'],
      panel: () => import('./CloudRunHousekeeping.jsx') },
    { id: 'cloud-storage', section: 'storage', placement: 'models',
      title: 'Model delivery and Hub storage', blurb: 'Choose full-model delivery and manage Hugging Face quota and caches.',
      keywords: ['hugging face', 'hf', 'quota', 'cloud', 'custom base'],
      panel: () => import('./HfStorageCard.jsx') },
  ],
  'setup.card': [
    { id: 'cloud-signup', placement: 'training',
      panel: () => import('../setup/CloudSignupNote.jsx') },
  ],
}
