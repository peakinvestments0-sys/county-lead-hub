const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../frontend/app.js'), 'utf8');
function extract(start, end) { return source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start))); }
function harness() {
  const nodes = new Map();
  const node = id => { if (!nodes.has(id)) nodes.set(id, {value:'',innerText:'',classList:{add(){},remove(){},toggle(name,value){if(name==='hidden') nodes.get(id).hidden=value;}}}); return nodes.get(id); };
  const snapshot = {Parcel_ID:'123',Property_Address:'10 Main St',Lead_Type:'Lis Pendens',All_Lead_Types:['Lis Pendens','Civil Judgment'],
    Is_Stacked_Distress:'Yes',Distress_Stack_Notes:'DOUBLE DISTRESS: Lis Pendens + Civil Judgment',Has_Confirmed_Probate:'No'};
  const context = vm.createContext({window:{excludeCondos:false},document:{getElementById:node},currentPipelineView:'saved',selectedCountyKey:'Orange',currentFilter:'stacked',
    liveRecords:[{Parcel_ID:'123',Property_Address:'10 Main St',Lead_Type:'Lis Pendens'}],
    savedContactsCache:{'123':{county:'Orange',owner:'Alice',email:'old@example.org',last_email_sent:'yesterday',matched_parcel_id:'123',property_match:{record:snapshot}},
      'SKIP-1':{county:'Orange',source:'Skip Trace CSV',owner:'Alice',address:'10 Main St',phone:'4072000001',matched_parcel_id:'123',property_match:{record:snapshot}},
      'SKIP-2':{county:'Orange',source:'Skip Trace CSV',address:'11 Main St',distress_category:'Civil Judgment'}},
    isCondoOrUnit:()=>false,hasLeadPhoto:()=>false,updateExportButtonsUI(){},renderLiveTable(records){context.rendered=records;}});
  vm.runInContext(extract('function isActiveCountyLead(', 'function isCodeViolationLead(') +
    extract('function isCodeViolationLead(', 'function filterLiveRecords(') +
    extract('function getFilteredPipelineDataset(', 'function updateFilterCounts(') +
    extract('function searchLiveTable()', 'function setupSearchFilter(') +
    extract('function getDefaultEmailTemplate(', 'function openEmailModal('), context);
  return {context,node};
}
test('saved view collapses aliases, retains contact IDs/history and uses persisted distress offline',()=>{
  const {context:c}=harness();
  c.liveRecords=[];
  const records=c.getActivePipelineDataset();
  assert.equal(records.length,2);
  const record=records.find(r=>r.Matched_Parcel_ID==='123');
  assert.equal(record.Parcel_ID,'SKIP-1');
  assert.equal(record.Saved_Email,'old@example.org');
  assert.equal(record.Last_Email_Sent,'yesterday');
  assert.equal(record.Is_Stacked_Distress,'Yes');
  assert.equal(record.All_Lead_Types.length,2);
  assert.equal(c.getSavedPropertyCount(),2);
});
test('switching counties isolates saved rows, counts, search, and CSV exports while retaining both lists',()=>{
  const {context:c,node}=harness();
  c.savedContactsCache['PIN-1']={county:'Pinellas',state:'WI',source:'Skip Trace CSV',address:'12 Main St',phone:'7272000001'};
  c.savedContactsCache['OTHER-COUNTY']={county:'Lake',state:'FL',source:'Skip Trace CSV',address:'13 Main St'};
  c.savedContactsCache['UNKNOWN']={source:'Skip Trace CSV',address:'14 Main St'};
  c.liveRecords.push({Parcel_ID:'OLD-LIVE',County:'Orange',Property_Address:'15 Main St',Saved_Phone:'4072000002'});
  c.selectedCountyKey='Pinellas';c.currentFilter='all';
  assert.deepEqual(Array.from(c.getActivePipelineDataset(),r=>r.Parcel_ID),['PIN-1']);
  assert.equal(c.getSavedPropertyCount(),1);
  node('liveSearchInput').value='Main';c.searchLiveTable();
  assert.deepEqual(Array.from(c.rendered,r=>r.Parcel_ID),['PIN-1']);
  c.selectedExportCategories=new Set(['all']);
  c.generateAndDownloadCsv=(rows,name)=>{c.exported={rows,name};};
  vm.runInContext(extract('function getRecordsForCategories(', 'function updateExportButtonsUI(')+
    extract('function exportCategoryCsv()', 'function generateAndDownloadCsv('),c);
  c.exportCategoryCsv();
  assert.deepEqual(Array.from(c.exported.rows,r=>r.County),['Pinellas']);
  assert.match(c.exported.name,/^Pinellas_County_ALL_1_Leads_/);
  c.exportEntireCountyCsv();
  assert.deepEqual(Array.from(c.exported.rows,r=>r.County),['Pinellas']);
  c.selectedCountyKey='Orange';
  assert.equal(c.getSavedPropertyCount(),2);
  assert.ok(c.getActivePipelineDataset().every(r=>r.County==='Orange' || r.Parcel_ID==='OLD-LIVE'));
  assert.ok(c.savedContactsCache['PIN-1']);
});
test('saved view carries one-time SMS reset state without deleting the old send timestamp',()=>{
  const {context:c}=harness();
  c.savedContactsCache['SKIP-1'].last_sms_sent='2026-10-13 08:00:00';
  c.savedContactsCache['SKIP-1'].sms_initial_resend_pending=true;
  const record=c.getActivePipelineDataset().find(r=>r.Parcel_ID==='SKIP-1');
  assert.equal(record.Sms_Initial_Resend_Pending,true);
  assert.equal(record.Last_Sms_Sent,'2026-10-13 08:00:00');
});
test('quick search preserves Double Distress instead of including single-distress leads',()=>{
  const {context:c,node}=harness();
  node('liveSearchInput').value='Main St';
  c.searchLiveTable();
  assert.equal(c.rendered.length,1);
  assert.equal(c.rendered[0].Parcel_ID,'SKIP-1');
});
test('email selection requires actual probate, ignoring trust, stacked flag and selected Probate tab',()=>{
  const {context:c}=harness();
  c.currentFilter='probate';
  assert.equal(c.getDefaultEmailTemplate({Lead_Type:'Lis Pendens',Is_Stacked_Distress:'Yes',Is_Trust_Or_Estate:'Yes'}),'lis_pendens');
  assert.equal(c.getDefaultEmailTemplate({Lead_Type:'Code Violation',Is_Stacked_Distress:'Yes'}),'code_violation');
  assert.equal(c.getDefaultEmailTemplate({Lead_Type:'Death Certificate'}),'quick_cash');
  assert.equal(c.getDefaultEmailTemplate({Lead_Type:'Probate (Death Certificate)'}),'quick_cash');
  assert.equal(c.getDefaultEmailTemplate({Lead_Type:'Probate Court Paper'}),'probate');
  assert.equal(c.getDefaultEmailTemplate({Lead_Type:'Lis Pendens',Has_Confirmed_Probate:'Yes',All_Lead_Types:['Lis Pendens','Probate']}),'probate');
  assert.equal(c.getDefaultEmailTemplate({Lead_Type:'Civil Judgment'}),'quick_cash');
});

test('choosing foreclosure does not reveal a probate offer for a non-probate property',()=>{
  const {context:c,node}=harness();
  c.window.activeEmailLeadRecord={Lead_Type:'Lis Pendens',All_Lead_Types:['Lis Pendens','Civil Judgment'],Has_Confirmed_Probate:'No'};
  c.applyEmailTemplate=()=>{};
  vm.runInContext(extract('window.selectDoubleDistressEmail =', 'function closeEmailModal('),c);
  c.window.selectDoubleDistressEmail('lis_pendens');
  assert.equal(node('btnEmailSwitchProbate').hidden,true);
  assert.equal(node('btnEmailSwitchLp').hidden,false);
  c.window.selectDoubleDistressEmail('probate');
  assert.equal(node('emailTemplateSelect').value,'lis_pendens');
});
