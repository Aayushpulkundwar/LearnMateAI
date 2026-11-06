import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import vm from 'node:vm';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { build } from 'esbuild';

// Compile the real component; API imports are unused during static rendering.
const result = await build({
  entryPoints: [fileURLToPath(new URL('../src/components/AuthPanel.tsx', import.meta.url))],
  bundle: true, write: false, format: 'cjs', platform: 'node', external: ['react'],
  plugins: [{ name: 'unused-api', setup(build) {
    build.onResolve({ filter: /api\/client$/ }, () => ({ path: 'api', namespace: 'unused-api' }));
    build.onLoad({ filter: /.*/, namespace: 'unused-api' }, () => ({ contents: 'export const listGrades = () => {}; export const loginStudent = () => {}; export const registerStudent = () => {};', loader: 'js' }));
  } }],
});
const module = { exports: {} };
vm.runInNewContext(result.outputFiles[0].text, { module, exports: module.exports, require: createRequire(import.meta.url) });
const { GradeSelect } = module.exports;
const grades = [7, 8, 9, 10, 11, 12].map(number => ({ id: `api-id-${number}`, name: `Class ${number}` }));

test('dropdown renders six API grades in order and uses the selected API ID', () => {
  for (const selected of grades) {
    const markup = renderToStaticMarkup(React.createElement(GradeSelect, { grades, value: selected.id, loading: false, onChange() {} }));
    assert.equal((markup.match(/<option/g) || []).length, 7);
    assert.match(markup, new RegExp(`value="${selected.id}" selected=""`));
    let previous = -1;
    for (const grade of grades) {
      const position = markup.indexOf(`>${grade.name}</option>`);
      assert.ok(position > previous);
      previous = position;
    }
    assert.ok(!markup.includes('disabled=""'));
  }
});

test('dropdown is disabled while grades load or are unavailable', () => {
  for (const loading of [true, false]) {
    const markup = renderToStaticMarkup(React.createElement(GradeSelect, { grades: [], value: '', loading, onChange() {} }));
    assert.match(markup, /disabled=""/);
    if (loading) assert.match(markup, /Loading grades/);
  }
});
