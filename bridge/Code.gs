/**
 * Drive Agent bridge: runs inside Google Apps Script AS THE OWNER.
 * The Python tools POST {secret, action, args}; this replies {ok, result} or {ok:false, error}.
 *
 * Script properties (Project Settings -> Script properties), never in code:
 *   SECRET                long random string (40+ chars), same as DRIVE_BRIDGE_SECRET in the cloud env
 *   FORBIDDEN_FOLDER_IDS  the forbidden folder ID (comma-separate several)
 *   REPORT_EMAIL          the only address send_mail will send to
 * Services: add "Drive API" (v3) under Services (+).
 *
 * Its own guard refuses anything inside a forbidden folder (any depth, shortcuts too), fails
 * closed, and errors never include file names or IDs. Tests: node --test bridge/
 */
var FIELDS = 'id,name,mimeType,size,modifiedTime,viewedByMeTime,parents,md5Checksum,ownedByMe,trashed,shortcutDetails,webViewLink';
var FOLDER = 'application/vnd.google-apps.folder';
var SHORTCUT = 'application/vnd.google-apps.shortcut';
var MAX_DOWNLOAD = 45 * 1024 * 1024;
var SAFE_ID = /^[A-Za-z0-9_-]+$/;
var SAFE_TIME = /^\d{4}-\d{2}-\d{2}T[0-9:.]+Z$/;

function NotFound_() { this.notFound = true; }
function Refused_() { this.refused = true; }
function GuardUnavailable_() { this.guardUnavailable = true; }
function IncompleteListing_() { this.incomplete = true; }

