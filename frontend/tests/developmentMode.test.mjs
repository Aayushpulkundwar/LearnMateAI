import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { transform } from 'esbuild';

const source = await readFile(new URL('../src/config/developmentMode.ts', import.meta.url), 'utf8');
const { code } = await transform(source, { loader: 'ts', format: 'esm', target: 'es2020' });
const { shouldSkipLogin } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);

test('login bypass requires an explicit true value in a development build', () => {
  assert.equal(shouldSkipLogin(true, 'true'), true);
  assert.equal(shouldSkipLogin(true, undefined), false);
  assert.equal(shouldSkipLogin(true, 'TRUE'), false);
});

test('login bypass is unavailable in production builds even when requested', () => {
  assert.equal(shouldSkipLogin(false, 'true'), false);
});
