import test from 'node:test';
import assert from 'node:assert/strict';
import {
  STEPS_RECIPE_BURST_MS, stepsRecipeRefreshDelay,
} from './stepsRecipeRefresh.js';

test('a hidden Training section never costs a server call', () => {
  // Curation changes keptCount from 6 to 48 while the grid is visible.
  assert.equal(stepsRecipeRefreshDelay(false, { n_images: 6 }, 48), null);
  assert.equal(stepsRecipeRefreshDelay(false, null, 48), null);
});

test('first load and recipe changes fetch immediately', () => {
  assert.equal(stepsRecipeRefreshDelay(true, null, 48), 0);
  assert.equal(stepsRecipeRefreshDelay(true, undefined, 48), 0);
  // An unchanged image count means the recipe changed, not curation.
  assert.equal(stepsRecipeRefreshDelay(true, { n_images: 48, steps: 3500 }, 48), 0);
});

test('a kept count that moved is refetched, regrouped not per image', () => {
  // Reported bug: a recipe for 6 images remains after the dataset reaches 48.
  assert.equal(stepsRecipeRefreshDelay(true, { n_images: 6, steps: 1500 }, 48),
    STEPS_RECIPE_BURST_MS);
  assert.equal(stepsRecipeRefreshDelay(true, { n_images: 48, steps: 3500 }, 47),
    STEPS_RECIPE_BURST_MS);
});

test('an older server without n_images never blocks the refresh', () => {
  assert.equal(stepsRecipeRefreshDelay(true, { steps: 1500 }, 48), 0);
  assert.equal(stepsRecipeRefreshDelay(true, { n_images: null }, 48), 0);
  assert.equal(stepsRecipeRefreshDelay(true, { n_images: 6 }, null), 0);
  assert.equal(stepsRecipeRefreshDelay(true, { n_images: 6 }, undefined), 0);
});
