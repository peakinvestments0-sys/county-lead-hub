const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
const queueCode = source.slice(source.indexOf('let autoSmsQueueCache ='), source.indexOf('function renderHistoryTable()'));

function setup() {
  const nodes = new Map(), requests = [];
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {textContent:'',disabled:false,hidden:false,classList:{toggle(name,hidden){if(name==='hidden') nodes.get(id).hidden=hidden;}}});
    return nodes.get(id);
  };
  const context = vm.createContext({
    document:{getElementById:node}, AbortController, setTimeout:()=>1, clearTimeout(){},setInterval:()=>1,
    currentPipelineView:'saved',selectedCountyKey:'Orange',
    currentFilteredRecords:[{Parcel_ID:'p2'},{Parcel_ID:'p1'},{Parcel_ID:'manual'},{Parcel_ID:'p3'}],
    savedContactsCache:{p1:{source:'Skip Trace CSV (sample.csv)',county:'Orange'},p2:{source:'Skip Trace CSV (sample.csv)',county:'Pinellas'},
                       p3:{source:'Skip Trace CSV (sample.csv)',county:'Lake'},manual:{source:'TruePeopleSearch'}},
    async fetch(url,options={}){
      requests.push({url,...options});
      return {ok:true,json:async()=>({status:'success',queue:{status:'running',counties:['Lake','Orange','Pinellas'],total:3,sent:0,remaining:3}})};
    }
  });
  vm.runInContext(source.slice(source.indexOf('function isActiveCountyLead('), source.indexOf('function getActivePipelineDataset()')) + queueCode, context);
  return {context,node,requests};
}

test('Start excludes other counties even if stale rows remain in the table',async()=>{
  const h=setup();
  h.context.renderAutoSmsQueueStatus();
  assert.equal(h.node('btnStartAutoSms').hidden,false);
  assert.equal(h.node('btnStartAutoSms').disabled,false);
  await h.context.startAutoSmsBatch();
  assert.equal(h.requests.length,1);
  assert.equal(h.requests[0].url,'/api/sms/auto/start');
  assert.deepEqual(JSON.parse(h.requests[0].body),{parcel_ids:['p1']});
  assert.equal(h.node('btnStartAutoSms').disabled,true);
  assert.equal(h.node('btnPauseAutoSms').hidden,false);
  assert.match(h.node('autoSmsQueueStatus').textContent,/Lake, Orange, Pinellas/);
});

test('merely loading controls never starts or sends SMS',async()=>{
  const h=setup();
  h.context.startAutoSmsStatusPolling();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.requests.length,1);
  assert.equal(h.requests[0].url,'/api/sms/auto/status');
  assert.equal(h.requests[0].method,undefined);
});
test('switching to Pinellas excludes Orange and Lake for both initial and follow-up queues',async()=>{
  for(const start of ['startAutoSmsBatch','startFollowUpSmsBatch']) {
    const h=setup();h.context.selectedCountyKey='Pinellas';
    h.context.savedContactsCache.p2.state='OR';
    await h.context[start]();
    assert.deepEqual(JSON.parse(h.requests[0].body).parcel_ids,['p2']);
  }
});

test('control buttons call only their queue endpoint without changing bot mode',async()=>{
  const h=setup();
  await h.context.controlAutoSmsBatch('pause');
  assert.deepEqual(JSON.parse(h.requests[0].body),{action:'pause'});
  assert.equal(h.requests[0].url,'/api/sms/auto/control');
  assert.ok(h.requests.every(r=>!r.url.includes('/bot/settings') && r.url!=='/api/sms/send'));
});

test('the button is hidden outside saved leads and cannot start an empty list',async()=>{
  const h=setup();
  h.context.currentPipelineView='all';
  h.context.renderAutoSmsQueueStatus();
  assert.equal(h.node('btnStartAutoSms').hidden,true);
  await h.context.startAutoSmsBatch();
  assert.equal(h.requests.length,0);
});

test('Follow Up starts the automatic queue for the filtered list with the follow_up campaign',async()=>{
  const h=setup();
  h.context.renderAutoSmsQueueStatus();
  assert.equal(h.node('btnStartFollowUpSms').hidden,false);
  assert.equal(h.node('btnStartFollowUpSms').disabled,false);
  await h.context.startFollowUpSmsBatch();
  assert.equal(h.requests.length,1);
  assert.equal(h.requests[0].url,'/api/sms/auto/start');
  assert.deepEqual(JSON.parse(h.requests[0].body),{parcel_ids:['p1'],campaign:'follow_up'});
  assert.equal(h.node('btnStartFollowUpSms').disabled,true);
  assert.equal(h.node('btnStartAutoSms').disabled,true);
});

test('Follow Up is hidden outside saved leads and cannot start an empty list',async()=>{
  const h=setup();
  h.context.currentPipelineView='all';
  h.context.renderAutoSmsQueueStatus();
  assert.equal(h.node('btnStartFollowUpSms').hidden,true);
  await h.context.startFollowUpSmsBatch();
  assert.equal(h.requests.length,0);
});

test('Follow Up progress explains automatic sends and manual replies',async()=>{
  const h=setup();
  vm.runInContext("autoSmsQueueCache = {status:'running',campaign:'follow_up',total:4,sent:1,remaining:3};",h.context);
  h.context.renderAutoSmsQueueStatus();
  assert.match(h.node('autoSmsQueueStatus').textContent,/Follow Up.*Running.*1\/4 sent/);
  assert.match(h.node('autoSmsQueueHint').textContent,/90 seconds.*10 property-owner messages.*manually/);
});
