import test from 'node:test';
import assert from 'node:assert/strict';
import { failureView, GENERIC_CAUSES } from './trainingFailure.js';

const EXCERPT = { kind: 'traceback', text: 'GatedRepoError: 401', headline: 'GatedRepoError: 401' };

const GATED_401 = {
  status: 401,
  repo: 'krea/Krea-2-Turbo',
  url: 'https://huggingface.co/krea/Krea-2-Turbo',
  title: 'Hugging Face saw no valid token — this is not a licence problem',
  message: 'The download of krea/Krea-2-Turbo was refused as NOT AUTHENTICATED (HTTP 401).',
};

test('a gated-repo verdict is surfaced as the cause', () => {
  const view = failureView({ rc: 1, excerpt: EXCERPT, hf_gated: GATED_401 });
  assert.equal(view.hfGated.status, 401);
  assert.ok(view.hfGated.message.includes('NOT AUTHENTICATED'));
});

test('a proven cause replaces the generic guesswork list', () => {
  // Reported by SurpassHR (GitHub): the generic list says "the base model needs
  // a Hugging Face token" for EVERY crash, which is noise once we know exactly.
  const withGate = failureView({ rc: 1, excerpt: EXCERPT, hf_gated: GATED_401 });
  assert.equal(withGate.causes, '');
  const without = failureView({ rc: 1, excerpt: EXCERPT });
  assert.equal(without.causes, GENERIC_CAUSES);
  assert.equal(without.hfGated, null);
});

test('a payload predating the verdict still renders (no crash, no invention)', () => {
  const view = failureView({ rc: 1, log_tail: 'boom' });
  assert.equal(view.hfGated, null);
  assert.equal(view.causes, GENERIC_CAUSES);
});

test('an empty gated payload is ignored rather than shown blank', () => {
  const view = failureView({ rc: 1, excerpt: EXCERPT, hf_gated: { status: 401 } });
  assert.equal(view.hfGated, null);
  assert.equal(view.causes, GENERIC_CAUSES);
});
