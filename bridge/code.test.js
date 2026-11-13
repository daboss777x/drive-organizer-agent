// Run: node --test bridge/
const test = require('node:test');
const assert = require('node:assert');
const { handle } = require('./Code.gs');

const SECRET = 'x'.repeat(40);
const SHORTCUT = 'application/vnd.google-apps.shortcut';

function makeEnv(props = {}) {
  const files = {
    ROOT: { id: 'ROOT', name: 'My Drive', mimeType: 'application/vnd.google-apps.folder' },
    VAULT: { id: 'VAULT', name: 'Vault', mimeType: 'application/vnd.google-apps.folder', parents: ['ROOT'] },
    SUB: { id: 'SUB', name: 'sub', mimeType: 'application/vnd.google-apps.folder', parents: ['VAULT'] },
    DEEP: { id: 'DEEP', name: 'notes.txt', mimeType: 'text/plain', parents: ['SUB'] },
    WORK: { id: 'WORK', name: 'Work', mimeType: 'application/vnd.google-apps.folder', parents: ['ROOT'] },
    OK: { id: 'OK', name: 'plan.txt', mimeType: 'text/plain', parents: ['WORK'] },
    SC: { id: 'SC', name: 'link', mimeType: SHORTCUT, parents: ['WORK'], shortcutDetails: { targetId: 'DEEP' } },
  };
  const calls = [];
  const env = {
    props: { SECRET, FORBIDDEN_FOLDER_IDS: 'VAULT', REPORT_EMAIL: 'me@x.com', ...props },
    calls,
    drive: {
      get(id) {
        calls.push(['get', id]);
        if (id === 'root') return files.ROOT;
        if (!files[id]) throw new Error('File not found: ' + id);
        return files[id];
      },
      list(params) { calls.push(['list', params.q]); return { files: Object.values(files).filter(f => f.id !== 'ROOT') }; },
      update(id, resource, params) { calls.push(['update', id, params]); return files[id]; },
      create(resource) { calls.push(['create', resource.name]); return { id: 'NEW', ...resource }; },
    },
    fetch(url) { calls.push(['fetch', url]); return { code: 200, text: () => 'TEXT', base64: () => 'QQ==' }; },
    blob() { return {}; },
    mail(to, s, b) { calls.push(['mail', to]); },
    sheets: {},
  };
  return env;
}

const req = (action, args, secret = SECRET) => ({ secret, action, args });
const touched = (env, verb) => env.calls.filter(c => c[0] === verb);

test('wrong or missing secret is rejected before touching Drive', () => {
  const missing = { action: 'get_meta', args: { id: 'OK' } };
  for (const r of [req('get_meta', { id: 'OK' }, 'nope'), req('get_meta', { id: 'OK' }, ''), missing, null]) {
    const env = makeEnv();
    assert.deepStrictEqual(handle(r, env), { ok: false, error: 'unauthorized' });
    assert.strictEqual(env.calls.length, 0);
  }
});

test('a short secret configured in the script is rejected', () => {
  const env = makeEnv({ SECRET: 'short' });
  assert.strictEqual(handle(req('get_meta', { id: 'OK' }, 'short'), env).error, 'unauthorized');
});

test('unconfigured forbidden folder refuses everything', () => {
  const env = makeEnv({ FORBIDDEN_FOLDER_IDS: '' });
  assert.strictEqual(handle(req('get_meta', { id: 'OK' }), env).error, 'refused');
});

test('normal file metadata is returned; missing file is not_found', () => {
  const env = makeEnv();
  assert.strictEqual(handle(req('get_meta', { id: 'OK' }), env).result.id, 'OK');
  assert.strictEqual(handle(req('get_meta', { id: 'GONE' }), env).error, 'not_found');
});

test('anything inside the forbidden folder is refused, at any depth or via shortcut', () => {
  for (const id of ['VAULT', 'SUB', 'DEEP', 'SC']) {
    assert.strictEqual(handle(req('get_meta', { id }), makeEnv()).error, 'refused', id);
  }
});

test('export and download of protected files are refused without fetching', () => {
  for (const action of ['export_text', 'download']) {
    const env = makeEnv();
    assert.strictEqual(handle(req(action, { id: 'DEEP', mime: 'text/plain' }), env).error, 'refused');
    assert.strictEqual(touched(env, 'fetch').length, 0);
  }
  assert.strictEqual(handle(req('export_text', { id: 'OK', mime: 'text/plain' }), makeEnv()).result, 'TEXT');
});

test('moving a file into the forbidden folder is refused', () => {
  const env = makeEnv();
  const r = handle(req('update', { id: 'OK', add_parent: 'SUB', remove_parent: 'WORK', name: null }), env);
  assert.strictEqual(r.error, 'refused');
  assert.strictEqual(touched(env, 'update').length, 0);
});

test('list_files excludes forbidden folders in the query and filters descendants out', () => {
  const env = makeEnv();
  const r = handle(req('list_files', { exclude_parents: ['VAULT'], modified_after: null }), env);
  const ids = r.result.map(f => f.id).sort();
  assert.deepStrictEqual(ids, ['OK', 'WORK']);
  assert.match(touched(env, 'list')[0][1], /not 'VAULT' in parents/);
});

