import assert from 'node:assert/strict';
import test from 'node:test';

import { isQuicProtocol, quicStatusFromEntries } from './quicStatus.js';

test('isQuicProtocol recognises every h3 flavour and nothing else', () => {
  assert.equal(isQuicProtocol('h3'), true);
  assert.equal(isQuicProtocol('h3-29'), true);
  assert.equal(isQuicProtocol('H3'), true);
  assert.equal(isQuicProtocol('h3 '), true);
  assert.equal(isQuicProtocol('http/1.1'), false);
  assert.equal(isQuicProtocol('h2'), false);
  assert.equal(isQuicProtocol(null), false);
  assert.equal(isQuicProtocol(undefined), false);
  assert.equal(isQuicProtocol(42), false);
});

test('a same-origin h3 resource lights the badge', () => {
  const entries = [
    { name: 'http://localhost:5050/api/health', nextHopProtocol: 'h3' },
  ];
  const status = quicStatusFromEntries(entries, { origin: 'http://localhost:5050' });
  assert.equal(status.active, true);
  assert.equal(status.protocol, 'h3');
});

test('a navigation entry over h3 counts too', () => {
  const entries = [
    { name: 'http://localhost:5050/', nextHopProtocol: 'h3' },
  ];
  const status = quicStatusFromEntries(entries, { origin: 'http://localhost:5050' });
  assert.equal(status.active, true);
});

test('relative names are resolved against the app origin', () => {
  const entries = [
    { name: '/api/health', nextHopProtocol: 'h3' },
  ];
  const status = quicStatusFromEntries(entries, { origin: 'http://localhost:5050' });
  assert.equal(status.active, true);
});

test('third-party h3 resources do not light the badge', () => {
  const entries = [
    { name: 'https://cdn.example.com/app.js', nextHopProtocol: 'h3' },
    { name: 'http://localhost:5050/api/health', nextHopProtocol: 'http/1.1' },
  ];
  const status = quicStatusFromEntries(entries, { origin: 'http://localhost:5050' });
  assert.equal(status.active, false);
});

test('no origin filter still finds a QUIC resource (test seam / broad scan)', () => {
  const entries = [
    { name: 'https://cdn.example.com/app.js', nextHopProtocol: 'h3' },
  ];
  const status = quicStatusFromEntries(entries);
  assert.equal(status.active, true);
});

test('nothing measured yet is inactive, not an error', () => {
  assert.deepEqual(quicStatusFromEntries([], { origin: 'http://localhost:5050' }), { active: false, protocol: null });
  assert.deepEqual(quicStatusFromEntries(null, { origin: 'http://localhost:5050' }), { active: false, protocol: null });
});
