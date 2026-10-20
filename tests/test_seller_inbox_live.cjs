const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
function extract(start, end) {
  const from = source.indexOf(start), to = source.indexOf(end, from);
  assert.ok(from >= 0 && to > from);
  return source.slice(from, to);
}

function harness() {
  const events = {}, windowEvents = {}, intervals = [], notices = [], nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {
      innerText: '', textContent: '', value: '', className: '',
      classList: { contains() { return false; }, add() {}, remove() {} },
      focus() {}, setSelectionRange() {}
    });
    return nodes.get(id);
  };
  let response = { messages: [], threads: [], count: 0 }, failure = false, renders = 0, requests = 0;
  const context = vm.createContext({
    AbortController,
    document: { hidden: false, getElementById: node, addEventListener: (n, fn) => { events[n] = fn; } },
    window: { addEventListener: (n, fn) => { windowEvents[n] = fn; } },
    setInterval: (fn, ms) => { intervals.push({ fn, ms }); return intervals.length; },
    setTimeout: () => 1, clearTimeout() {}, console,
    fetch: async (url, options) => {
      assert.equal(url, '/api/inbox');
      assert.equal(options.cache, 'no-store');
      requests++;
      if (failure) throw new Error('offline');
      return { ok: true, json: async () => response };
    },
    inboxThreadsCache: [], sellerInboxCache: [], activeInboxThreadKey: 'seller',
    renderInboxThreadsList() {},
    renderActiveThread() { renders++; node('inboxReplyTextarea').value = ''; },
    selectInboxThread(key) { context.activeInboxThreadKey = key; },
    loadScheduledCallbacks() {}, playInboundNotificationChime() {},
    showInboundToast(...args) { notices.push(args); }
  });
  vm.runInContext(extract('let inboxPollTimer =', 'function playInboundNotificationChime(') + '\n' +
    extract('async function pollSellerInboxUpdates()', '// SMS Copilot Card Functions'), context);
  return { context, nodes, node, events, windowEvents, intervals, notices,
    respond(data) { response = data; }, fail(value) { failure = value; },
    renders: () => renders, requests: () => requests };
}

test('page startup reaches the inbox timer and county loading without a missing-function error', async () => {
  const h = harness();
  for (const name of ['fetchStates','fetchStats','fetchCounties','fetchCustomCategories','fetchSavedContacts',
    'fetchOutreachHistory','loadSmsSettings','loadEmailSettings','loadPandadocSettings','fetchOutreachTemplates',
    'loadSellerBotSettings','fetchLinkZoneHealth','fetchOpenerMetrics','setupSearchFilter','startAutoSmsStatusPolling','startAutoEmailStatusPolling']) h.context[name] = () => {};
  let countiesLoaded = false;
  h.context.loadLiveCountyLeads = () => { countiesLoaded = true; };
  Object.assign(h.context, { currentState: 'FL', selectedCountyKey: 'Orange' });
  vm.runInContext(extract('document.addEventListener("DOMContentLoaded",', 'async function fetchStates('), h.context);
  h.events.DOMContentLoaded();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(countiesLoaded, true);
  assert.ok(h.intervals.some(i => i.fn === h.context.pollSellerInboxUpdates && i.ms === 2000));
  h.context.startSellerInboxPolling();
  assert.equal(h.intervals.filter(i => i.ms === 2000).length, 1);
  assert.equal(h.windowEvents.focus, h.context.pollSellerInboxUpdates);
});

test('an incoming reply updates the selected chat automatically and preserves the reply draft', async () => {
  const h = harness();
  const initial = { key: 'seller', messages: [] };
  h.context.inboxThreadsCache = [initial];
  h.respond({ count: 0, messages: [], threads: [initial] });
  await h.context.pollSellerInboxUpdates();
  assert.equal(h.renders(), 0, 'unchanged polls should not rebuild the chat');
  h.node('inboxReplyTextarea').value = 'My unfinished reply';
  h.context.document.activeElement = h.node('inboxReplyTextarea');
  const incoming = { timestamp: '2026-10-12 21:00:00', phone: '4075550123', direction: 'INBOUND', message: 'Yes, call me.' };
  h.respond({ count: 1, messages: [incoming], threads: [{ ...initial, messages: [incoming], inbound_count: 1 }] });
  await h.context.pollSellerInboxUpdates();
  assert.equal(h.renders(), 1);
  assert.equal(h.node('inboxReplyTextarea').value, 'My unfinished reply');
  assert.equal(h.notices.length, 1);
  assert.equal(h.notices[0][1], 'Yes, call me.');
  await h.context.pollSellerInboxUpdates();
  assert.equal(h.renders(), 1);
  assert.equal(h.notices.length, 1);
});

test('new replies notify even when the retained inbound count stays constant', async () => {
  const h = harness();
  const old = { timestamp: '1', phone: '4075550123', message: 'old' };
  h.respond({ count: 1, messages: [old], threads: [] });
  await h.context.pollSellerInboxUpdates();
  h.respond({ count: 1, messages: [{ ...old, timestamp: '2', message: 'new' }], threads: [] });
  await h.context.pollSellerInboxUpdates();
  assert.equal(h.notices.length, 1);
  assert.equal(h.notices[0][1], 'new');
});

test('connection errors are shown and the next successful poll restores live updates', async () => {
  const h = harness();
  h.fail(true);
  await h.context.pollSellerInboxUpdates();
  assert.match(h.node('inboxConnectionStatus').textContent, /Connection lost/);
  h.fail(false);
  await h.context.pollSellerInboxUpdates();
  assert.equal(h.node('inboxConnectionStatus').textContent, 'Live updates on');
});

test('overlapping polls are skipped while a previous request is pending', async () => {
  const h = harness();
  let release;
  let calls = 0;
  h.context.fetch = () => { calls++; return new Promise(resolve => { release = resolve; }); };
  const first = h.context.pollSellerInboxUpdates();
  await h.context.pollSellerInboxUpdates();
  assert.equal(calls, 1);
  release({ ok: true, json: async () => ({ messages: [], threads: [] }) });
  await first;
  const next = h.context.pollSellerInboxUpdates();
  assert.equal(calls, 2);
  release({ ok: true, json: async () => ({ messages: [], threads: [] }) });
  await next;
});

test('received SMS is labeled RECEIVED while outbound failures remain FAILED', () => {
  const badgeSource = extract('    const statusSuccess = entry.status', '    const angleBadge =');
  const badge = entry => vm.runInNewContext(badgeSource + '\nstatusBadge;', { entry });
  assert.match(badge({ direction: 'INBOUND', status: 'RECEIVED' }), /RECEIVED/);
  assert.doesNotMatch(badge({ direction: 'INBOUND', status: 'RECEIVED' }), /FAILED/);
  assert.match(badge({ direction: 'OUTBOUND', status: 'SENT' }), /SENT/);
  assert.match(badge({ direction: 'OUTBOUND', status: 'FAILED' }), /FAILED/);
});
