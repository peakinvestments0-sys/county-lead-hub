const chokidar = require('chokidar');
const path = require('node:path');
const fs = require('node:fs/promises');
const { spawn } = require('node:child_process');
const { randomUUID } = require('node:crypto');

const root = path.resolve(__dirname, '..');

function ingestPullFile(filePath) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.INBOUND_PYTHON || 'python',
      [path.join(__dirname, 'ingest_pull_file.py'), filePath],
      { cwd: root, windowsHide: true, env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
    let output = '';
    let errors = '';
    child.stdout.on('data', chunk => { output += chunk; });
    child.stderr.on('data', chunk => { errors = (errors + chunk).slice(-4000); });
    child.on('error', reject);
    child.on('close', code => {
      const line = output.split(/\r?\n/).findLast(value => value.startsWith('INBOUND_RESULT='));
      try {
        const result = line ? JSON.parse(line.slice('INBOUND_RESULT='.length)) : {};
        if (code !== 0 || result.error) {
          reject(Object.assign(new Error(result.error || errors || `Ingest exited ${code}`), { summary: result }));
        } else if (!line) {
          reject(new Error('Ingest returned no result'));
        } else {
          resolve(result);
        }
      } catch (error) { reject(error); }
    });
  });
}

async function moveTo(filePath, destination) {
  // Exclusive hard links are not supported on Drive's virtual filesystem.
  // COPYFILE_EXCL prevents overwriting an earlier archived pull with the same name.
  const { constants } = require('node:fs');
  let target = path.join(path.dirname(filePath), destination, path.basename(filePath));
  for (;;) {
    try {
      await fs.copyFile(filePath, target, constants.COPYFILE_EXCL);
      await fs.unlink(filePath);
      return target;
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      target = path.join(path.dirname(filePath), destination,
        `${path.basename(filePath, path.extname(filePath))}-${randomUUID()}.csv`);
    }
  }
}

async function startWatcher({ dir = process.env.INBOUND_PULL_DIR, ingest = ingestPullFile,
  log = line => console.log(line), recoverInitial = true } = {}) {
  if (!dir) throw new Error('INBOUND_PULL_DIR is required');
  dir = path.resolve(dir);
  // A missing Drive mount is an operational failure, not an empty new directory.
  if (!(await fs.stat(dir)).isDirectory()) throw new Error('INBOUND_PULL_DIR must be a directory');
  await fs.mkdir(path.join(dir, 'processed'), { recursive: true });
  await fs.mkdir(path.join(dir, 'quarantine'), { recursive: true });
  let pending = Promise.resolve();
  const active = new Set();
  const watcher = chokidar.watch(dir, {
    persistent: true, ignoreInitial: true, depth: 0, followSymlinks: false,
    // Polling works on Drive for Desktop even when fs.watch notifications are lost.
    usePolling: true, interval: 500,
    ignored: (candidate, stats) => {
      candidate = path.resolve(candidate);
      return candidate !== dir && (path.dirname(candidate) !== dir ||
        stats?.isDirectory() || !candidate.toLowerCase().endsWith('.csv'));
    },
    awaitWriteFinish: { stabilityThreshold: 2000, pollInterval: 500 },
  });
  async function processFile(filePath) {
    let summary = { filename: path.basename(filePath), list_type: 'unknown', county: 'unknown',
      rows_ingested: 0, rows_skipped_duplicates: 0, rows_quarantined: 0 };
    try {
      summary = { ...summary, ...await ingest(filePath) };
    } catch (error) {
      summary = { ...summary, ...error.summary, error: error.message };
      // Count with the shared CSV parser when possible; do not count lines in Node.
      summary.rows_quarantined = error.summary?.rows_total ?? null;
      try { await moveTo(filePath, 'quarantine'); summary.destination = 'quarantine'; }
      catch (moveError) { summary.move_error = moveError.message; summary.destination = 'inbound'; }
    }
    if (!summary.error) {
      // An archive error must never reclassify successfully ingested rows as bad schema.
      try { await moveTo(filePath, 'processed'); summary.destination = 'processed'; }
      catch (error) { summary.move_error = error.message; summary.destination = 'inbound'; }
    }
    log('[inbound-pull] ' + JSON.stringify({ ...summary, timestamp: new Date().toISOString() }));
  }
  function enqueue(filePath) {
    if (active.has(filePath)) return;
    active.add(filePath);
    pending = pending.then(() => processFile(filePath)).finally(() => active.delete(filePath));
  }
  watcher.on('add', enqueue);
  watcher.on('error', error => log('[inbound-pull] ' + JSON.stringify({ error: error.message, timestamp: new Date().toISOString() })));
  await new Promise((resolve, reject) => { watcher.once('ready', resolve); watcher.once('error', reject); });
  if (recoverInitial) {
    // Recover files synced while the app was off, with the same 2s stability gate.
    for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
      if (entry.isFile() && entry.name.toLowerCase().endsWith('.csv')) {
        const filePath = path.join(dir, entry.name);
        if (active.has(filePath)) continue;
        active.add(filePath);
        pending = pending.then(async () => {
          let previous;
          let stableSince = Date.now();
          for (;;) {
            let stat;
            try { stat = await fs.stat(filePath); }
            catch (error) { if (error.code === 'ENOENT') return; throw error; }
            const current = `${stat.size}:${stat.mtimeMs}`;
            if (current !== previous) { previous = current; stableSince = Date.now(); }
            if (Date.now() - stableSince >= 2000) break;
            await new Promise(resolve => setTimeout(resolve, 500));
          }
          await processFile(filePath);
        }).finally(() => active.delete(filePath));
      }
    }
  }
  return { watcher, drain: () => pending, close: async () => { await watcher.close(); await pending; } };
}

if (require.main === module) {
  let lock;
  const lockPath = path.join(root, 'data', 'inbound-watcher.lock');
  async function claimLock() {
    await fs.mkdir(path.dirname(lockPath), { recursive: true });
    for (;;) {
      try {
        lock = await fs.open(lockPath, 'wx');
        await lock.writeFile(String(process.pid));
        return;
      } catch (error) {
        if (error.code !== 'EEXIST') throw error;
        const pid = Number(await fs.readFile(lockPath, 'utf8'));
        try { process.kill(pid, 0); }
        catch (checkError) {
          if (checkError.code !== 'ESRCH') throw checkError;
          await fs.unlink(lockPath);
          continue;
        }
        throw new Error(`Inbound watcher already running (PID ${pid})`);
      }
    }
  }
  async function releaseLock() {
    if (lock) { await lock.close(); await fs.unlink(lockPath); }
  }
  claimLock().then(() => startWatcher()).then(service => {
    console.log(`[inbound-pull] watching ${process.env.INBOUND_PULL_DIR}`);
    let stopping = false;
    async function stop() {
      if (stopping) return;
      stopping = true;
      await service.close();
      await releaseLock();
      process.exit(0);
    }
    for (const signal of ['SIGINT', 'SIGTERM']) {
      process.once(signal, stop);
    }
    if (process.env.INBOUND_PARENT_PID) {
      // Task Scheduler stops the supervisor without reliably stopping children.
      // Finish an active import and stop watching when our supervisor exits.
      setInterval(() => {
        try { process.kill(Number(process.env.INBOUND_PARENT_PID), 0); }
        catch (error) { if (error.code === 'ESRCH') stop(); }
      }, 1000).unref();
    }
  }).catch(async error => {
    console.error('[inbound-pull]', error.message);
    if (lock) await releaseLock();
    process.exitCode = 1;
  });
}

module.exports = { startWatcher, ingestPullFile, moveTo };
