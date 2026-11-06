import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import vm from 'node:vm';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [fileURLToPath(new URL('../src/App.tsx', import.meta.url))],
  bundle: true, write: false, format: 'cjs', platform: 'node', external: ['react'],
  // Public rendering must never import a client that fetches private records.
  plugins: [{ name: 'no-private-api', setup(builder) {
    builder.onResolve({ filter: /api\/client$/ }, () => { throw new Error('Public app must not load private API clients'); });
  } }],
});
const module = { exports: {} };
const browser = { location: { pathname: '/' } };
Object.defineProperty(browser, 'sessionStorage', { get() { throw new Error('Public app must not restore student data'); } });
vm.runInNewContext(compiled.outputFiles[0].text, {
  module, exports: module.exports, require: createRequire(import.meta.url), window: browser,
});
const { App, publicPath } = module.exports;
const render = path => {
  browser.location.pathname = path;
  return renderToStaticMarkup(React.createElement(App));
};

test('homepage renders dashboard immediately, without a session or auth controls', () => {
  const html = render('/');
  assert.match(html, /Welcome to LearnMateAI/);
  for (const text of ['My Subjects', 'AI Tutor', 'Assessments &amp; Quizzes', 'Concept Mastery']) assert.ok(html.includes(text));
  assert.doesNotMatch(html, /type="password"|Log in|Log out|Sign up|Register|Loading secure session/);
  assert.doesNotMatch(html, /Open profile|Textbooks/);
});

test('retired authentication paths resolve to root without a redirect loop', () => {
  for (const path of ['/login', '/register', '/signup', '/login/', '/register/']) {
    assert.equal(publicPath(path), '/');
    assert.equal(publicPath(publicPath(path)), '/');
    assert.match(render(path), /Welcome to LearnMateAI/);
  }
});

test('learning routes render interfaces with explicit unavailable states', () => {
  for (const [path, title] of [
    ['/subjects', 'My Subjects'], ['/subjects/private-id/chapters', 'Chapters'],
    ['/tutor', 'Your learning workspace'], ['/study/private-id', 'Your learning workspace'],
    ['/assessment', 'Assessments &amp; Quizzes'], ['/diagnostic', 'Assessments &amp; Quizzes'],
    ['/practice', 'Assessments &amp; Quizzes'], ['/progress', 'Concept mastery tracking'],
  ]) {
    const html = render(path);
    assert.ok(html.includes(title), path);
    assert.match(html, /unavailable in this public deployment/);
    assert.match(html, /No student records are loaded or saved here/);
    assert.doesNotMatch(html, /type="password"|Please log in/);
  }
});

test('tutor and assessment actions that require private APIs are disabled', () => {
  assert.match(render('/tutor'), /disabled="" aria-label="Send question unavailable"/);
  assert.match(render('/tutor'), /disabled="">Generate quiz/);
  assert.match(render('/assessment'), /disabled="">Start assessment/);
});

test('direct private and administrative UI URLs never render student records or admin tools', () => {
  assert.match(render('/admin/textbooks'), /Administration unavailable/);
  assert.match(render('/profile'), /Student profile unavailable/);
  assert.doesNotMatch(render('/admin/textbooks'), /type="file"|Upload textbook/);
});
