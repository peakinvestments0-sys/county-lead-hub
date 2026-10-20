const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
function extract(start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from);
  assert.ok(from >= 0 && to > from, `Missing function boundaries: ${start}`);
  return source.slice(from, to);
}

function createComposer({ owner = '', contactOwner = '', record = {} } = {}) {
  const nodes = new Map();
  const context = vm.createContext({
    document: {
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, {
          value: '', innerText: '', innerHTML: '', style: {},
          classList: { add() {}, remove() {} }
        });
        return nodes.get(id);
      }
    },
    window: {},
    console,
    PRESERVED_ACRONYMS: new Set(),
    savedContactsCache: { 'parcel-1': { owner: contactOwner } },
    liveRecords: [{ Parcel_ID: 'parcel-1', ...record }],
    selectedCountyKey: 'Orange',
    currentState: 'FL',
    inboxThreadsCache: [],
    outreachTemplatesCache: null,
    SMS_TEMPLATES: { cash_offer: 'Hi {FirstName}, would you consider selling {Address}?' },
    localStorage: { getItem() { return '0'; }, setItem() {} },
    markLeadAsViewed() {},
    formatDisplayAddress(value) { return value || ''; },
    formatDisplayCity(value) { return value || ''; },
    updateSmsCharCount() {},
    fetch(url) {
      assert.ok(url.startsWith('/api/outreach/lead?'), 'Only read-only history lookup is permitted');
      return Promise.resolve({ json: async () => ({ status: 'success', items: [] }) });
    }
  });
  vm.runInContext([
    extract('function formatDisplayName(', 'function formatDisplayCity('),
    extract('function resolveSmsOwnerName(', 'function cycleNextSmsTemplate('),
    extract('function applySmsTemplate(', 'function updateSmsCharCount(')
  ].join('\n'), context);
  context.openSmsModal('parcel-1', '4075550123', owner, '123 Main St');
  return { context, nodes };
}

test('blank property name uses saved contact for greeting, tracking, and copilot', () => {
  const { context, nodes } = createComposer({ contactOwner: 'Brian Bruton' });
  assert.equal(nodes.get('smsOwnerName').value, 'Brian Bruton');
  assert.equal(nodes.get('smsOwnerDisplay').innerText, 'Brian Bruton');
  assert.equal(context.window.activeSmsLeadContext.ownerName, 'Brian Bruton');
  assert.equal(nodes.get('smsMessageText').value, 'Hi Brian, would you consider selling 123 Main St?');
});

test('existing supplied name remains preferred', () => {
  const { nodes } = createComposer({ owner: 'Alice Adams', contactOwner: 'Brian Bruton' });
  assert.match(nodes.get('smsMessageText').value, /^Hi Alice,/);
});

test('placeholder supplied names use the saved owner', () => {
  for (const owner of ['Unknown Owner', 'Homeowner', 'Property Owner', 'nan', '   ']) {
    const { nodes } = createComposer({ owner, contactOwner: 'Brian Bruton' });
    assert.match(nodes.get('smsMessageText').value, /^Hi Brian,/);
  }
});

test('clean property name is used when saved owner is unavailable', () => {
  const { nodes } = createComposer({
    contactOwner: 'Property Owner',
    record: { Clean_First_Name: 'CHARLES', Clean_Last_Name: 'ANDERSON' }
  });
  assert.equal(nodes.get('smsOwnerName').value, 'Charles Anderson');
  assert.match(nodes.get('smsMessageText').value, /^Hi Charles,/);
});

test('missing names retain the existing fallback and template changes retain resolved name', () => {
  const missing = createComposer();
  assert.match(missing.nodes.get('smsMessageText').value, /^Hi Homeowner,/);
  const named = createComposer({ contactOwner: 'Brian Bruton' });
  named.context.applySmsTemplate('cash_offer');
  assert.match(named.nodes.get('smsMessageText').value, /^Hi Brian,/);
});
