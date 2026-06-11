import assert from 'node:assert/strict';
import test from 'node:test';

import {getBrowserChannelCandidates} from './playwright-check.mjs';

test('uses installed browser channels before bundled chromium', () => {
    assert.deepEqual(getBrowserChannelCandidates({}), ['msedge', 'chrome']);
});

test('honors explicit browser channel override', () => {
    assert.deepEqual(getBrowserChannelCandidates({PLAYWRIGHT_BROWSER_CHANNEL: 'chrome'}), ['chrome']);
});
