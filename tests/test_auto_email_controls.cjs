const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../frontend/app.js'), 'utf8');
const code = source.slice(source.indexOf('let autoEmailQueueCache ='), source.indexOf('function renderHistoryTable()'));
function setup() {
  const nodes=new Map(), requests=[];
  const node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',disabled:false,hidden:false,classList:{toggle(name,hidden){if(name==='hidden')nodes.get(id).hidden=hidden;}}});return nodes.get(id);};
  let fail=false;
  const context=vm.createContext({document:{getElementById:node},AbortController,setTimeout:()=>1,clearTimeout(){},setInterval:()=>1,
    currentPipelineView:'saved',selectedCountyKey:'Orange',currentFilteredRecords:[{Parcel_ID:'p2',Contact_Parcel_IDs:['p2','alias2']},{Parcel_ID:'p1'},{Parcel_ID:'TEST-1'}],
    savedContactsCache:{p1:{source:'Skip Trace CSV',county:'Orange'},p2:{source:'TruePeopleSearch',county:'Orange'},alias2:{county:'Orange'},'TEST-1':{}},
    async fetch(url, options={}){
      requests.push({url,...options});
      if(fail)return{ok:false,json:async()=>({detail:'No eligible emails'})};
      return{ok:true,json:async()=>url.endsWith('/preview')?{status:'success',eligible:2,skipped:1,template_counts:{lis_pendens:1,quick_cash:1}}
        :{status:'success',queue:{status:options.method?'running':'idle',total:2,sent:0,remaining:2}}};
    }});
  vm.runInContext(source.slice(source.indexOf('function isActiveCountyLead('),source.indexOf('function getActivePipelineDataset()'))+code,context);
  return{context,node,requests,fail(){fail=true;}};
}
test('Start Auto Email uses the entire filtered list and linked contact aliases regardless of source',async()=>{
  const h=setup();h.context.renderAutoEmailQueueStatus();
  assert.equal(h.node('btnStartAutoEmail').hidden,false);
  await h.context.startAutoEmailBatch();
  assert.equal(h.requests.length,1);
  assert.equal(h.requests[0].url,'/api/email/auto/start');
  assert.deepEqual(JSON.parse(h.requests[0].body),{parcel_ids:['p2','alias2','p1']});
  assert.equal(h.node('btnStartAutoEmail').disabled,true);
  assert.equal(h.node('btnPauseAutoEmail').hidden,false);
});
test('loading email controls only checks status and never starts a batch',async()=>{
  const h=setup();h.context.startAutoEmailStatusPolling();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.requests.length,1);
  assert.equal(h.requests[0].url,'/api/email/auto/status');
  assert.equal(h.requests[0].method,undefined);
});
test('email excludes stale rows and contact aliases from another county',async()=>{
  const h=setup();h.context.selectedCountyKey='Pinellas';
  h.context.savedContactsCache.p2.county='Pinellas';
  h.context.savedContactsCache.p2.state='WI';
  await h.context.startAutoEmailBatch();
  assert.deepEqual(JSON.parse(h.requests[0].body),{parcel_ids:['p2']});
});
test('eligibility check is preview-only and shows the template counts',async()=>{
  const h=setup();await h.context.previewAutoEmailBatch();
  assert.equal(h.requests[0].url,'/api/email/auto/preview');
  assert.match(h.node('autoEmailQueuePreview').textContent,/2 eligible.*1 skipped.*foreclosure.*general offer/);
  assert.equal(h.node('btnStartAutoEmail').disabled,false);
});
test('email controls never call SMS or direct-send endpoints',async()=>{
  const h=setup();await h.context.controlAutoEmailBatch('pause');
  assert.equal(h.requests[0].url,'/api/email/auto/control');
  assert.deepEqual(JSON.parse(h.requests[0].body),{action:'pause'});
  assert.ok(h.requests.every(r=>!r.url.includes('/sms/') && r.url!=='/api/email/send'));
});
test('outside saved leads the start button is hidden and an empty list cannot start',async()=>{
  const h=setup();h.context.currentPipelineView='all';h.context.renderAutoEmailQueueStatus();
  assert.equal(h.node('btnStartAutoEmail').hidden,true);
  await h.context.startAutoEmailBatch();assert.equal(h.requests.length,0);
});
test('request failures are visible and release the start button',async()=>{
  const h=setup();h.fail();await h.context.startAutoEmailBatch();
  assert.match(h.node('autoEmailQueueNotice').textContent,/No eligible emails/);
  assert.equal(h.node('btnStartAutoEmail').disabled,false);
});