test('list_files rejects query injection', () => {
  const r = handle(req('list_files', { exclude_parents: ["x' or '1'='1"], modified_after: null }), makeEnv());
  assert.strictEqual(r.error, 'error');
});

test('mail only goes to the configured report address', () => {
  const env = makeEnv();
  assert.strictEqual(handle(req('send_mail', { to: 'evil@x.com', subject: 's', body: 'b' }), env).ok, false);
  assert.strictEqual(touched(env, 'mail').length, 0);
  assert.strictEqual(handle(req('send_mail', { to: 'ME@x.com', subject: 's', body: 'b' }), env).ok, true);
});

test('unexpected errors return a bare code with no message', () => {
  const env = makeEnv();
  env.drive.get = () => { throw new Error('boom secret-name.pdf'); };
  const r = handle(req('get_meta', { id: 'OK' }), env);
  assert.deepStrictEqual(r, { ok: false, error: 'error' });
  const env2 = makeEnv();
  env2.drive.list = () => { throw new Error('boom secret-name.pdf'); };
  assert.deepStrictEqual(handle(req('list_files', { exclude_parents: [], modified_after: null }), env2),
    { ok: false, error: 'error' });
});

test('unknown actions are rejected', () => {
  assert.strictEqual(handle(req('delete', { id: 'OK' }), makeEnv()).error, 'unknown_action');
});

test('upload cannot overwrite or create inside protected files', () => {
  const env = makeEnv();
  assert.strictEqual(handle(req('upload', { name: 'x', parent: 'WORK', mime: 'text/plain', file_id: 'DEEP', data: '' }), env).error, 'refused');
  assert.strictEqual(handle(req('upload', { name: 'x', parent: 'SUB', mime: 'text/plain', file_id: null, data: '' }), env).error, 'refused');
  assert.strictEqual(touched(env, 'update').length + touched(env, 'create').length, 0);
});

test('sheet actions on a protected id are refused', () => {
  for (const action of ['sheet_rows', 'sheet_append', 'sheet_set', 'sheet_setup']) {
    assert.strictEqual(handle(req(action, { sid: 'DEEP' }), makeEnv()).error, 'refused', action);
  }
});

test('list_files reports guard_unavailable instead of silently dropping files when a lookup fails', () => {
  const env = makeEnv();
  const realGet = env.drive.get;
  env.drive.get = (id) => { if (id === 'root' || id === 'ROOT') throw new Error('User rate limit exceeded'); return realGet(id); };
  const r = handle(req('list_files', { exclude_parents: [], modified_after: null }), env);
  assert.deepStrictEqual(r, { ok: false, error: 'guard_unavailable' });
});

test('list_files drops only the file whose parent is missing (fail closed per file)', () => {
  const env = makeEnv();
  const realList = env.drive.list;
  env.drive.list = (params) => {
    const r = realList(params);
    r.files.push({ id: 'ORPHAN', name: 'o.txt', mimeType: 'text/plain', parents: ['GONE'] });
    return r;
  };
  const r = handle(req('list_files', { exclude_parents: ['VAULT'], modified_after: null }), env);
  assert.strictEqual(r.ok, true);
  assert.deepStrictEqual(r.result.map(f => f.id).sort(), ['OK', 'WORK']);
});

test('a malformed FORBIDDEN_FOLDER_IDS (e.g. {"id"} or a URL) refuses every action with bad_config', () => {
  for (const bad of ['{"VAULT"}', 'https://drive.google.com/drive/folders/VAULT', 'VAULT, "x"']) {
    for (const [action, args] of [['get_meta', { id: 'OK' }], ['list_files', { exclude_parents: [], modified_after: null }],
                                  ['sheet_rows', { sid: 'OK' }]]) {
      const env = makeEnv({ FORBIDDEN_FOLDER_IDS: bad });
      assert.deepStrictEqual(handle(req(action, args), env), { ok: false, error: 'bad_config' }, bad + ' ' + action);
      assert.strictEqual(env.calls.length, 0);
    }
  }
});

test('list_files returns name-free counts in meta', () => {
  const r = handle(req('list_files', { exclude_parents: ['VAULT'], modified_after: null }), makeEnv());
  assert.deepStrictEqual(r.meta, { pages: 1, raw: 6, kept: 2, incomplete: false });
});

test('list_files fails with incomplete_listing when Drive reports an incomplete search', () => {
  const env = makeEnv();
  const realList = env.drive.list;
  env.drive.list = (params) => ({ ...realList(params), files: [], incompleteSearch: true });
  assert.deepStrictEqual(handle(req('list_files', { exclude_parents: [], modified_after: null }), env),
    { ok: false, error: 'incomplete_listing' });
});

test('list_files puts each excluded folder in the query once (duplicates make Drive return empty pages)', () => {
  const env = makeEnv();
  handle(req('list_files', { exclude_parents: ['VAULT', 'VAULT', 'WORK'], modified_after: null }), env);
  const q = touched(env, 'list')[0][1];
  assert.strictEqual(q.split("not 'VAULT' in parents").length - 1, 1, q);
  assert.strictEqual(q.split("not 'WORK' in parents").length - 1, 1, q);
});
