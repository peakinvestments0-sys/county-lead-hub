const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { startWatcher, moveTo } = require('../scripts/inbound-watcher.js');

async function until(check, timeout = 12000) {
  const end = Date.now() + timeout;
  while (!await check()) {
    if (Date.now() > end) throw new Error('Timed out waiting for watcher');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
}

test('chunked Drive writes, startup recovery, serial imports, quarantine, and one audit per file', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'inbound-watcher-'));
  const logs = [];
  const ingested = [];
  let active = 0;
  let maximum = 0;
  let service;
  try {
    await fs.writeFile(path.join(dir, 'existing.csv'), 'header\nold\n');
    service = await startWatcher({ dir, log: line => logs.push(line), ingest: async file => {
      active++; maximum = Math.max(maximum, active);
      try {
        const content = await fs.readFile(file, 'utf8');
        ingested.push({ name: path.basename(file), content, at: Date.now() });
        await new Promise(resolve => setTimeout(resolve, 100));
        if (file.endsWith('bad.csv')) throw Object.assign(new Error('Header mismatch: missing=grantee'),
          { summary: { rows_total: 1, list_type: 'lis-pendens', county: 'Orange' } });
        return { rows_ingested: 1, rows_skipped_duplicates: 0, rows_quarantined: 0 };
      } finally { active--; }
    } });
    await until(() => logs.length === 1);
    const chunked = path.join(dir, 'new.csv');
    await fs.writeFile(chunked, 'header\n');
    await new Promise(resolve => setTimeout(resolve, 900));
    await fs.appendFile(chunked, 'complete row\n');
    const finishedAt = Date.now();
    await fs.writeFile(path.join(dir, 'bad.csv'), 'wrong\nrow\n');
    await fs.writeFile(path.join(dir, 'ignore.txt'), 'ignored');
    await fs.writeFile(path.join(dir, 'processed', 'nested.csv'), 'ignored');
    await until(() => logs.length === 3);
    await service.drain();
    assert.equal(maximum, 1);
    const item = ingested.find(item => item.name === 'new.csv');
    assert.equal(item.content, 'header\ncomplete row\n');
    assert.ok(item.at - finishedAt >= 1900, 'Must wait for stability after the final chunk');
    assert.equal(await fs.readFile(path.join(dir, 'quarantine', 'bad.csv'), 'utf8'), 'wrong\nrow\n');
    assert.equal(logs.filter(line => JSON.parse(line.slice(15)).filename === 'bad.csv').length, 1);
    const bad = logs.map(line => JSON.parse(line.slice(15))).find(row => row.filename === 'bad.csv');
    assert.equal(bad.rows_quarantined, 1);
    assert.ok(bad.timestamp);
    assert.match(bad.error, /Header mismatch/);
    assert.equal(ingested.length, 3);
  } finally {
    if (service) await service.close();
    await fs.rm(dir, { recursive: true, force: true });
  }
});

test('archive collisions preserve both files', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'inbound-archive-'));
  try {
    await fs.mkdir(path.join(dir, 'processed'));
    await fs.writeFile(path.join(dir, 'processed', 'same.csv'), 'first');
    await fs.writeFile(path.join(dir, 'same.csv'), 'second');
    const target = await moveTo(path.join(dir, 'same.csv'), 'processed');
    assert.notEqual(target, path.join(dir, 'processed', 'same.csv'));
    assert.equal(await fs.readFile(target, 'utf8'), 'second');
    assert.equal(await fs.readFile(path.join(dir, 'processed', 'same.csv'), 'utf8'), 'first');
  } finally { await fs.rm(dir, { recursive: true, force: true }); }
});

test('an archive failure leaves committed data inbound, without quarantining it', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'inbound-move-failure-'));
  const logs = [];
  const original = fs.copyFile;
  let service;
  try {
    service = await startWatcher({ dir, recoverInitial: false, log: line => logs.push(line),
      ingest: async () => ({ rows_ingested: 4, rows_skipped_duplicates: 2 }) });
    fs.copyFile = async () => { throw new Error('Drive unavailable'); };
    await fs.writeFile(path.join(dir, 'pull.csv'), 'header\nrow\n');
    await until(() => logs.length === 1);
    const audit = JSON.parse(logs[0].slice(15));
    assert.equal(audit.rows_ingested, 4);
    assert.equal(audit.rows_skipped_duplicates, 2);
    assert.equal(audit.destination, 'inbound');
    assert.match(audit.move_error, /Drive unavailable/);
    assert.equal(audit.rows_quarantined, 0);
    assert.equal(await fs.readFile(path.join(dir, 'pull.csv'), 'utf8'), 'header\nrow\n');
    assert.deepEqual(await fs.readdir(path.join(dir, 'quarantine')), []);
  } finally {
    fs.copyFile = original;
    if (service) await service.close();
    await fs.rm(dir, { recursive: true, force: true });
  }
});