function safeEqual_(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  var diff = 0;
  for (var i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function makeGuard_(env) {
  var forb = {};
  String(env.props.FORBIDDEN_FOLDER_IDS || '').split(',').forEach(function (s) {
    s = s.trim(); if (s) forb[s] = true;
  });
  var configured = Object.keys(forb).length > 0;
  var cache = {};
  var rootId = null;
  var index = {};

  function get(id) {
    if (index[id]) return index[id];
    try { return env.drive.get(id); }
    catch (e) { if (/not found|404/i.test(String(e && e.message))) throw new NotFound_(); throw e; }
  }
  function root() { if (rootId === null) rootId = env.drive.get('root').id; return rootId; }

  function folderBlocked(id, depth) {
    if (forb[id]) return true;
    if (cache.hasOwnProperty(id)) return cache[id];
    if (depth > 50) return true;
    var f = get(id);
    var blocked = !!forb[f.id] || (f.parents || []).some(function (p) { return folderBlocked(p, depth + 1); });
    cache[id] = blocked;
    return blocked;
  }

  // strict (listing): a lookup that fails for any reason but not-found aborts the whole call
  // with GuardUnavailable_, so a Drive hiccup can't silently turn into an empty listing.
  function metaBlocked(m, strict) {
    if (!configured) return true;
    try {
      if (forb[m.id]) return true;
      if (m.mimeType === SHORTCUT) {
        var t = m.shortcutDetails && m.shortcutDetails.targetId;
        if (!t || metaBlocked(get(t), strict)) return true;
      }
      var parents = m.parents || [];
      if (!parents.length) return m.id !== root();  // only My Drive itself has no parents
      return parents.some(function (p) { return folderBlocked(p, 0); });
    } catch (e) {
      if (strict && !(e instanceof NotFound_)) throw new GuardUnavailable_();
      return true;  // fail closed
    }
  }

  return {
    configured: configured,
    forbiddenIds: Object.keys(forb),
    get: get,
    setIndex: function (files) { files.forEach(function (f) { index[f.id] = f; }); },
    metaBlocked: metaBlocked,
    // Fetch + check. Throws NotFound_ / Refused_.
    check: function (id) {
      if (!configured) throw new Refused_();
      if (id === 'root') return get('root');
      if (typeof id !== 'string' || !SAFE_ID.test(id)) throw new Refused_();
      var m = get(id);
      if (metaBlocked(m)) throw new Refused_();
      return m;
    },
  };
}

// Every entry must be a bare Drive ID. Anything else ({"id"}, a URL, quotes) would silently match
// nothing, so the bridge refuses all Drive actions until the property is fixed.
function forbiddenIdsMalformed_(props) {
  return String(props.FORBIDDEN_FOLDER_IDS || '').split(',').some(function (s) {
    s = s.trim(); return s !== '' && !SAFE_ID.test(s);
  });
}

function q_(s) { return String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'"); }

// stats (optional) collects name-free counts: pages fetched and whether Drive cut the search short.
function listAll_(env, q, stats) {
  var out = [], token = null;
  stats = stats || {};
  stats.pages = 0; stats.incomplete = false;
  do {
    var resp = env.drive.list({ q: q, pageSize: 1000, pageToken: token,
                                fields: 'nextPageToken,incompleteSearch,files(' + FIELDS + ')' });
    stats.pages++;
    if (resp.incompleteSearch) stats.incomplete = true;
    out = out.concat(resp.files || []);
    token = resp.nextPageToken;
  } while (token);
  return out;
}

function findChild_(env, g, a, folder) {
  g.check(a.parent);
  var q = "name = '" + q_(a.name) + "' and '" + q_(a.parent) + "' in parents and trashed = false and mimeType " +
    (folder ? '= ' : '!= ') + "'" + FOLDER + "'";
  var hits = listAll_(env, q).filter(function (f) { return !g.metaBlocked(f); });
  return hits.length ? hits[0] : null;
}

var ACTIONS = {
  get_meta: function (env, g, a) { return g.check(a.id); },

  list_files: function (env, g, a, meta) {
    if (!g.configured) throw new Refused_();
    // Deduplicated: a repeated "not 'X' in parents" clause makes Drive intermittently return an
    // empty first page with no error (seen live, 2026-11-13).
    var exclude = (a.exclude_parents || []).concat(g.forbiddenIds).filter(function (id, i, all) {
      return all.indexOf(id) === i;
    });
    exclude.forEach(function (id) { if (!SAFE_ID.test(id)) throw new Error('bad id'); });
    if (a.modified_after && !SAFE_TIME.test(a.modified_after)) throw new Error('bad time');
    var parts = ["'me' in owners", 'trashed = false'];
    exclude.forEach(function (id) { parts.push("not '" + id + "' in parents"); });
    if (a.modified_after) parts.push("modifiedTime > '" + a.modified_after + "'");
    var files = listAll_(env, parts.join(' and '), meta);
    if (meta.incomplete) throw new IncompleteListing_();  // partial results would look like "nothing to do"
    g.setIndex(files);
    var kept = files.filter(function (f) { return !g.metaBlocked(f, true); });
    meta.raw = files.length; meta.kept = kept.length;
    return kept;
  },

  export_text: function (env, g, a) {
    g.check(a.id);
    var r = env.fetch('https://www.googleapis.com/drive/v3/files/' + a.id + '/export?mimeType=' + encodeURIComponent(a.mime || 'text/plain'));
    if (r.code !== 200) throw new Error('export failed');
    return r.text();
  },

  download: function (env, g, a) {
    var m = g.check(a.id);
    if (Number(m.size || 0) > MAX_DOWNLOAD) throw new Error('too large');
    var r = env.fetch('https://www.googleapis.com/drive/v3/files/' + a.id + '?alt=media');
    if (r.code !== 200) throw new Error('download failed');
    return r.base64();
  },

  update: function (env, g, a) {
    g.check(a.id);
    var params = { fields: FIELDS };
    if (a.add_parent) {
      g.check(a.add_parent);
      params.addParents = a.add_parent;
      params.removeParents = a.remove_parent;
    }
    return env.drive.update(a.id, a.name ? { name: a.name } : {}, params, null);
  },

  create_folder: function (env, g, a) {
    g.check(a.parent);
    return env.drive.create({ name: a.name, mimeType: FOLDER, parents: [a.parent] }, { fields: FIELDS }, null);
  },

  create_file: function (env, g, a) {
    g.check(a.parent);
    return env.drive.create({ name: a.name, mimeType: a.mime, parents: [a.parent] }, { fields: FIELDS }, null);
  },

  find_child_folder: function (env, g, a) { return findChild_(env, g, a, true); },
  find_child_file: function (env, g, a) { return findChild_(env, g, a, false); },

  upload: function (env, g, a) {
    var blob = env.blob(a.data, a.mime, a.name);
    if (a.file_id) { g.check(a.file_id); return env.drive.update(a.file_id, {}, { fields: FIELDS }, blob); }
    g.check(a.parent);
    return env.drive.create({ name: a.name, parents: [a.parent] }, { fields: FIELDS }, blob);
  },

  sheet_rows: function (env, g, a) { g.check(a.sid); return env.sheets.rows(a.sid); },
  sheet_append: function (env, g, a) { g.check(a.sid); env.sheets.append(a.sid, a.rows); return true; },
  sheet_set: function (env, g, a) { g.check(a.sid); env.sheets.set(a.sid, a.row, a.col, a.value); return true; },
  sheet_setup: function (env, g, a) { g.check(a.sid); env.sheets.setup(a.sid, a.header, a.choices, a.answer_col); return true; },

  send_mail: function (env, g, a) {
    var to = String(env.props.REPORT_EMAIL || '').toLowerCase();
    if (!to || String(a.to || '').toLowerCase() !== to) return { ok: false, error: 'bad_recipient' };
    env.mail(env.props.REPORT_EMAIL, String(a.subject || ''), String(a.body || ''));
    return 'sent';
  },
};

function handle(req, env) {
  var secret = String(env.props.SECRET || '');
  if (!req || secret.length < 32 || !safeEqual_(req.secret, secret)) return { ok: false, error: 'unauthorized' };
  var fn = ACTIONS.hasOwnProperty(req.action) ? ACTIONS[req.action] : null;
  if (!fn) return { ok: false, error: 'unknown_action' };
  // send_mail touches no Drive file, so the report can still tell the owner about the bad config
  if (req.action !== 'send_mail' && forbiddenIdsMalformed_(env.props)) return { ok: false, error: 'bad_config' };
  try {
    var meta = {};  // counts only, never names or IDs
    var result = fn(env, makeGuard_(env), req.args || {}, meta);
    if (result && result.ok === false) return result;
    var out = { ok: true, result: result === undefined ? null : result };
    if (Object.keys(meta).length) out.meta = meta;
    return out;
  } catch (e) {
    if (e instanceof NotFound_) return { ok: false, error: 'not_found' };
    if (e instanceof Refused_) return { ok: false, error: 'refused' };
    if (e instanceof GuardUnavailable_) return { ok: false, error: 'guard_unavailable' };
    if (e instanceof IncompleteListing_) return { ok: false, error: 'incomplete_listing' };
    return { ok: false, error: 'error' };  // never the message: it may contain names
  }
}

// ---------------- Apps Script entry point + real services ----------------
function doPost(e) {
  var req;
  try { req = JSON.parse(e.postData.contents); } catch (err) { req = null; }
  var out = handle(req, realEnv_());
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}

function realEnv_() {
  return {
    props: PropertiesService.getScriptProperties().getProperties(),
    drive: {
      get: function (id) { return Drive.Files.get(id, { fields: FIELDS }); },
      list: function (params) { return Drive.Files.list(params); },
      update: function (id, resource, params, blob) { return Drive.Files.update(resource, id, blob, params); },
      create: function (resource, params, blob) { return Drive.Files.create(resource, blob, params); },
    },
    fetch: function (url) {
      var r = UrlFetchApp.fetch(url, { headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() }, muteHttpExceptions: true });
      return { code: r.getResponseCode(), text: function () { return r.getContentText(); },
               base64: function () { return Utilities.base64Encode(r.getContent()); } };
    },
    blob: function (b64, mime, name) { return Utilities.newBlob(Utilities.base64Decode(b64), mime, name); },
    mail: function (to, subject, body) { MailApp.sendEmail(to, subject, body); },
    sheets: {
      tab_: function (sid) { var ss = SpreadsheetApp.openById(sid); return ss.getSheetByName('Inbox') || ss.getSheets()[0]; },
      rows: function (sid) { return this.tab_(sid).getDataRange().getDisplayValues(); },
      append: function (sid, rows) { var t = this.tab_(sid); rows.forEach(function (r) { t.appendRow(r); }); },
      set: function (sid, row, col, value) { this.tab_(sid).getRange(row, col).setValue(value); },
      setup: function (sid, header, choices, answerCol) {
        var t = SpreadsheetApp.openById(sid).getSheets()[0];
        t.setName('Inbox');
        t.getRange(1, 1, 1, header.length).setValues([header]).setFontWeight('bold');
        t.setFrozenRows(1);
        var rule = SpreadsheetApp.newDataValidation().requireValueInList(choices, true).setAllowInvalid(false).build();
        t.getRange(2, answerCol, 999, 1).setDataValidation(rule);
      },
    },
  };
}

/** Run once from the editor: authorizes the script and checks the setup without listing anything. */
function selfTest() {
  var env = realEnv_();
  var g = makeGuard_(env);
  Logger.log('secret set: ' + (String(env.props.SECRET || '').length >= 32));
  Logger.log('forbidden folder configured: ' + g.configured);
  Logger.log('forbidden IDs well-formed: ' + !forbiddenIdsMalformed_(env.props));
  Logger.log('report email set: ' + !!env.props.REPORT_EMAIL);
  Logger.log('My Drive reachable: ' + !!env.drive.get('root').id);
}

if (typeof module !== 'undefined') module.exports = { handle: handle };
