/* Server-owned continuation: the browser shows and controls one session;
 * it never starts the next clip from a poll or a React effect. */
export const autoContinueUrl = (action = '') => `/api/video-studio/auto-continue${action ? `/${action}` : ''}`;

// The continuation pipeline takes a last frame and FL2V settings. A reference
// clip or reference dials cannot silently become a different model on Start.
export function canAutoContinue(clip, mode = 'i2v') {
  return clip?.status === 'done' && clip.mode !== 'ref2va' && mode !== 'ref2va';
}

export function autoIsBusy(session) {
  return !!session && (!!session.enabled || !!session.draining
    || ['extracting', 'writing', 'generating'].includes(session.phase));
}

export function autoPhaseLabel(session) {
  if (!session) return 'Choose Auto beside a finished clip to start.';
  const next = (Number(session.completed) || 0) + 1;
  if (session.can_abandon) return 'The previous step was interrupted. Stop Auto to end this session and keep any available clip.';
  if (session.draining || (!session.enabled && session.phase === 'generating')) {
    return 'Finishing the current clip — no next clip will be started.';
  }
  switch (session.phase) {
    case 'extracting': return `Clip ${next} · Taking the last frame`;
    case 'writing': return `Clip ${next} · Analysing the frame and writing the next motion`;
    case 'generating': return `Clip ${next} · Generating`;
    case 'paused': return 'Paused — resolve the problem, then Resume; or Stop Auto to end this take.';
    case 'stopped': return 'Auto is off.';
    case 'complete': return 'The clip limit has been reached.';
    default: return 'Waiting for the next step…';
  }
}

export function autoLimit(value) {
  if (value === null || value === undefined || String(value).trim() === '') return null;
  const n = Number(value);
  return Number.isSafeInteger(n) && n >= 0 && n <= 10000 ? n : null;
}

export function autoStateKey(session) {
  return session ? [session.id, session.current_clip_id, session.phase, session.completed,
    session.enabled, session.draining].join(':') : '';
}
