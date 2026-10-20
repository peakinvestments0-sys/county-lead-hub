const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../frontend/app.js'),'utf8');
const cut=(start,end)=>{const a=source.indexOf(start),b=source.indexOf(end,a);assert.ok(a>=0&&b>a,`Missing source boundary: ${start} / ${end}`);return source.slice(a,b);};
function harness(county, selectedCounty=county){
  const nodes=new Map(),requests=[];
  const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',innerHTML:'',innerText:'',textContent:'',style:{},options:[],classList:{add(){},remove(){}},appendChild(option){this.options.push(option);}});return nodes.get(id);};
  const templates=JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../data/outreach_templates.json'),'utf8'));
  const c=vm.createContext({document:{getElementById:node,createElement:()=>({})},window:{},console,
    selectedCountyKey:selectedCounty,currentState:'FL',PRESERVED_ACRONYMS:new Set(),
    savedContactsCache:{p1:{owner:'Alice Smith',county,city:'Test City'}},
    liveRecords:[{Parcel_ID:'p1',County:county}],inboxThreadsCache:[],outreachTemplatesCache:templates,
    localStorage:{getItem:()=> '0',setItem(){}},markLeadAsViewed(){},updateSmsCharCount(){},
    formatDisplayAddress:x=>x||'',formatDisplayCity:x=>x||'',
    async fetch(url,options={}){requests.push({url,...options});return{ok:true,json:async()=>url.includes('/settings')?{template:'OLD GATEWAY OPENER'}:{status:'ok',suggestion:'Shared current opener',spread_eval:{},items:[]}};}});
  vm.runInContext(cut('const SMS_TEMPLATES =','document.addEventListener("DOMContentLoaded",')+
    cut('function formatDisplayName(', 'function formatDisplayCity(')+
    cut('function resolveSmsOwnerName(', 'function cycleNextSmsTemplate(')+
    cut('function applySmsTemplate(', 'function updateSmsCharCount(')+
    cut('async function loadSmsSettings()', 'function resolveSmsOwnerName(') ,c);
  return{c,node,requests};
}
test('Orange and Pinellas use the same initial template and the lead county survives a different selected county',()=>{
  const orange=harness('Orange'),pinellas=harness('Pinellas','Orange');
  orange.c.openSmsModal('p1','4072000001','Alice Smith','123 Main St');
  pinellas.c.openSmsModal('p1','7272000001','Alice Smith','123 Main St');
  assert.equal(orange.node('smsMessageText').value,pinellas.node('smsMessageText').value);
  assert.equal(pinellas.node('smsCounty').value,'Pinellas');
  assert.equal(pinellas.c.window.activeSmsLeadContext.county,'Pinellas');
});
test('every initial composer option uses the four approved owner checks, including when the template cache is unavailable',()=>{
  const expected = [
    "Hello, I'm trying to locate the property owner of 123 Main St. Would that be you?",
    "Hi, I'm looking for the homeowner at 123 Main St. Is that you?",
    "Hello, is this the right person to reach about ownership of 123 Main St?",
    "Hi there, I'm trying to get in touch with the owner of 123 Main St. Are you the owner?"
  ];
  for (const county of ['Pinellas','Orange']) {
    for (const cacheAvailable of [true,false]) {
      const h=harness(county);h.c.openSmsModal('p1','7272000001','Alice Smith','123 Main St');
      if (!cacheAvailable) h.c.outreachTemplatesCache=null;
      ['casual_direct','quick_question','neighbor_investor','quick_checkin'].forEach((id,i)=>{
        h.c.applySmsTemplate(id);
        assert.equal(h.node('smsMessageText').value,expected[i]);
      });
    }
  }
});
test('legacy template IDs resolve to the shared configured templates',()=>{
  const h=harness('Pinellas');h.c.openSmsModal('p1','7272000001','Alice Smith','123 Main St');
  h.c.applySmsTemplate('single_list');const legacy=h.node('smsMessageText').value;
  h.c.applySmsTemplate('quick_question');assert.equal(h.node('smsMessageText').value,legacy);
  assert.equal(legacy, "Hi, I'm looking for the homeowner at 123 Main St. Is that you?");
});
test('gateway loading cannot overwrite the global initial opener',async()=>{
  const h=harness('Pinellas');await h.c.loadSmsSettings();
  h.c.openSmsModal('p1','7272000001','Alice Smith','123 Main St');
  h.c.applySmsTemplate('cash_offer');
  assert.ok(!h.node('smsMessageText').value.includes('OLD GATEWAY'));
});
test('Copilot initial suggestion requests the same selected template and actual lead county',async()=>{
  const h=harness('Pinellas','Orange');
  h.c.openSmsModal('p1','7272000001','Alice Smith','123 Main St');
  vm.runInContext(cut('async function generateEmmaCopilotSuggestion()', 'function applyEmmaCopilotSuggestion('),h.c);
  await h.c.generateEmmaCopilotSuggestion();
  const request=h.requests.find(r=>r.url==='/api/bot/suggest');
  const payload=JSON.parse(request.body);
  assert.equal(payload.county,'Pinellas');
  assert.equal(payload.opener_angle,h.node('smsTemplateSelect').value);
});
