import test from 'node:test';
import assert from 'node:assert/strict';
import {
  KLEIN_STEPS_MAX, KLEIN_STEPS_MIN, clampKleinSteps, kleinDialPayload, kleinStepsDescription,
} from './kleinDials.js';

/* 🖥️ Klein sampler steps, in the run panel.

   `klein.generation_steps` existed as a Settings field only, while the Krea
   panel carried its own steps slider inches away on the same screen. The value
   that decides how long every Klein shot renders for was the one you had to
   leave the page to change. Same key, same endpoint, one value — exactly the
   contract the Krea dials already state on screen. */

test('the shipped range is the one the backend accepts', () => {
  assert.equal(KLEIN_STEPS_MIN, 1);
  assert.equal(KLEIN_STEPS_MAX, 50);
});

test('a value out of range, or junk, lands on something the graph can run', () => {
  assert.equal(clampKleinSteps(0, 5), 1);
  assert.equal(clampKleinSteps(999, 5), 50);
  assert.equal(clampKleinSteps(7.6, 5), 8);          // steps are whole numbers
  // Junk falls back to the shipped default, and junk DEFAULTS fall back to 5 —
  // klein.generation_steps' own shipped value, so a backend too old to publish
  // config_defaults still lands where the graph actually runs.
  assert.equal(clampKleinSteps('nope', 5), 5);
  assert.equal(clampKleinSteps(undefined, undefined), 5);
});

test('the number is never shown bare — it says what it costs', () => {
  // A step count means nothing on its own: 5 is the shipped value, and the only
  // thing a user needs told is that raising it costs time proportionally.
  assert.match(kleinStepsDescription(5), /5/);
  assert.match(kleinStepsDescription(5), /shipped|default/i);
  assert.match(kleinStepsDescription(20), /slower|longer|wait/i);
});

test('the write is a partial that touches nothing else', () => {
  // The endpoint deep-merges: naming only this key is what keeps the model file,
  // the consistency LoRA and the preset out of a slider drag's blast radius.
  assert.deepEqual(kleinDialPayload({ generation_steps: 12 }),
    { config: { klein: { generation_steps: 12 } } });
});
