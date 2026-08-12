import test from 'node:test';
import assert from 'node:assert/strict';

import { REVIEW_SHORTCUT_HINT, ownsTypedKeys, reviewKeyAction } from './reviewShortcuts.js';

const press = (key, extra = {}) => ({ key, target: null, ...extra });

test('the three verdicts are on K, R and S', () => {
  assert.equal(reviewKeyAction(press('k')), 'keep');
  assert.equal(reviewKeyAction(press('r')), 'reject');
  assert.equal(reviewKeyAction(press('s')), 'skip');
  // Caps Lock must not silently disarm the whole mode.
  assert.equal(reviewKeyAction(press('K')), 'keep');
  assert.equal(reviewKeyAction(press('R')), 'reject');
  assert.equal(reviewKeyAction(press('S')), 'skip');
});

test('→ IS skip, ← goes back, Esc closes', () => {
  // Moving on without judging is a skip — same action, two keys, so that a walk
  // with the arrows never quietly means something else than the ⏭ button.
  assert.equal(reviewKeyAction(press('ArrowRight')), 'skip');
  assert.equal(reviewKeyAction(press('ArrowLeft')), 'back');
  assert.equal(reviewKeyAction(press('Escape')), 'close');
});

test('a modified keystroke is never ours', () => {
  for (const mod of ['metaKey', 'ctrlKey', 'altKey', 'shiftKey']) {
    assert.equal(reviewKeyAction(press('k', { [mod]: true })), null, mod);
    assert.equal(reviewKeyAction(press('ArrowRight', { [mod]: true })), null, mod);
  }
  // ⌘R must reload the page, not reject the picture.
  assert.equal(reviewKeyAction(press('r', { metaKey: true })), null);
});

test('an unrelated key is left to the caller', () => {
  // The Bank still reads [ ] and M off the same event; returning null is what
  // lets it, instead of this module having to know about rotation and masks.
  for (const key of ['[', ']', 'm', 'Enter', 'Tab', ' ', 'ArrowUp']) {
    assert.equal(reviewKeyAction(press(key)), null, key);
  }
  assert.equal(reviewKeyAction(null), null);
  assert.equal(reviewKeyAction({}), null);
});

test('only TEXT entry swallows the shortcuts', () => {
  // The measured bug: the focus trap lands on the 🎲 Random-order checkbox when
  // the Bank review opens, and a blanket "input" guard made K/R/S inert until
  // the user clicked elsewhere.
  const el = (tagName, type) => ({ tagName, type });
  assert.equal(ownsTypedKeys(el('INPUT', 'checkbox')), false);
  assert.equal(ownsTypedKeys(el('INPUT', 'radio')), false);
  assert.equal(ownsTypedKeys(el('INPUT', 'button')), false);
  assert.equal(ownsTypedKeys(el('INPUT', 'submit')), false);
  assert.equal(ownsTypedKeys(el('INPUT', 'range')), false);
  assert.equal(ownsTypedKeys(el('INPUT', 'text')), true);
  assert.equal(ownsTypedKeys(el('INPUT', 'search')), true);
  assert.equal(ownsTypedKeys(el('TEXTAREA', '')), true);
  assert.equal(ownsTypedKeys(el('SELECT', '')), true);
  assert.equal(ownsTypedKeys({ isContentEditable: true }), true);
  assert.equal(ownsTypedKeys(null), false);

  assert.equal(reviewKeyAction(press('k', { target: el('INPUT', 'checkbox') })), 'keep');
  assert.equal(reviewKeyAction(press('k', { target: el('TEXTAREA', '') })), null);
  assert.equal(reviewKeyAction(press('ArrowLeft', { target: el('INPUT', 'text') })), null);
});

test('Escape answers even from inside a caption field', () => {
  // A field focused inside an overlay must never be able to trap the user in it.
  assert.equal(reviewKeyAction(press('Escape', { target: { tagName: 'TEXTAREA' } })), 'close');
});

test('the printed hint is the one the handler implements', () => {
  assert.equal(REVIEW_SHORTCUT_HINT, 'K keep · R reject · S skip');
});
