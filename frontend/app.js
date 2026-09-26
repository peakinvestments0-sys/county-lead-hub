// Florida Lead Hub Client Application Controller
let currentState = localStorage.getItem("flh_state") || "FL";
let allStates = [];
let allCounties = [];
let selectedCountyKey = "Pinellas";
let liveRecords = [];
let currentFilter = "all";
let currentPipelineView = "all"; // 'all' | 'saved' | 'history'
let customCategories = [];
let savedContactsCache = {};
let outreachHistoryCache = [];
let smsSettingsCache = null;
let pandadocSettingsCache = null;
let outreachTemplatesCache = null;
let activeTemplatesChannel = 'sms';
let selectedTemplateId = null;

const SMS_TEMPLATES = {
  cash_offer: "Hi {FirstName}, I noticed your property at {Address}. I'm an active local investor and wanted to see if you would consider a quick all-cash offer as-is? Let me know!",
  pre_foreclosure: "Hi {FirstName}, I saw the recent county court filing regarding {Address}. If you need a fast, private resolution before the auction date, we can purchase cash as-is and cover closing costs. Would you be open to a quick call?",
  probate_estate: "Hi {FirstName}, my condolences on the family estate regarding {Address}. If you or the heirs are planning to sell the property without repairs or realtor fees, I would love to make a fair as-is cash offer. Let me know if you'd like to discuss.",
  code_violation: "Hi {FirstName}, I was looking at properties in {City} and saw {Address}. If the county code requirements or repairs are becoming a headache, we buy houses in any condition with zero cleanout needed. Would you consider an offer?",
  casual_followup: "Hi {FirstName}, just following up regarding {Address} in {City}. Are you still open to selling if the price and terms make sense? Thanks!"
};

document.addEventListener("DOMContentLoaded", () => {
  fetchStates();
  fetchStats(currentState);
  fetchCounties(currentState);
  fetchCustomCategories();
  fetchSavedContacts();
  fetchOutreachHistory();
  loadSmsSettings();
  loadEmailSettings();
  loadPandadocSettings();
  fetchOutreachTemplates();
  loadLiveCountyLeads("Pinellas", null, currentState);
  setupSearchFilter();
});

async function fetchStates() {
  try {
    const res = await fetch("/api/states");
    if (res.ok) {
      allStates = await res.json();
      const sel = document.getElementById("stateSelect");
      if (sel) {
        sel.innerHTML = "";
        allStates.forEach(s => {
          const opt = document.createElement("option");
          opt.value = s.code;
          opt.textContent = `${s.name} (${s.code})`;
          if (s.code === currentState) opt.selected = true;
          sel.appendChild(opt);
        });
      }
      updateActiveStateUI(currentState);
    }
  } catch (err) {
    console.error("Error fetching states:", err);
  }
}

function updateActiveStateUI(stateCode) {
  const stateObj = allStates.find(s => s.code === stateCode) || {
    code: "FL", name: "Florida", icon: "🌴", script_text: "Florida", tagline: "Opportunity Lives Here"
  };

  const iconEl = document.getElementById("activeStateIcon");
  if (iconEl) iconEl.innerText = stateObj.icon || "🌴";

  const scriptEl = document.getElementById("heroStateScript");
  if (scriptEl) scriptEl.innerText = stateObj.script_text || stateObj.name;

  const tagEl = document.getElementById("heroStateTagline");
  if (tagEl) tagEl.innerText = stateObj.tagline || `${stateObj.name} Real Estate`;

  const heroTitle = document.getElementById("heroTitle");
  if (heroTitle) heroTitle.innerText = `Find Property Leads in ${stateObj.name}`;
}

async function handleStateChange(stateCode) {
  currentState = stateCode;
  localStorage.setItem("flh_state", stateCode);
  updateActiveStateUI(stateCode);
  await fetchStats(stateCode);
  await fetchCounties(stateCode);
}

async function fetchStats(state = currentState) {
  try {
    const res = await fetch(`/api/stats?state=${encodeURIComponent(state)}`);
    if (res.ok) {
      const data = await res.json();
      document.getElementById("statTotalRecords").innerText = data.total_records;
      document.getElementById("statUniqueProps").innerText = data.unique_properties;
      document.getElementById("statCounties").innerText = data.counties_available;
      document.getElementById("statFreshness").innerText = data.updated_status;
    }
  } catch (err) {
    console.error("Error fetching global stats:", err);
  }
}

async function fetchCounties(state = currentState) {
  try {
    const res = await fetch(`/api/counties?state=${encodeURIComponent(state)}`);
    if (!res.ok) return;
    allCounties = await res.json();

    // Select default county if current county is not in this state's counties
    const exists = allCounties.some(c => c.key === selectedCountyKey);
    if (!exists && allCounties.length > 0) {
      selectedCountyKey = allCounties[0].key;
    }

    // Populate Hero County Dropdown
    const select = document.getElementById("heroCountySelect");
    if (select) {
      select.innerHTML = "";
      allCounties.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c.key;
        opt.textContent = `${c.name} County ${c.has_master ? `(${c.records.toLocaleString()} records)` : ""}`;
        if (c.key === selectedCountyKey) opt.selected = true;
        select.appendChild(opt);
      });
    }

    renderCountyGrid(allCounties);
    updateCategoryCardLinks(selectedCountyKey);
  } catch (err) {
    console.error("Error fetching counties:", err);
  }
}

function renderCountyGrid(counties) {
  const grid = document.getElementById("countyGrid");
  if (!grid) return;
  grid.innerHTML = "";

  counties.forEach(c => {
    const isSelected = c.key === selectedCountyKey;
    const card = document.createElement("div");
    card.className = `glass-surface county-card-hover rounded-xl p-3.5 border border-slate-800 transition cursor-pointer relative overflow-hidden group ${isSelected ? 'active-county-ring' : ''}`;
    card.onclick = () => selectCounty(c.key);

    const isLive = c.status.includes("LIVE") || c.has_master;
    const statusColor = isLive ? "text-emerald-400" : "text-amber-400";
    const dotColor = isLive ? "bg-emerald-400" : "bg-amber-400";

    card.innerHTML = `
      <div class="h-20 -mx-3.5 -mt-3.5 mb-3 bg-cover bg-center" style="background-image: url('${c.img}')">
        <div class="w-full h-full bg-gradient-to-t from-[#0a101d] via-[#0a101d]/60 to-transparent"></div>
      </div>
      <div class="font-bold text-white text-sm flex items-center justify-between">
        <span>${c.name}</span>
        ${c.has_master ? '<span class="w-2 h-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50" title="Parcel database installed"></span>' : ''}
      </div>
      <div class="text-xs text-slate-400 mt-0.5">${c.records_formatted}</div>
      <div class="text-[10px] text-slate-500 mt-1">Updated ${c.updated}</div>
      <div class="flex items-center gap-1.5 mt-2 text-[11px] font-semibold ${statusColor}">
        <span class="w-1.5 h-1.5 rounded-full ${dotColor}"></span> ${c.status}
      </div>
    `;
    grid.appendChild(card);
  });

  // Append "+ More Counties Coming Soon" Card
  const moreCard = document.createElement("div");
  moreCard.className = "glass-surface rounded-xl p-4 border border-dashed border-slate-700 flex flex-col items-center justify-center text-center cursor-pointer hover:border-blue-500 transition";
  moreCard.onclick = () => alert("Additional Florida counties (Duval, Seminole, Brevard, etc.) can be dropped into the data/ directory and will automatically appear!");
  moreCard.innerHTML = `
    <div class="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center text-slate-400 mb-2">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"/></svg>
    </div>
    <div class="text-xs font-bold text-slate-300">More Counties</div>
    <div class="text-[10px] text-slate-500">Coming Soon</div>
  `;
  grid.appendChild(moreCard);
}

let activeLeadsFetch = null;

async function selectCounty(key, targetFilter = null) {
  selectedCountyKey = key;
  updateCategoryCardLinks(key);
  const select = document.getElementById("heroCountySelect");
  if (select) select.value = key;
  renderCountyGrid(allCounties);

  const countyObj = allCounties.find(c => c.key === key);
  const setupBox = document.getElementById("setupNoticeBox");
  const tableContainer = document.getElementById("liveTableContainer");
  const filterPills = document.getElementById("liveFilterPills");

  if (countyObj && !countyObj.has_master && key !== "Pinellas") {
    // Show setup box
    setupBox.classList.remove("hidden");
    tableContainer.classList.add("hidden");
    filterPills.classList.add("hidden");

    document.getElementById("setupCountyName").innerText = `${countyObj.name} County`;
    document.getElementById("setupTargetDir").innerText = countyObj.target_dir || `data/${countyObj.name.toLowerCase()}/`;
    document.getElementById("setupDownloadBtn").href = countyObj.master_parcel_download_url || "#";

    document.getElementById("liveCountyTitle").innerText = `${countyObj.name} County (Awaiting Parcel File)`;
    document.getElementById("liveStatusBadge").innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span> Needs Setup`;
    document.getElementById("liveCountySub").innerText = `Download master parcel file and save into ${countyObj.target_dir || `data/${countyObj.name}/`} to unlock matching.`;
  } else {
    // Live county (Pinellas)
    setupBox.classList.add("hidden");
    tableContainer.classList.remove("hidden");
    filterPills.classList.remove("hidden");
    
    await loadLiveCountyLeads(key, targetFilter, currentState);
  }
}

async function loadLiveCountyLeads(countyKey, initialFilter = null, state = currentState) {
  if (initialFilter) {
    currentFilter = initialFilter;
  }

  // If records are already in memory, simply filter
  if (liveRecords && liveRecords.length > 0 && selectedCountyKey === countyKey) {
    filterLiveRecords(currentFilter);
    return;
  }

  // If a fetch is currently in flight, wait for it
  if (activeLeadsFetch) {
    await activeLeadsFetch;
    filterLiveRecords(currentFilter);
    return;
  }

  try {
    await fetchSavedContacts();
    activeLeadsFetch = fetch(`/api/leads?county=${encodeURIComponent(countyKey)}&state=${encodeURIComponent(state || currentState)}`);
    const res = await activeLeadsFetch;
    activeLeadsFetch = null;
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById("liveCountyTitle").innerText = `${data.county} County Live Distressed Leads`;
    document.getElementById("liveCountySub").innerText = `Cross-referenced against ${data.total_records_in_db?.toLocaleString() || '437,559'} official county master parcels with clean owner names and absentee indicators.`;
    document.getElementById("liveStatusBadge").innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> ${data.kpis.matched_count.toLocaleString()} Verified Properties`;

    // Filter out Corporate LLCs completely so wholesalers only see individual/trust/probate homeowners
    const validHumanLeads = (data.records || []).filter(r => !isCorporateOwner(r));
    liveRecords = validHumanLeads;

    // Counts (Strictly non-corporate)
    const allCnt = validHumanLeads.length;
    const pCountAll = document.getElementById("pipelineCountAll");
    if (pCountAll) pCountAll.innerText = allCnt.toLocaleString();

    updateSavedPipelineCount();
    updateFilterCounts();
    filterLiveRecords(currentFilter || "all");
  } catch (err) {
    activeLeadsFetch = null;
    console.error("Error loading live leads:", err);
  }
}

function isCorporateOwner(r) {
  const entity = (r.Owner_Entity_Type || "").toLowerCase();
  const name = (r.Clean_Full_Name || r.Clean_Last_Name || "").toLowerCase();
  return entity.includes("llc") || entity.includes("company") || entity.includes("corp") || entity.includes("inc") ||
         name.includes("llc") || name.includes(" inc") || name.includes(" corp") || name.includes("company") || name.includes("bank") || name.includes("holdings");
}


function renderLiveTable(records) {
  const tbody = document.getElementById("liveTableBody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!records || records.length === 0) {
    if (currentPipelineView === "saved") {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" class="p-10 text-center">
            <div class="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-400 mb-3 text-xl">
              ⭐
            </div>
            <div class="font-bold text-white text-base">No Saved Leads in Your Pipeline Yet</div>
            <p class="text-xs text-slate-400 max-w-md mx-auto mt-1 mb-4">Click "Free Trace" on any distressed property in the All County Leads tab to find the homeowner's phone number or email. Once found, they will automatically appear here in your active pipeline.</p>
            <button type="button" onclick="switchPipelineView('all')" class="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs inline-flex items-center gap-2 transition cursor-pointer">
              🌴 Browse All County Leads
            </button>
          </td>
        </tr>`;
      return;
    }
    if (currentFilter === "tax_liens") {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" class="p-8 text-center">
            <div class="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-400 mb-3">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            </div>
            <div class="font-bold text-white text-sm">No Tax Liens Loaded for ${selectedCountyKey} County</div>
            <p class="text-xs text-slate-400 max-w-md mx-auto mt-1 mb-4">No tax certificates or tax delinquent properties loaded for this county yet. Drop a tax lien CSV into <code class="mono text-cyan-300 bg-slate-900 px-2 py-0.5 rounded">data/${selectedCountyKey.toLowerCase()}/</code> or click below to upload.</p>
            <button onclick="openImportModal('tax_liens')" class="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs inline-flex items-center gap-2 transition cursor-pointer">
              + Upload Tax Liens CSV
            </button>
          </td>
        </tr>`;
    } else {
      tbody.innerHTML = `<tr><td colspan="8" class="p-8 text-center text-slate-400 font-semibold">No records found matching current filter for ${selectedCountyKey} County.</td></tr>`;
    }
    return;
  }

  records.forEach(r => {
    const isAbsentee = (r.Absentee_Status || "").includes("Out-of-State");
    const isLlc = (r.Owner_Entity_Type || "").includes("LLC");
    const isTrust = (r.Owner_Entity_Type || "").includes("Trust") || r.Is_Trust_Or_Estate === "Yes";
    const mktVal = parseFloat(r.Market_Value || 0);

    const isStacked = r.Is_Stacked_Distress === "Yes";
    const isLp = r.Lead_Type === "Lis Pendens";
    const isProbate = r.Lead_Type === "Probate";
    const isLpTrust = isLp && (r.Is_Trust_In_LP === "Yes" || r.Is_Trust_Or_Estate === "Yes");

    let leadBadgeClass = "bg-rose-500/15 text-rose-300 border border-rose-500/30";
    let leadBadgeIcon = "🚨 Code Violation";

    if (isProbate) {
      leadBadgeClass = "bg-indigo-500/15 text-indigo-300 border border-indigo-500/30";
      leadBadgeIcon = "⚖️ Probate Court";
    } else if (isLp) {
      leadBadgeClass = "bg-purple-500/15 text-purple-300 border border-purple-500/30";
      leadBadgeIcon = "📄 Lis Pendens";
    } else if ((r.Lead_Type || "").includes("Tax Lien")) {
      leadBadgeClass = "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30";
      leadBadgeIcon = "💰 Tax Lien";
    }

    const pQuery = encodeURIComponent(r.Parcel_ID || "");
    const addrQuery = encodeURIComponent(`${r.Property_Address || ""}, Pinellas, FL`);
    
    // Pinellas STRAP calculation: Range(2) + Township(2) + Section(2) + Subdivision(5) + Block(3) + Lot(4)
    let paUrl = "https://www.pcpao.gov/quick-search";
    const pidTrim = (r.Parcel_ID || "").trim();
    const pidParts = pidTrim.split("-");
    if (pidParts.length === 6) {
      const strap = `${pidParts[2]}${pidParts[1]}${pidParts[0]}${pidParts[3]}${pidParts[4]}${pidParts[5]}`;
      paUrl = `https://www.pcpao.gov/property-details?s=${strap}`;
    } else if (pidTrim.replace(/[^0-9A-Za-z]/g, "").length === 18) {
      paUrl = `https://www.pcpao.gov/property-details?s=${pidTrim.replace(/[^0-9A-Za-z]/g, "")}`;
    }
    const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${addrQuery}`;

    // 1-Click Free Skip Trace URL calculation (TruePeopleSearch)
    let skipName = "";
    if (r.Clean_First_Name && r.Clean_Last_Name) {
      skipName = `${r.Clean_First_Name} ${r.Clean_Last_Name}`;
    } else if (r.Clean_Full_Name) {
      skipName = r.Clean_Full_Name;
    } else if (r.Clean_Last_Name) {
      skipName = r.Clean_Last_Name;
    }
    // Clean out legal markers like TR, TRUSTEE, ESTATE, ET AL, DECD, OF
    skipName = (skipName || "").replace(/\b(TR|TRE|TRUSTEE|ESTATE|EST|OF|DECD|DECEASED|ET|AL|LIFE|LE)\b/gi, " ").replace(/\s+/g, " ").trim();

    // Prefer mailing address city & state where owner currently lives (especially out-of-state/absentee)
    const skipCity = (r.Mailing_City || r.Property_City || "St Petersburg").trim();
    const skipState = (r.Mailing_State || "FL").trim();
    const skipLoc = `${skipCity}, ${skipState}`;
    
    // Hash parameters pass lead context seamlessly to the Chrome extension
    const skipTraceUrl = `https://www.truepeoplesearch.com/results?name=${encodeURIComponent(skipName)}&citystatezip=${encodeURIComponent(skipLoc)}#lead_hub_pid=${encodeURIComponent(r.Parcel_ID || '')}&county=${encodeURIComponent(selectedCountyKey)}&owner=${encodeURIComponent(skipName)}&addr=${encodeURIComponent(r.Property_Address || '')}`;

    const savedContact = savedContactsCache[r.Parcel_ID] || ((r.Saved_Phone || r.Saved_Email) ? { phone: r.Saved_Phone, email: r.Saved_Email } : null);
    const savedPhone = savedContact ? savedContact.phone : null;
    const savedEmail = savedContact ? (savedContact.email || r.Saved_Email) : (r.Saved_Email || null);
    const lastSmsSent = savedContact?.last_sms_sent || r.Last_Sms_Sent;
    const lastEmailSent = savedContact?.last_email_sent || r.Last_Email_Sent;

    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-800/40 transition cursor-pointer";

    tr.innerHTML = `
      <td class="px-4 py-3">
        <div class="flex flex-col gap-1 items-start">
          <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${leadBadgeClass}">
            ${leadBadgeIcon}
          </span>
          ${isStacked ? `
            <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[9px] font-black bg-gradient-to-r from-rose-500/25 to-amber-500/25 text-amber-300 border border-amber-500/50 shadow-sm animate-pulse" title="${r.Distress_Stack_Notes || 'Pre-Foreclosure + Probate Court Case'}">
              🔥 DOUBLE DISTRESS
            </span>
          ` : ''}
          ${isLpTrust && !isStacked ? `
            <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[9px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
              🏛️ Trust / Estate
            </span>
          ` : ''}
        </div>
        <div class="text-[10px] text-emerald-400 font-semibold mt-1">✓ ${r.Match_Method || 'Exact PIN'}</div>
        ${r.Distress_Stack_Notes ? `<div class="text-[9px] text-amber-300/90 font-medium mt-0.5 max-w-[210px] leading-tight" title="${r.Distress_Stack_Notes}">${r.Distress_Stack_Notes}</div>` : ''}
      </td>
      <td class="px-4 py-3">
        <div class="font-bold text-white text-xs">${r.Property_Address || 'N/A'}</div>
        <div class="text-[10px] text-slate-400">${r.Property_City || 'ST PETERSBURG'}, FL ${r.Property_Zip || ''}</div>
      </td>
      <td class="px-4 py-3">
        <div class="font-bold text-blue-300 text-xs">${r.Clean_Full_Name || r.Clean_Last_Name || 'Unknown Owner'}</div>
        <div class="text-[10px] text-slate-500 mono">PIN: ${r.Parcel_ID || 'N/A'}</div>
        ${savedPhone ? `
          <div class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-[10px] font-bold mt-1 shadow-sm">
            <span>📱</span> <span>${savedPhone}</span>
          </div>
          ${lastSmsSent ? `<div class="text-[9px] text-emerald-400/80 mt-0.5 font-medium">✓ Texted ${lastSmsSent}</div>` : ''}
        ` : ''}
        ${savedEmail ? `
          <div class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 text-[10px] font-bold mt-1 shadow-sm">
            <span>✉️</span> <span>${savedEmail}</span>
          </div>
          ${lastEmailSent ? `<div class="text-[9px] text-cyan-400/80 mt-0.5 font-medium">✓ Emailed ${lastEmailSent}</div>` : ''}
        ` : ''}
      </td>
      <td class="px-4 py-3">
        <span class="px-2 py-0.5 rounded-md text-[10px] font-semibold ${isLlc ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30' : (isTrust ? 'bg-purple-500/15 text-purple-300 border border-purple-500/30' : 'bg-slate-800 text-slate-300')}">
          ${isTrust && !isLlc ? '🏛️ Trust / Estate' : (r.Owner_Entity_Type || 'Individual')}
        </span>
      </td>
      <td class="px-4 py-3">
        <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${isAbsentee ? 'bg-purple-500/15 text-purple-300 border border-purple-500/30' : 'bg-slate-800 text-slate-400'}">
          ${isAbsentee ? '✈️ ' : ''}${r.Absentee_Status || 'Owner Occupied'}
        </span>
        ${r.Mailing_State && isAbsentee ? `<div class="text-[10px] text-purple-400 mt-0.5">Lives in ${r.Mailing_State}</div>` : ''}
      </td>
      <td class="px-4 py-3">
        <div class="text-xs font-semibold text-slate-200">${r.Living_Sqft && r.Living_Sqft !== 'nan' ? `${r.Living_Sqft} sqft` : '-'}</div>
        <div class="text-[10px] text-slate-500">Built ${r.Year_Built && r.Year_Built !== 'nan' ? r.Year_Built : '-'}</div>
      </td>
      <td class="px-4 py-3 text-right mono font-bold text-white">
        ${mktVal > 0 ? `$${mktVal.toLocaleString()}` : '-'}
      </td>
      <td class="px-4 py-3 text-center whitespace-nowrap min-w-[320px]">
        <div class="flex items-center justify-center gap-1.5">
          <button type="button" onclick="openContractModal('${r.Parcel_ID}', '${escapeAttr(savedPhone || '')}', '${escapeAttr(savedEmail || '')}', '${escapeAttr(skipName)}', '${escapeAttr(r.Property_Address || '')}', '${escapeAttr(r.Property_City || 'St Petersburg')}', '${escapeAttr(r.Property_Zip || '')}', ${mktVal})" class="px-2.5 py-1 rounded bg-purple-600 hover:bg-purple-500 text-white text-[10px] font-bold transition flex items-center gap-1 shadow-md shadow-purple-600/30 cursor-pointer" title="Generate 1-Page Wholesale Purchase Agreement & E-Sign via PandaDoc">
            <span>📝</span> <span>Contract</span>
          </button>
          ${savedPhone ? `
            <button type="button" onclick="openSmsModal('${r.Parcel_ID}', '${savedPhone}', '${escapeAttr(skipName)}', '${escapeAttr(r.Property_Address || '')}')" class="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] font-bold transition flex items-center gap-1 shadow-md shadow-emerald-600/30 cursor-pointer" title="Send Wholesale SMS Offer via Android Gateway">
              <span>💬</span> <span>SMS</span>
            </button>
          ` : ''}
          ${savedEmail ? `
            <button type="button" onclick="openEmailModal('${r.Parcel_ID}', '${savedEmail}', '${escapeAttr(skipName)}', '${escapeAttr(r.Property_Address || '')}')" class="px-2.5 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-[10px] font-bold transition flex items-center gap-1 shadow-md shadow-cyan-600/30 cursor-pointer" title="Send Wholesale HTML Offer via SMTP2GO">
              <span>✉️</span> <span>Email</span>
            </button>
          ` : ''}
          ${!savedPhone && !savedEmail ? `
            <a href="${skipTraceUrl}" target="_blank" rel="noopener noreferrer" class="px-2 py-1 rounded bg-amber-500/20 hover:bg-amber-500 hover:text-slate-950 text-amber-300 text-[10px] font-bold transition flex items-center gap-1 shadow-sm border border-amber-500/30" title="Free 1-Click Skip Trace (TruePeopleSearch) for ${skipName || 'Owner'}">
              <span>📞</span> <span>Free Trace</span>
            </a>
          ` : `
            <a href="${skipTraceUrl}" target="_blank" rel="noopener noreferrer" class="px-1.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] transition" title="Search additional phone numbers & emails">
              🔄
            </a>
          `}
          <a href="${paUrl}" target="_blank" class="px-2 py-1 rounded bg-slate-800 hover:bg-blue-600 hover:text-white text-slate-300 text-[10px] font-semibold transition" title="View Property Appraiser">
            🔍 PCPAO
          </a>
          <a href="${mapsUrl}" target="_blank" class="px-2 py-1 rounded bg-slate-800 hover:bg-emerald-600 hover:text-white text-slate-300 text-[10px] font-semibold transition" title="Google Maps">
            🗺️ Maps
          </a>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function filterLiveRecords(type) {
  currentFilter = type;
  
  // Highlight tab with correct element IDs
  const tabBtnMap = {
    all: "btnTabAll",
    stacked: "btnTabStacked",
    lis_pendens: "btnTabLp",
    lp_trust: "btnTabLpTrust",
    probate: "btnTabProbate",
    code: "btnTabCode",
    absentee: "btnTabAbsentee",
    tax_liens: "btnTabTax",
    trust: "btnTabTrust"
  };

  Object.entries(tabBtnMap).forEach(([t, btnId]) => {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    if (t === type) {
      if (t === 'stacked') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold bg-amber-500 text-slate-950 shadow-md cursor-pointer whitespace-nowrap";
      } else {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-blue-600 text-white shadow-sm cursor-pointer whitespace-nowrap";
      }
    } else {
      if (t === 'stacked') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-amber-300 hover:text-white border border-amber-500/40 transition cursor-pointer whitespace-nowrap";
      } else if (t === 'lp_trust') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-purple-300 hover:text-white transition cursor-pointer whitespace-nowrap";
      } else if (t === 'probate') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-indigo-300 hover:text-white transition cursor-pointer whitespace-nowrap";
      } else if (t === 'tax_liens') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-rose-300 hover:text-white transition cursor-pointer whitespace-nowrap";
      } else {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-slate-300 hover:text-white transition cursor-pointer whitespace-nowrap";
      }
    }
  });

  if (!liveRecords) return;

  const dataset = (currentPipelineView === "saved")
    ? liveRecords.filter(r => r.Parcel_ID && (savedContactsCache[r.Parcel_ID] || r.Saved_Phone || r.Saved_Email))
    : liveRecords;

  if (type === "all") {
    renderLiveTable(dataset);
  } else if (type === "stacked") {
    renderLiveTable(dataset.filter(r => r.Is_Stacked_Distress === "Yes"));
  } else if (type === "lis_pendens") {
    renderLiveTable(dataset.filter(r => r.Lead_Type === "Lis Pendens"));
  } else if (type === "lp_trust") {
    renderLiveTable(dataset.filter(r => r.Lead_Type === "Lis Pendens" && (r.Is_Trust_In_LP === "Yes" || r.Is_Trust_Or_Estate === "Yes")));
  } else if (type === "probate") {
    renderLiveTable(dataset.filter(r => r.Lead_Type === "Probate"));
  } else if (type === "code") {
    renderLiveTable(dataset.filter(r => r.Lead_Type === "Code Violation"));
  } else if (type === "absentee") {
    renderLiveTable(dataset.filter(r => (r.Absentee_Status || "").includes("Out-of-State")));
  } else if (type === "trust") {
    renderLiveTable(dataset.filter(r => (r.Owner_Entity_Type || "").includes("Trust") || r.Lead_Type === "Probate" || r.Is_Trust_Or_Estate === "Yes"));
  } else if (type === "tax_liens") {
    renderLiveTable(dataset.filter(r => (r.Lead_Type || "").includes("Tax Lien")));
  }
}

function updateFilterCounts() {
  if (!liveRecords) return;
  const dataset = (currentPipelineView === "saved")
    ? liveRecords.filter(r => r.Parcel_ID && (savedContactsCache[r.Parcel_ID] || r.Saved_Phone || r.Saved_Email))
    : liveRecords;

  const elAll = document.getElementById("liveCountAll");
  if (elAll) elAll.innerText = dataset.length.toLocaleString();

  const elStacked = document.getElementById("liveCountStacked");
  if (elStacked) elStacked.innerText = dataset.filter(r => r.Is_Stacked_Distress === "Yes").length.toLocaleString();

  const elLp = document.getElementById("liveCountLp");
  if (elLp) elLp.innerText = dataset.filter(r => r.Lead_Type === "Lis Pendens").length.toLocaleString();

  const elLpTrust = document.getElementById("liveCountLpTrust");
  if (elLpTrust) elLpTrust.innerText = dataset.filter(r => r.Lead_Type === "Lis Pendens" && (r.Is_Trust_In_LP === "Yes" || r.Is_Trust_Or_Estate === "Yes")).length.toLocaleString();

  const elProbate = document.getElementById("liveCountProbate");
  if (elProbate) elProbate.innerText = dataset.filter(r => r.Lead_Type === "Probate").length.toLocaleString();

  const elCode = document.getElementById("liveCountCode");
  if (elCode) elCode.innerText = dataset.filter(r => r.Lead_Type === "Code Violation").length.toLocaleString();

  const elAbsentee = document.getElementById("liveCountAbsentee");
  if (elAbsentee) elAbsentee.innerText = dataset.filter(r => (r.Absentee_Status || "").includes("Out-of-State")).length.toLocaleString();

  const elTrust = document.getElementById("liveCountTrust");
  if (elTrust) elTrust.innerText = dataset.filter(r => (r.Owner_Entity_Type || "").includes("Trust") || r.Is_Trust_Or_Estate === "Yes").length.toLocaleString();

  const elTax = document.getElementById("liveCountTax");
  if (elTax) elTax.innerText = dataset.filter(r => (r.Lead_Type || "").includes("Tax Lien")).length.toLocaleString();
}

function updateSavedPipelineCount() {
  const savedCount = Object.keys(savedContactsCache || {}).length;
  const pCountSaved = document.getElementById("pipelineCountSaved");
  if (pCountSaved) pCountSaved.innerText = savedCount;
  const sideCountSaved = document.getElementById("sidebarSavedCount");
  if (sideCountSaved) sideCountSaved.innerText = savedCount;
}

async function fetchOutreachHistory() {
  try {
    const res = await fetch("/api/outreach/history");
    if (res.ok) {
      outreachHistoryCache = await res.json();
      const count = outreachHistoryCache.length;
      const pCountHist = document.getElementById("pipelineCountHistory");
      if (pCountHist) pCountHist.innerText = count;
      const sideHist = document.getElementById("sidebarHistoryCount");
      if (sideHist) sideHist.innerText = count;
      if (currentPipelineView === "history") {
        renderHistoryTable();
      }
    }
  } catch (err) {
    console.error("Error fetching outreach history:", err);
  }
}

function switchPipelineView(viewMode) {
  currentPipelineView = viewMode;

  // Pipeline Switcher Tab Buttons
  const tabAll = document.getElementById("pipelineTabAll");
  const tabSaved = document.getElementById("pipelineTabSaved");
  const tabHistory = document.getElementById("pipelineTabHistory");

  // Sidebar Links
  const sideDashboard = document.getElementById("sidebarLinkDashboard");
  const sideSaved = document.getElementById("sidebarLinkSaved");
  const sideHistory = document.getElementById("sidebarLinkHistory");

  const baseTabClass = "px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 bg-slate-800 text-slate-300 hover:text-white border border-slate-700 cursor-pointer";
  const inactiveSideClass = "flex items-center gap-3.5 px-4 py-2.5 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800/60 font-medium text-sm transition";

  if (tabAll) tabAll.className = baseTabClass;
  if (tabSaved) tabSaved.className = baseTabClass;
  if (tabHistory) tabHistory.className = baseTabClass;

  if (sideDashboard) sideDashboard.className = inactiveSideClass;
  if (sideSaved) sideSaved.className = inactiveSideClass;
  if (sideHistory) sideHistory.className = inactiveSideClass;

  const liveTableContainer = document.getElementById("liveTableContainer");
  const liveHistoryContainer = document.getElementById("liveHistoryContainer");
  const liveFilterPillsContainer = document.getElementById("liveFilterPillsContainer");
  const searchExportBar = document.getElementById("liveTableSearchExportBar");
  const liveCountyTitle = document.getElementById("liveCountyTitle");
  const liveStatusBadge = document.getElementById("liveStatusBadge");
  const liveCountySub = document.getElementById("liveCountySub");
  const pipelineDesc = document.getElementById("pipelineViewDescription");

  if (viewMode === "history") {
    if (tabHistory) tabHistory.className = "px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 bg-emerald-600 text-white shadow-md shadow-emerald-600/30 cursor-pointer";
    if (sideHistory) sideHistory.className = "flex items-center gap-3.5 px-4 py-2.5 rounded-xl bg-emerald-600 text-white font-semibold text-sm shadow-md shadow-emerald-600/25";

    if (liveFilterPillsContainer) liveFilterPillsContainer.classList.add("hidden");
    if (liveTableContainer) liveTableContainer.classList.add("hidden");
    if (searchExportBar) searchExportBar.classList.add("hidden");
    if (liveHistoryContainer) liveHistoryContainer.classList.remove("hidden");

    if (liveCountyTitle) liveCountyTitle.innerText = "Outreach Activity & Delivery Log";
    if (liveStatusBadge) liveStatusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Complete Dispatch Log`;
    if (liveCountySub) liveCountySub.innerText = "Audit record of every SMS message dispatched via your Android cellular plan and email offer sent via SMTP2GO.";
    if (pipelineDesc) pipelineDesc.innerText = "Timeline log of all outbound SMS texts and SMTP2GO wholesale email offers";

    renderHistoryTable();
  } else if (viewMode === "saved") {
    if (tabSaved) tabSaved.className = "px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 bg-amber-600 text-white shadow-md shadow-amber-600/30 cursor-pointer";
    if (sideSaved) sideSaved.className = "flex items-center gap-3.5 px-4 py-2.5 rounded-xl bg-amber-600 text-white font-semibold text-sm shadow-md shadow-amber-600/25";

    if (liveHistoryContainer) liveHistoryContainer.classList.add("hidden");
    if (liveFilterPillsContainer) liveFilterPillsContainer.classList.remove("hidden");
    if (liveTableContainer) liveTableContainer.classList.remove("hidden");
    if (searchExportBar) searchExportBar.classList.remove("hidden");

    const savedCount = Object.keys(savedContactsCache || {}).length;
    if (liveCountyTitle) liveCountyTitle.innerText = "⭐ Saved Lists & Active Pipeline (Skip-Traced Leads)";
    if (liveStatusBadge) liveStatusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span> ${savedCount} Skip-Traced Leads`;
    if (liveCountySub) liveCountySub.innerText = "Homeowners you have skip-traced, found phone numbers or emails for, and are actively targeting with offers.";
    if (pipelineDesc) pipelineDesc.innerText = "Curated pipeline of skip-traced leads with saved phone numbers and email addresses ready for outreach";

    filterLiveRecords(currentFilter);
    updateFilterCounts();
  } else {
    // 'all'
    if (tabAll) tabAll.className = "px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 bg-blue-600 text-white shadow-md shadow-blue-600/30 cursor-pointer";
    if (sideDashboard) sideDashboard.className = "flex items-center gap-3.5 px-4 py-2.5 rounded-xl bg-blue-600 text-white font-semibold text-sm shadow-md shadow-blue-600/25";

    if (liveHistoryContainer) liveHistoryContainer.classList.add("hidden");
    if (liveFilterPillsContainer) liveFilterPillsContainer.classList.remove("hidden");
    if (liveTableContainer) liveTableContainer.classList.remove("hidden");
    if (searchExportBar) searchExportBar.classList.remove("hidden");

    const totalVerified = liveRecords ? liveRecords.length : 3205;
    if (liveCountyTitle) liveCountyTitle.innerText = `${selectedCountyKey} County Live Distressed Leads`;
    if (liveStatusBadge) liveStatusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> ${totalVerified.toLocaleString()} Verified Properties`;
    if (liveCountySub) liveCountySub.innerText = "Cross-referenced against official county master parcels with clean owner names and absentee indicators.";
    if (pipelineDesc) pipelineDesc.innerText = "Showing all raw distressed public filings for Pinellas County";

    filterLiveRecords(currentFilter);
    updateFilterCounts();
  }
}

function renderHistoryTable() {
  const tbody = document.getElementById("liveHistoryTableBody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!outreachHistoryCache || outreachHistoryCache.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="p-12 text-center">
          <div class="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 mb-3 text-xl">
            📜
          </div>
          <div class="font-bold text-white text-base">No Outreach History Logged Yet</div>
          <p class="text-xs text-slate-400 max-w-md mx-auto mt-1 mb-4">Every text message dispatched through your Android phone and every wholesale offer emailed via SMTP2GO will be timestamped and permanently logged here.</p>
          <button type="button" onclick="switchPipelineView('saved')" class="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs inline-flex items-center gap-2 transition cursor-pointer">
            ⭐ View Saved Leads to Contact
          </button>
        </td>
      </tr>`;
    return;
  }

  outreachHistoryCache.forEach((entry) => {
    const isSms = (entry.channel || "").toUpperCase() === "SMS";
    const channelBadge = isSms 
      ? `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">💬 SMS Text</span>`
      : `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">✉️ SMTP2GO Email</span>`;

    const statusSuccess = entry.status === "SENT" || entry.status_code === 200 || entry.status_code === 201;
    const statusBadge = statusSuccess
      ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">✓ SENT</span>`
      : `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/40">✕ FAILED</span>`;

    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-800/40 transition";
    tr.innerHTML = `
      <td class="px-4 py-3 whitespace-nowrap text-slate-400 mono text-[11px]">
        ${entry.timestamp || "N/A"}
      </td>
      <td class="px-4 py-3 whitespace-nowrap">
        ${channelBadge}
      </td>
      <td class="px-4 py-3">
        <div class="font-bold text-white text-xs">${entry.owner || "Homeowner"}</div>
        ${entry.parcel_id ? `<div class="text-[10px] text-slate-500 mono">PIN: ${entry.parcel_id}</div>` : ""}
      </td>
      <td class="px-4 py-3">
        <div class="text-xs text-slate-300">${entry.address || "N/A"}</div>
        <div class="text-[10px] text-slate-500">${entry.county || "Pinellas"}, FL</div>
      </td>
      <td class="px-4 py-3 whitespace-nowrap mono text-xs text-emerald-300 font-semibold">
        ${entry.recipient || entry.phone || "N/A"}
      </td>
      <td class="px-4 py-3 max-w-xs">
        ${entry.subject && entry.subject !== "SMS Text Message" ? `<div class="text-[11px] font-bold text-blue-300 truncate">${entry.subject}</div>` : ""}
        <div class="text-[11px] text-slate-300 line-clamp-2 leading-relaxed" title="${escapeAttr(entry.message || "")}">
          ${entry.message || entry.subject || "Offer dispatched"}
        </div>
      </td>
      <td class="px-4 py-3 text-center whitespace-nowrap">
        ${statusBadge}
      </td>
      <td class="px-4 py-3 text-center whitespace-nowrap">
        ${isSms ? `
          <button type="button" onclick="openSmsModal('${entry.parcel_id || ""}', '${escapeAttr(entry.recipient || entry.phone || "")}', '${escapeAttr(entry.owner || "")}', '${escapeAttr(entry.address || "")}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-emerald-600 hover:text-white text-slate-300 text-[10px] font-bold transition flex items-center gap-1 mx-auto cursor-pointer">
            <span>💬</span> <span>Follow Up</span>
          </button>
        ` : `
          <button type="button" onclick="openEmailModal('${entry.parcel_id || ""}', '${escapeAttr(entry.recipient || "")}', '${escapeAttr(entry.owner || "")}', '${escapeAttr(entry.address || "")}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-cyan-600 hover:text-white text-slate-300 text-[10px] font-bold transition flex items-center gap-1 mx-auto cursor-pointer">
            <span>✉️</span> <span>Follow Up</span>
          </button>
        `}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function handleClearOutreachHistory() {
  if (!confirm("Are you sure you want to clear your outreach activity log?")) return;
  try {
    const res = await fetch("/api/outreach/history", { method: "DELETE" });
    if (res.ok) {
      await fetchOutreachHistory();
      renderHistoryTable();
    }
  } catch (err) {
    console.error("Error clearing outreach history:", err);
  }
}

function searchLiveTable() {
  const q = document.getElementById("liveSearchInput").value.toLowerCase().trim();
  if (!q) {
    filterLiveRecords(currentFilter);
    return;
  }
  const dataset = (currentPipelineView === "saved")
    ? liveRecords.filter(r => r.Parcel_ID && (savedContactsCache[r.Parcel_ID] || r.Saved_Phone || r.Saved_Email))
    : liveRecords;
  const filtered = dataset.filter(r => {
    const text = `${r.Property_Address} ${r.Clean_Full_Name} ${r.Parcel_ID} ${r.Mailing_Address} ${r.Mailing_City} ${r.Saved_Phone || ""} ${r.Saved_Email || ""}`.toLowerCase();
    return text.includes(q);
  });
  renderLiveTable(filtered);
}

function setupSearchFilter() {
  const searchInput = document.getElementById("countySearchInput");
  if (!searchInput) return;
  searchInput.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase().trim();
    if (!q) {
      renderCountyGrid(allCounties);
      return;
    }
    const filtered = allCounties.filter(c => c.name.toLowerCase().includes(q) || c.full_name.toLowerCase().includes(q));
    renderCountyGrid(filtered);
  });
}

async function quickFilterLeadType(leadType) {
  // Use currently selected county - never force Pinellas!
  const countyKey = selectedCountyKey || "Pinellas";
  const countyObj = allCounties.find(c => c.key === countyKey);

  // If county needs setup, keep county and show setup notice
  if (countyObj && !countyObj.has_master && countyKey !== "Pinellas") {
    await selectCounty(countyKey);
    const liveSection = document.getElementById("liveRecordsSection");
    if (liveSection) liveSection.scrollIntoView({ behavior: 'smooth' });
    return;
  }

  let filterKey = "all";
  if (leadType === "code_violations" || leadType === "code") filterKey = "code";
  else if (leadType === "lis_pendens" || leadType === "lp") filterKey = "lis_pendens";
  else if (leadType === "stacked") filterKey = "stacked";
  else if (leadType === "lp_trust") filterKey = "lp_trust";
  else if (leadType === "probate") filterKey = "probate";
  else if (leadType === "trust") filterKey = "lp_trust";
  else if (leadType === "tax_liens" || leadType === "tax") filterKey = "tax_liens";

  const heroSelect = document.getElementById("heroLeadSource");
  if (heroSelect) {
    if (filterKey === "code") heroSelect.value = "code_violations";
    else if (filterKey === "lis_pendens") heroSelect.value = "lis_pendens";
    else if (filterKey === "stacked") heroSelect.value = "stacked";
    else if (filterKey === "lp_trust") heroSelect.value = "lp_trust";
    else if (filterKey === "probate") heroSelect.value = "probate";
    else if (filterKey === "tax_liens") heroSelect.value = "tax_liens";
    else heroSelect.value = "lis_pendens";
  }

  // If Tax Liens is clicked and no Tax Liens records exist in the database:
  if (filterKey === "tax_liens") {
    const hasTax = liveRecords && liveRecords.some(r => (r.Lead_Type || "").includes("Tax Lien"));
    if (!hasTax) {
      openImportModal("tax_liens");
      filterLiveRecords("tax_liens");
      const liveSection = document.getElementById("liveRecordsSection");
      if (liveSection) liveSection.scrollIntoView({ behavior: 'smooth' });
      return;
    }
  }

  await selectCounty(countyKey, filterKey);
  filterLiveRecords(filterKey);

  const liveSection = document.getElementById("liveRecordsSection");
  if (liveSection) liveSection.scrollIntoView({ behavior: 'smooth' });
}

async function handleFindProperties(e) {
  if (e && e.preventDefault) e.preventDefault();

  const county = document.getElementById("heroCountySelect").value;
  const source = document.getElementById("heroLeadSource").value;
  
  let filterKey = "all";
  if (source === "code_violations") filterKey = "code";
  else if (source === "lis_pendens") filterKey = "lis_pendens";
  else if (source === "lp_trust") filterKey = "lp_trust";
  else if (source === "stacked") filterKey = "stacked";
  else if (source === "probate") filterKey = "probate";
  else if (source === "tax_liens") filterKey = "tax_liens";

  const countyObj = allCounties.find(c => c.key === county);
  if (countyObj && !countyObj.has_master && county !== "Pinellas") {
    await selectCounty(county);
    const liveSection = document.getElementById("liveRecordsSection");
    if (liveSection) liveSection.scrollIntoView({ behavior: 'smooth' });
    return;
  }

  if (filterKey === "tax_liens") {
    const hasTax = liveRecords && liveRecords.some(r => (r.Lead_Type || "").includes("Tax Lien"));
    if (!hasTax) {
      openImportModal("tax_liens");
      filterLiveRecords("tax_liens");
      const liveSection = document.getElementById("liveRecordsSection");
      if (liveSection) liveSection.scrollIntoView({ behavior: 'smooth' });
      return;
    }
  }

  await selectCounty(county, filterKey);
  filterLiveRecords(filterKey);

  const liveSection = document.getElementById("liveRecordsSection");
  if (liveSection) liveSection.scrollIntoView({ behavior: 'smooth' });
}

function triggerExport() {
  window.location.href = "/api/export";
}

// Modal & CSV Import Handlers
function openImportModal(defaultLeadType = "tax_liens") {
  const modal = document.getElementById("importModal");
  if (!modal) return;
  modal.classList.remove("hidden");

  const countyInput = document.getElementById("importCountyInput");
  if (countyInput) countyInput.value = `${selectedCountyKey || 'Pinellas'} County`;

  const typeSelect = document.getElementById("importLeadTypeSelect");
  if (typeSelect && defaultLeadType) {
    if (defaultLeadType === "code") typeSelect.value = "code_violations";
    else if (defaultLeadType === "lis_pendens" || defaultLeadType === "lp") typeSelect.value = "lis_pendens";
    else if (defaultLeadType === "trust" || defaultLeadType === "probate") typeSelect.value = "probate";
    else typeSelect.value = "tax_liens";
  }

  const fileInput = document.getElementById("importFileInput");
  if (fileInput) fileInput.value = "";
  const label = document.getElementById("importFileLabel");
  if (label) label.innerText = "Click or drag & drop CSV file here";
}

function closeImportModal() {
  const modal = document.getElementById("importModal");
  if (modal) modal.classList.add("hidden");
}

function handleFileSelected(input) {
  const label = document.getElementById("importFileLabel");
  if (input.files && input.files[0]) {
    label.innerText = `Selected: ${input.files[0].name} (${(input.files[0].size / 1024).toFixed(1)} KB)`;
  } else {
    label.innerText = "Click or drag & drop CSV file here";
  }
}

async function handleImportSubmit(e) {
  if (e && e.preventDefault) e.preventDefault();

  const fileInput = document.getElementById("importFileInput");
  if (!fileInput || !fileInput.files[0]) {
    alert("Please select a CSV or Excel file to import.");
    return;
  }

  const county = selectedCountyKey || "Pinellas";
  const countyObj = allCounties.find(c => c.key === county);

  if (countyObj && !countyObj.has_master && county !== "Pinellas") {
    alert(`Please download and install the master parcel file for ${county} County before matching lead lists.`);
    return;
  }

  const leadSource = document.getElementById("importLeadTypeSelect").value;
  const file = fileInput.files[0];

  const submitBtn = document.getElementById("btnSubmitImport");
  const origBtnText = submitBtn.innerHTML;
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span>⏳ Cross-referencing...</span>`;

  try {
    const formData = new FormData();
    formData.append("county", county);
    formData.append("lead_source", leadSource);
    formData.append("file", file);

    const res = await fetch("/api/match", {
      method: "POST",
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Match engine error");
    }

    const data = await res.json();
    closeImportModal();

    if (data.records && data.records.length > 0) {
      // Reload all county leads and KPIs from server so all counts and cross-referenced multi-distress signals are fresh
      await loadLiveCountyLeads(county);

      // Show results modal
      openResultsModal(data);

      // Re-filter live table
      const targetFilter = leadSource === "tax_liens" ? "tax_liens" : (leadSource === "code_violations" ? "code" : (leadSource === "probate" ? "probate" : "lis_pendens"));
      filterLiveRecords(targetFilter);
    } else {
      alert(`No parcel matches found in the uploaded file for ${county} County.`);
    }
  } catch (err) {
    alert(`Import failed: ${err.message}`);
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = origBtnText;
  }
}

function openResultsModal(data) {
  const modal = document.getElementById("resultsModal");
  if (!modal) return;
  modal.classList.remove("hidden");

  document.getElementById("modalCountyTitle").innerText = `${data.county} County Matched Leads`;
  document.getElementById("modalSubTitle").innerText = `Cross-referenced against ${data.total_parcels?.toLocaleString() || '437,559'} master parcels`;

  document.getElementById("kpiTotalLeads").innerText = (data.kpis?.total_leads || data.records?.length || 0).toLocaleString();
  document.getElementById("kpiMatchedCount").innerText = (data.kpis?.matched_count || data.records?.length || 0).toLocaleString();
  document.getElementById("kpiMatchRate").innerText = `${data.kpis?.match_rate || 90}%`;
  document.getElementById("kpiAbsenteeCount").innerText = (data.kpis?.out_of_state_count || 0).toLocaleString();
  document.getElementById("kpiAvgValue").innerText = data.kpis?.avg_market_value ? `$${Math.round(data.kpis.avg_market_value).toLocaleString()}` : '$340,000';

  renderModalTable(data.records);
}

function closeResultsModal() {
  const modal = document.getElementById("resultsModal");
  if (modal) modal.classList.add("hidden");
}

function renderModalTable(records) {
  const tbody = document.getElementById("modalTableBody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!records || records.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="p-6 text-center text-slate-400">No records found.</td></tr>`;
    return;
  }

  records.forEach(r => {
    const isAbsentee = (r.Absentee_Status || "").includes("Out-of-State");
    const isLlc = (r.Owner_Entity_Type || "").includes("LLC");
    const isTrust = (r.Owner_Entity_Type || "").includes("Trust");
    const mktVal = parseFloat(r.Market_Value || 0);

    // Skip Trace calculation
    let modalSkipName = (r.Clean_First_Name && r.Clean_Last_Name) ? `${r.Clean_First_Name} ${r.Clean_Last_Name}` : (r.Clean_Full_Name || r.Clean_Last_Name || "");
    modalSkipName = (modalSkipName || "").replace(/\b(TR|TRE|TRUSTEE|ESTATE|EST|OF|DECD|DECEASED|ET|AL|LIFE|LE)\b/gi, " ").replace(/\s+/g, " ").trim();
    const modalCity = (r.Mailing_City || r.Property_City || "St Petersburg").trim();
    const modalState = (r.Mailing_State || "FL").trim();
    const modalSkipUrl = `https://www.truepeoplesearch.com/results?name=${encodeURIComponent(modalSkipName)}&citystatezip=${encodeURIComponent(`${modalCity}, ${modalState}`)}#lead_hub_pid=${encodeURIComponent(r.Parcel_ID || '')}&county=${encodeURIComponent(selectedCountyKey)}&owner=${encodeURIComponent(modalSkipName)}&addr=${encodeURIComponent(r.Property_Address || '')}`;
    
    const mSavedContact = savedContactsCache[r.Parcel_ID] || (r.Saved_Phone ? { phone: r.Saved_Phone } : null);
    const mSavedPhone = mSavedContact ? mSavedContact.phone : null;

    let modalPaUrl = "https://www.pcpao.gov/quick-search";
    const mPidTrim = (r.Parcel_ID || "").trim();
    const mPidParts = mPidTrim.split("-");
    if (mPidParts.length === 6) {
      modalPaUrl = `https://www.pcpao.gov/property-details?s=${mPidParts[2]}${mPidParts[1]}${mPidParts[0]}${mPidParts[3]}${mPidParts[4]}${mPidParts[5]}`;
    }

    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-800/40 transition";
    tr.innerHTML = `
      <td class="px-4 py-3"><span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400">✓ MATCHED</span></td>
      <td class="px-4 py-3"><div class="font-bold text-white text-xs">${r.Property_Address || 'N/A'}</div><div class="text-[10px] text-slate-400">${r.Property_City || 'ST PETERSBURG'}, FL ${r.Property_Zip || ''}</div></td>
      <td class="px-4 py-3">
        <div class="font-bold text-blue-300 text-xs">${r.Clean_Full_Name || r.Clean_Last_Name || 'Unknown Owner'}</div>
        <div class="text-[10px] text-slate-500 mono">PIN: ${r.Parcel_ID || 'N/A'}</div>
        ${mSavedPhone ? `
          <div class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-[10px] font-bold mt-1 shadow-sm">
            <span>📱</span> <span>${mSavedPhone}</span>
          </div>
        ` : ''}
      </td>
      <td class="px-4 py-3"><span class="px-2 py-0.5 rounded-md text-[10px] font-semibold ${isLlc ? 'bg-amber-500/15 text-amber-300' : (isTrust ? 'bg-purple-500/15 text-purple-300' : 'bg-slate-800 text-slate-300')}">${r.Owner_Entity_Type || 'Individual'}</span></td>
      <td class="px-4 py-3"><span class="px-2 py-0.5 rounded-full text-[10px] font-semibold ${isAbsentee ? 'bg-purple-500/20 text-purple-300' : 'bg-slate-800 text-slate-400'}">${isAbsentee ? '✈️ ' : ''}${r.Absentee_Status || 'Owner Occupied'}</span></td>
      <td class="px-4 py-3"><div class="text-xs text-slate-200">${r.Living_Sqft || '-'} sqft</div><div class="text-[10px] text-slate-500">Built ${r.Year_Built || '-'}</div></td>
      <td class="px-4 py-3 text-right mono font-bold text-white">${mktVal > 0 ? `$${mktVal.toLocaleString()}` : '-'}</td>
      <td class="px-4 py-3 text-center">
        <div class="flex items-center justify-center gap-1.5">
          ${mSavedPhone ? `
            <button type="button" onclick="openSmsModal('${r.Parcel_ID}', '${mSavedPhone}', '${escapeAttr(modalSkipName)}', '${escapeAttr(r.Property_Address || '')}')" class="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] font-bold transition flex items-center gap-1 shadow-md shadow-emerald-600/30 cursor-pointer" title="Send Wholesale SMS Offer">
              <span>💬</span> <span>Send SMS</span>
            </button>
          ` : `
            <a href="${modalSkipUrl}" target="_blank" rel="noopener noreferrer" class="px-2 py-1 rounded bg-amber-500/20 hover:bg-amber-500 hover:text-slate-950 text-amber-300 text-[10px] font-bold transition flex items-center gap-1 shadow-sm border border-amber-500/30" title="Free 1-Click Skip Trace (TruePeopleSearch) for ${modalSkipName}">
              <span>📞</span> <span>Free Trace</span>
            </a>
          `}
          <a href="${modalPaUrl}" target="_blank" class="px-2 py-1 rounded bg-slate-800 hover:bg-blue-600 hover:text-white text-slate-300 text-[10px] font-semibold transition" title="View Property Appraiser">
            🔍 PCPAO
          </a>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// -------------------------------------------------------------
// Official County Portal Links & Source Management
// -------------------------------------------------------------

function updateCategoryCardLinks(countyKey) {
  const c = allCounties.find(item => item.key === countyKey) || {
    name: "Pinellas",
    key: "Pinellas",
    master_parcel_download_url: "https://www.pcpao.gov/tools-data/data-downloads/raw-database-files",
    clerk_lis_pendens_url: "https://officialrecords.mypinellasclerk.gov/search/SearchTypeDocType",
    code_enforcement_url: "https://aca-prod.accela.com/PINELLAS/Cap/CapHome.aspx?module=Enforcement&TabName=Home",
    tax_liens_url: "https://pinellas.county-taxes.com/public",
    clerk_probate_url: "https://officialrecords.mypinellasclerk.gov/search/SearchTypeDocType"
  };

  const label = document.getElementById("heroSelectedCountyLabel");
  if (label) label.innerText = `${c.name} County`;

  const heroMaster = document.getElementById("heroMasterParcelLink");
  if (heroMaster) {
    heroMaster.href = c.master_parcel_download_url || "#";
    heroMaster.title = `Official Master Parcel Download for ${c.name} County`;
  }

  const linkLp = document.getElementById("cardLinkLp");
  if (linkLp) {
    linkLp.href = c.clerk_lis_pendens_url || "#";
    linkLp.title = `Official Lis Pendens Portal (${c.name} County)`;
  }

  const linkCode = document.getElementById("cardLinkCode");
  if (linkCode) {
    linkCode.href = c.code_enforcement_url || "#";
    linkCode.title = `Official Code Enforcement Portal (${c.name} County)`;
  }

  const linkTax = document.getElementById("cardLinkTax");
  if (linkTax) {
    linkTax.href = c.tax_liens_url || "#";
    linkTax.title = `Official Tax Collector Portal (${c.name} County)`;
  }

  const linkProbate = document.getElementById("cardLinkProbate");
  if (linkProbate) {
    linkProbate.href = c.clerk_probate_url || "#";
    linkProbate.title = `Official Probate Court Portal (${c.name} County)`;
  }
}

async function openPortalLinksModal(countyKey = null) {
  if (!allCounties || allCounties.length === 0) {
    try {
      const res = await fetch("/api/counties");
      if (res.ok) allCounties = await res.json();
    } catch (e) {
      console.error("Error fetching counties in openPortalLinksModal:", e);
    }
  }

  const targetKey = countyKey || selectedCountyKey || "Pinellas";
  const select = document.getElementById("portalCountySelect");
  if (select) {
    select.innerHTML = "";
    (allCounties || []).forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.key;
      opt.textContent = `${c.name} County`;
      if (c.key === targetKey) opt.selected = true;
      select.appendChild(opt);
    });
  }

  loadCountyPortalInputs(targetKey);
  const modal = document.getElementById("portalLinksModal");
  if (modal) modal.classList.remove("hidden");
  const alertEl = document.getElementById("portalSaveAlert");
  if (alertEl) alertEl.classList.add("hidden");
}

function closePortalLinksModal() {
  const modal = document.getElementById("portalLinksModal");
  if (modal) modal.classList.add("hidden");
}

function loadCountyPortalInputs(countyKey) {
  let c = (allCounties || []).find(item => item.key === countyKey);
  if (!c) {
    c = {
      name: "Pinellas",
      key: "Pinellas",
      master_parcel_download_url: "https://www.pcpao.gov/tools-data/data-downloads/raw-database-files",
      clerk_lis_pendens_url: "https://officialrecords.mypinellasclerk.gov/search/SearchTypeDocType",
      code_enforcement_url: "https://aca-prod.accela.com/PINELLAS/Cap/CapHome.aspx?module=Enforcement&TabName=Home",
      tax_liens_url: "https://pinellas.county-taxes.com/public",
      clerk_probate_url: "https://officialrecords.mypinellasclerk.gov/search/SearchTypeDocType"
    };
  }

  const inMaster = document.getElementById("inputPortalMaster");
  const inLp = document.getElementById("inputPortalLp");
  const inCode = document.getElementById("inputPortalCode");
  const inTax = document.getElementById("inputPortalTax");
  const inProbate = document.getElementById("inputPortalProbate");

  if (inMaster) inMaster.value = c.master_parcel_download_url || "";
  if (inLp) inLp.value = c.clerk_lis_pendens_url || "";
  if (inCode) inCode.value = c.code_enforcement_url || "";
  if (inTax) inTax.value = c.tax_liens_url || "";
  if (inProbate) inProbate.value = c.clerk_probate_url || "";

  syncTestPortalButtons();
}

function syncTestPortalButtons() {
  const inMaster = document.getElementById("inputPortalMaster");
  const inLp = document.getElementById("inputPortalLp");
  const inCode = document.getElementById("inputPortalCode");
  const inTax = document.getElementById("inputPortalTax");
  const inProbate = document.getElementById("inputPortalProbate");

  const btnMaster = document.getElementById("btnTestMaster");
  const btnLp = document.getElementById("btnTestLp");
  const btnCode = document.getElementById("btnTestCode");
  const btnTax = document.getElementById("btnTestTax");
  const btnProbate = document.getElementById("btnTestProbate");

  if (btnMaster && inMaster) btnMaster.href = inMaster.value || "#";
  if (btnLp && inLp) btnLp.href = inLp.value || "#";
  if (btnCode && inCode) btnCode.href = inCode.value || "#";
  if (btnTax && inTax) btnTax.href = inTax.value || "#";
  if (btnProbate && inProbate) btnProbate.href = inProbate.value || "#";
}

// Live update test buttons as user edits URL fields
document.addEventListener("DOMContentLoaded", () => {
  ["inputPortalMaster", "inputPortalLp", "inputPortalCode", "inputPortalTax", "inputPortalProbate"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", syncTestPortalButtons);
  });
});

async function handlePortalLinksSubmit(event) {
  event.preventDefault();
  const select = document.getElementById("portalCountySelect");
  const countyKey = select ? select.value : selectedCountyKey;
  
  const payload = {
    county: countyKey,
    master_parcel_download_url: (document.getElementById("inputPortalMaster").value || "").trim(),
    clerk_lis_pendens_url: (document.getElementById("inputPortalLp").value || "").trim(),
    code_enforcement_url: (document.getElementById("inputPortalCode").value || "").trim(),
    tax_liens_url: (document.getElementById("inputPortalTax").value || "").trim(),
    clerk_probate_url: (document.getElementById("inputPortalProbate").value || "").trim()
  };

  const btn = document.getElementById("btnSavePortalLinks");
  if (btn) btn.innerText = "Saving...";

  try {
    const res = await fetch("/api/counties/update-portals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      // Update in-memory allCounties
      const idx = allCounties.findIndex(c => c.key === countyKey);
      if (idx !== -1) {
        allCounties[idx] = { ...allCounties[idx], ...payload };
      }
      updateCategoryCardLinks(selectedCountyKey);
      const alertEl = document.getElementById("portalSaveAlert");
      if (alertEl) {
        alertEl.classList.remove("hidden");
        setTimeout(() => alertEl.classList.add("hidden"), 3500);
      }
    } else {
      alert("Error saving portal links. Please check server logs.");
    }
  } catch (err) {
    console.error("Save portal error:", err);
    alert("Connection error while saving portal links.");
  } finally {
    if (btn) btn.innerText = "💾 Save Portal Links";
  }
}

// -------------------------------------------------------------
// Custom Distress Categories & Cards Management
// -------------------------------------------------------------

async function fetchCustomCategories() {
  try {
    const res = await fetch("/api/custom-categories");
    if (res.ok) {
      customCategories = await res.json();
      updateCustomCategoryBadges();
      renderCustomCategoryCardsOnDashboard();
      updateDropdownOptionsWithCustomCategories();
    }
  } catch (err) {
    console.error("Error fetching custom categories:", err);
  }
}

function updateCustomCategoryBadges() {
  const badge = document.getElementById("customCardCountBadge");
  if (badge) {
    badge.innerText = customCategories.length;
    if (customCategories.length > 0) {
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
    }
  }
}

function switchPortalModalTab(tab) {
  const btnUrls = document.getElementById("tabBtnPortalUrls");
  const btnCards = document.getElementById("tabBtnCustomCards");
  const panelUrls = document.getElementById("panelPortalUrls");
  const panelCards = document.getElementById("panelCustomCards");

  if (tab === "urls") {
    btnUrls.className = "px-4 py-2 border-b-2 border-blue-500 text-blue-400 font-bold text-xs cursor-pointer transition";
    btnCards.className = "px-4 py-2 border-b-2 border-transparent text-slate-400 hover:text-slate-200 font-bold text-xs cursor-pointer transition flex items-center gap-1.5";
    panelUrls.classList.remove("hidden");
    panelCards.classList.add("hidden");
  } else {
    btnCards.className = "px-4 py-2 border-b-2 border-purple-500 text-purple-400 font-bold text-xs cursor-pointer transition flex items-center gap-1.5";
    btnUrls.className = "px-4 py-2 border-b-2 border-transparent text-slate-400 hover:text-slate-200 font-bold text-xs cursor-pointer transition";
    panelCards.classList.remove("hidden");
    panelUrls.classList.add("hidden");
    renderCustomCardsList();
  }
}

function renderCustomCardsList() {
  const container = document.getElementById("customCardsList");
  if (!container) return;

  if (!customCategories || customCategories.length === 0) {
    container.innerHTML = `
      <div class="text-xs text-slate-500 italic p-3 rounded-xl bg-slate-900/50 border border-slate-800 text-center">
        No custom distress cards added yet. Use the form below to add cards for Judgments, Divorce, Evictions, etc.
      </div>
    `;
    return;
  }

  container.innerHTML = "";
  customCategories.forEach(cat => {
    const item = document.createElement("div");
    item.className = "p-3 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center justify-between gap-3";
    item.innerHTML = `
      <div class="flex items-center gap-3">
        <span class="text-xl">${cat.icon || '⚖️'}</span>
        <div>
          <div class="flex items-center gap-2">
            <span class="font-bold text-xs text-white">${cat.name}</span>
            <span class="px-2 py-0.5 rounded text-[9px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">${cat.badge || 'Custom'}</span>
          </div>
          <div class="text-[10px] text-slate-400 mt-0.5">${cat.description || 'Custom distress lead source'}</div>
          ${cat.portal_url ? `<a href="${cat.portal_url}" target="_blank" class="text-[10px] text-blue-400 hover:underline">🌐 ${cat.portal_url}</a>` : ''}
        </div>
      </div>
      <button type="button" onclick="handleDeleteCustomCategory('${cat.id}')" class="px-2.5 py-1 rounded-lg bg-rose-500/10 hover:bg-rose-600 text-rose-400 hover:text-white border border-rose-500/20 text-[10px] font-bold transition cursor-pointer" title="Remove this custom card">
        🗑️ Remove
      </button>
    `;
    container.appendChild(item);
  });
}

async function handleCreateCustomCategory(event) {
  event.preventDefault();
  const name = document.getElementById("newCatName").value.trim();
  const badge = document.getElementById("newCatBadge").value.trim();
  const icon = document.getElementById("newCatIcon").value;
  const desc = document.getElementById("newCatDesc").value.trim();
  const url = document.getElementById("newCatUrl").value.trim();

  if (!name) return;

  const btn = document.getElementById("btnSubmitCustomCard");
  if (btn) btn.innerText = "Adding...";

  try {
    const res = await fetch("/api/custom-categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name,
        badge: badge,
        icon: icon,
        description: desc,
        portal_url: url
      })
    });

    if (res.ok) {
      document.getElementById("newCatName").value = "";
      document.getElementById("newCatBadge").value = "";
      document.getElementById("newCatDesc").value = "";
      document.getElementById("newCatUrl").value = "";
      
      const alertEl = document.getElementById("customCatAlert");
      if (alertEl) {
        alertEl.classList.remove("hidden");
        setTimeout(() => alertEl.classList.add("hidden"), 3500);
      }

      await fetchCustomCategories();
      renderCustomCardsList();
    } else {
      alert("Error adding custom category.");
    }
  } catch (err) {
    console.error("Create custom category error:", err);
    alert("Connection error while creating custom category.");
  } finally {
    if (btn) btn.innerHTML = "<span>➕</span> Add Card to Dashboard";
  }
}

async function handleDeleteCustomCategory(id) {
  if (!confirm("Are you sure you want to remove this distress card from the dashboard?")) return;

  try {
    const res = await fetch(`/api/custom-categories/${id}`, {
      method: "DELETE"
    });
    if (res.ok) {
      await fetchCustomCategories();
      renderCustomCardsList();
    }
  } catch (err) {
    console.error("Delete custom category error:", err);
  }
}

function renderCustomCategoryCardsOnDashboard() {
  const container = document.getElementById("leadCategories");
  if (!container) return;

  // Remove existing custom cards (marked with class 'custom-category-card')
  const existingCustom = container.querySelectorAll(".custom-category-card");
  existingCustom.forEach(el => el.remove());

  // Render each custom category
  customCategories.forEach(cat => {
    const card = document.createElement("div");
    card.className = "custom-category-card glass-surface rounded-2xl p-5 border border-slate-800 hover:border-purple-700/60 transition cursor-pointer group flex flex-col justify-between";
    card.onclick = () => filterLiveRecordsByCustom(cat.name);

    card.innerHTML = `
      <div>
        <div class="flex items-center space-x-3.5 mb-2">
          <div class="w-10 h-10 rounded-xl bg-purple-950/60 border border-purple-800/40 flex items-center justify-center text-lg group-hover:scale-105 transition">
            ${cat.icon || '⚖️'}
          </div>
          <div>
            <div class="font-bold text-white text-sm">${cat.name}</div>
            <div class="text-[10px] text-purple-400 font-semibold">${cat.badge || 'Distress Filing'}</div>
          </div>
        </div>
        <p class="text-xs text-slate-400 mt-2">${cat.description || 'Public court & county distress filings.'}</p>
      </div>
      <div class="mt-4 pt-3 border-t border-slate-800/80 space-y-2">
        <div class="flex items-center justify-between gap-1.5">
          <button type="button" onclick="event.stopPropagation(); filterLiveRecordsByCustom('${cat.name}')" class="inline-flex items-center gap-1 text-[11px] font-bold text-purple-400 hover:text-purple-300 transition cursor-pointer">
            VIEW DETAILS &rarr;
          </button>
          ${cat.portal_url ? `
            <a href="${cat.portal_url}" target="_blank" onclick="event.stopPropagation()" class="px-2 py-1 rounded-lg bg-slate-800/90 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 text-[10px] font-semibold inline-flex items-center gap-1 transition" title="Go to official portal">
              🌐 Official Portal ↗
            </a>
          ` : ''}
        </div>
        <button type="button" onclick="event.stopPropagation(); openImportModal('${cat.id}')" class="w-full py-1.5 rounded-lg bg-purple-600/20 hover:bg-purple-600 text-purple-300 hover:text-white border border-purple-500/30 text-[10px] font-bold inline-flex items-center justify-center gap-1.5 transition cursor-pointer" title="Import new ${cat.name} CSV">
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
          + Update CSV
        </button>
      </div>
    `;

    container.appendChild(card);
  });
}

function filterLiveRecordsByCustom(categoryName) {
  if (!liveRecords) return;
  const filtered = liveRecords.filter(r => (r.Lead_Type || "").toLowerCase().includes(categoryName.toLowerCase()));
  if (filtered.length === 0) {
    const matchedCategory = customCategories.find(c => c.name.toLowerCase() === categoryName.toLowerCase());
    openImportModal(matchedCategory ? matchedCategory.id : "custom");
  } else {
    renderLiveTable(filtered);
    const liveSection = document.getElementById("liveRecordsSection");
    if (liveSection) liveSection.scrollIntoView({ behavior: 'smooth' });
  }
}

function updateDropdownOptionsWithCustomCategories() {
  const heroSelect = document.getElementById("heroLeadSource");
  const importSelect = document.getElementById("importLeadTypeSelect");

  // Remove previous custom options
  if (heroSelect) {
    heroSelect.querySelectorAll(".custom-option").forEach(el => el.remove());
    customCategories.forEach(cat => {
      const opt = document.createElement("option");
      opt.className = "custom-option";
      opt.value = cat.id;
      opt.textContent = `${cat.icon || '⚖️'} ${cat.name}`;
      heroSelect.appendChild(opt);
    });
  }

  if (importSelect) {
    importSelect.querySelectorAll(".custom-option").forEach(el => el.remove());
    customCategories.forEach(cat => {
      const opt = document.createElement("option");
      opt.className = "custom-option";
      opt.value = cat.id;
      opt.textContent = `${cat.icon || '⚖️'} ${cat.name}`;
      importSelect.appendChild(opt);
    });
  }
}

// -------------------------------------------------------------
// Contact Management & Android SMS Gateway (capcom6/android-sms-gateway)
// -------------------------------------------------------------
function escapeAttr(str) {
  if (!str) return "";
  return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

async function fetchSavedContacts() {
  try {
    const res = await fetch("/api/leads/contacts");
    if (res.ok) {
      savedContactsCache = await res.json();
      updateSavedPipelineCount();
    }
  } catch (err) {
    console.error("Error loading saved contacts:", err);
  }
}

// Re-fetch contacts and re-render the current view
async function refreshContactsAndUI() {
  const oldJson = JSON.stringify(savedContactsCache);
  await fetchSavedContacts();
  const newJson = JSON.stringify(savedContactsCache);
  if (oldJson !== newJson) {
    updateSavedPipelineCount();
    updateFilterCounts();
    if (liveRecords && liveRecords.length > 0) {
      filterLiveRecords(currentFilter);
    }
  }
}

// When window gains focus (user tabs back from TruePeopleSearch), re-fetch contacts and re-render
window.addEventListener("focus", refreshContactsAndUI);

// Fast auto-sync interval every 3 seconds so split-screen / background tabs update immediately!
setInterval(refreshContactsAndUI, 3000);

async function loadSmsSettings() {
  try {
    const res = await fetch("/api/sms/settings");
    if (res.ok) {
      smsSettingsCache = await res.json();
      if (smsSettingsCache.template) {
        SMS_TEMPLATES.cash_offer = smsSettingsCache.template;
      }
    }
  } catch (err) {
    console.error("Error loading SMS settings:", err);
  }
}

function openSmsModal(parcelId, phone, ownerName, propertyAddress) {
  const modal = document.getElementById("smsModal");
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }

  try {
    const pidEl = document.getElementById("smsParcelId");
    if (pidEl) pidEl.value = parcelId || "";
    const cntyEl = document.getElementById("smsCounty");
    if (cntyEl) cntyEl.value = selectedCountyKey || "Pinellas";
    const ownEl = document.getElementById("smsOwnerName");
    if (ownEl) ownEl.value = ownerName || "";
    const addrEl = document.getElementById("smsPropertyAddress");
    if (addrEl) addrEl.value = propertyAddress || "";

    const ownDisp = document.getElementById("smsOwnerDisplay");
    if (ownDisp) ownDisp.innerText = ownerName || "Homeowner";
    const addrDisp = document.getElementById("smsAddressDisplay");
    if (addrDisp) addrDisp.innerText = propertyAddress || "Florida Property";
    const phInput = document.getElementById("smsPhoneInput");
    if (phInput) phInput.value = phone || "";

    const statusBanner = document.getElementById("smsStatusBanner");
    if (statusBanner) {
      statusBanner.className = "hidden p-3 rounded-xl text-xs font-semibold";
      statusBanner.innerText = "";
    }

    // Refresh template selector options from cache
    const tmplSelect = document.getElementById("smsTemplateSelect");
    if (tmplSelect && outreachTemplatesCache && outreachTemplatesCache.sms) {
      const curVal = tmplSelect.value;
      tmplSelect.innerHTML = "";
      outreachTemplatesCache.sms.forEach(t => {
        const opt = document.createElement("option");
        opt.value = t.id;
        opt.textContent = t.name;
        tmplSelect.appendChild(opt);
      });
      if (curVal && outreachTemplatesCache.sms.some(t => t.id === curVal)) {
        tmplSelect.value = curVal;
      } else {
        tmplSelect.value = outreachTemplatesCache.sms[0]?.id || "cash_offer";
      }
    }

    // Apply active template
    const activeKey = tmplSelect ? tmplSelect.value : "cash_offer";
    applySmsTemplate(activeKey);
  } catch (err) {
    console.error("Error setting up SMS modal:", err);
  }
}

function closeSmsModal() {
  const modal = document.getElementById("smsModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

function applySmsTemplate(templateKey) {
  let templateBody = "";
  if (outreachTemplatesCache && outreachTemplatesCache.sms) {
    const found = outreachTemplatesCache.sms.find(t => t.id === templateKey);
    if (found) templateBody = found.body;
  }
  if (!templateBody) {
    templateBody = SMS_TEMPLATES[templateKey] || SMS_TEMPLATES.cash_offer;
  }

  const rawOwner = document.getElementById("smsOwnerName")?.value || "Homeowner";
  const rawAddr = document.getElementById("smsPropertyAddress")?.value || "your property";
  
  // Extract First Name & Last Name
  const nameParts = rawOwner.trim().split(/\s+/);
  let firstName = nameParts[0] || "Homeowner";
  firstName = firstName.charAt(0).toUpperCase() + firstName.slice(1).toLowerCase();
  const lastName = nameParts.length > 1 ? nameParts[nameParts.length - 1] : "";

  // Extract Street Address & City
  const addrParts = rawAddr.split(",");
  const streetAddr = addrParts[0]?.trim() || rawAddr;
  const city = selectedCountyKey || "your area";

  let filled = templateBody
    .replace(/{FirstName}/g, firstName)
    .replace(/{LastName}/g, lastName)
    .replace(/{Address}/g, streetAddr)
    .replace(/{City}/g, city)
    .replace(/{State}/g, currentState || "FL")
    .replace(/{County}/g, selectedCountyKey || "Pinellas")
    .replace(/{Phone}/g, "(407) 555-FLIP");

  const textEl = document.getElementById("smsMessageText");
  if (textEl) {
    textEl.value = filled;
    updateSmsCharCount();
  }
}

function updateSmsCharCount() {
  const textEl = document.getElementById("smsMessageText");
  const countEl = document.getElementById("smsCharCount");
  if (textEl && countEl) {
    const len = textEl.value.length;
    const segments = Math.ceil(len / 160) || 1;
    countEl.innerText = `${len} chars (${segments} SMS segment${segments > 1 ? 's' : ''})`;
  }
}

async function handleSendSms(e) {
  e.preventDefault();
  const phone = document.getElementById("smsPhoneInput").value.trim();
  const message = document.getElementById("smsMessageText").value.trim();
  const parcelId = document.getElementById("smsParcelId").value;
  const county = document.getElementById("smsCounty").value;
  const ownerName = document.getElementById("smsOwnerName").value;
  const propertyAddress = document.getElementById("smsPropertyAddress").value;

  const btn = document.getElementById("btnSendSmsSubmit");
  const banner = document.getElementById("smsStatusBanner");

  if (!phone || !message) {
    alert("Please provide both phone number and message.");
    return;
  }

  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> <span>Sending via Phone...</span>`;
  banner.className = "hidden p-3 rounded-xl text-xs font-semibold";

  try {
    const res = await fetch("/api/sms/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        phone: phone,
        message: message,
        parcel_id: parcelId,
        county: county,
        owner_name: ownerName,
        property_address: propertyAddress
      })
    });

    const data = await res.json();
    if (data.status === "success") {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-emerald-950/60 border border-emerald-500/50 text-emerald-300 block";
      banner.innerHTML = `✓ SMS dispatched successfully! Phone: <b>${data.phone}</b>. Sent from your cellular plan via Android SMS Gateway.`;
      
      // Update local contacts cache
      if (parcelId) {
        if (!savedContactsCache[parcelId]) savedContactsCache[parcelId] = {};
        savedContactsCache[parcelId].phone = phone;
        savedContactsCache[parcelId].last_sms_sent = "Just now";
        savedContactsCache[parcelId].last_sms_status = "SENT";
        updateSavedPipelineCount();
        updateFilterCounts();
        if (liveRecords && liveRecords.length > 0) filterLiveRecords(currentFilter);
      }
      fetchOutreachHistory();

      setTimeout(() => {
        closeSmsModal();
      }, 2400);
    } else {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
      banner.innerHTML = `⚠️ <b>Send Failed:</b> ${data.message}`;
    }
  } catch (err) {
    banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
    banner.innerHTML = `⚠️ <b>Error:</b> Could not reach backend server or SMS Gateway: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>🚀</span> <span>Send SMS via Phone</span>`;
  }
}

function openSmsSettingsModal() {
  const modal = document.getElementById("smsSettingsModal");
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }

  // Populate from cache immediately if available
  const s = smsSettingsCache || {};
  const mode = s.mode || "local";
  const radios = document.getElementsByName("smsMode");
  for (let r of radios) {
    r.checked = (r.value === mode);
  }
  toggleSmsModeUI(mode);

  const baseEl = document.getElementById("smsBaseUrl");
  if (baseEl) baseEl.value = s.base_url || "http://192.168.1.100:8080";
  const userEl = document.getElementById("smsUsername");
  if (userEl) userEl.value = s.username || "admin";
  const passEl = document.getElementById("smsPassword");
  if (passEl) passEl.value = s.password || "";
  const simEl = document.getElementById("smsSimNumber");
  if (simEl) simEl.value = s.sim_number || 1;
  const tmplEl = document.getElementById("smsDefaultTemplate");
  if (tmplEl) tmplEl.value = s.template || SMS_TEMPLATES.cash_offer;

  const alertBox = document.getElementById("smsSettingsAlert");
  if (alertBox) alertBox.className = "hidden rounded-xl p-2.5 text-xs font-semibold text-center";

  // Re-fetch in background to ensure latest server state
  loadSmsSettings().then(() => {
    if (!smsSettingsCache) return;
    const latest = smsSettingsCache;
    const curMode = latest.mode || "local";
    for (let r of radios) {
      r.checked = (r.value === curMode);
    }
    toggleSmsModeUI(curMode);
    if (baseEl && document.activeElement !== baseEl) baseEl.value = latest.base_url || "http://192.168.1.100:8080";
    if (userEl && document.activeElement !== userEl) userEl.value = latest.username || "admin";
    if (passEl && document.activeElement !== passEl) passEl.value = latest.password || "";
    if (simEl) simEl.value = latest.sim_number || 1;
    if (tmplEl && document.activeElement !== tmplEl) tmplEl.value = latest.template || SMS_TEMPLATES.cash_offer;
  }).catch(() => {});
}

function closeSmsSettingsModal() {
  const modal = document.getElementById("smsSettingsModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

function toggleSmsModeUI(mode) {
  const localGroup = document.getElementById("localUrlGroup");
  if (localGroup) {
    localGroup.style.display = (mode === "local") ? "block" : "none";
  }
}

async function handleSaveSmsSettings(e) {
  e.preventDefault();
  let mode = "local";
  const radios = document.getElementsByName("smsMode");
  for (let r of radios) {
    if (r.checked) mode = r.value;
  }

  const payload = {
    mode: mode,
    base_url: document.getElementById("smsBaseUrl").value.trim() || "http://192.168.1.100:8080",
    username: document.getElementById("smsUsername").value.trim(),
    password: document.getElementById("smsPassword").value.trim(),
    sim_number: parseInt(document.getElementById("smsSimNumber").value || 1, 10),
    template: document.getElementById("smsDefaultTemplate").value.trim()
  };

  const alertBox = document.getElementById("smsSettingsAlert");

  try {
    const res = await fetch("/api/sms/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      smsSettingsCache = payload;
      SMS_TEMPLATES.cash_offer = payload.template;
      alertBox.className = "rounded-xl p-2.5 text-xs font-semibold text-center bg-emerald-950/50 border border-emerald-500/50 text-emerald-300 block";
      alertBox.innerText = "✓ SMS Gateway settings saved successfully!";
      setTimeout(() => closeSmsSettingsModal(), 1200);
    } else {
      throw new Error(`Server returned ${res.status}`);
    }
  } catch (err) {
    alertBox.className = "rounded-xl p-2.5 text-xs font-semibold text-center bg-rose-950/50 border border-rose-500/50 text-rose-300 block";
    alertBox.innerText = `Error saving settings: ${err.message}`;
  }
}

async function testSmsGatewayConnection() {
  const btn = document.getElementById("btnTestSmsConn");
  const alertBox = document.getElementById("smsSettingsAlert");

  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> <span>Pinging Phone...</span>`;
  alertBox.className = "hidden rounded-xl p-2.5 text-xs font-semibold text-center";

  // First save what the user typed in the inputs
  let mode = "local";
  const radios = document.getElementsByName("smsMode");
  for (let r of radios) {
    if (r.checked) mode = r.value;
  }
  const payload = {
    mode: mode,
    base_url: document.getElementById("smsBaseUrl").value.trim(),
    username: document.getElementById("smsUsername").value.trim(),
    password: document.getElementById("smsPassword").value,
    sim_number: parseInt(document.getElementById("smsSimNumber").value || "1"),
    template: document.getElementById("smsDefaultTemplate").value || SMS_TEMPLATES.cash_offer
  };

  try {
    await fetch("/api/sms/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const res = await fetch("/api/sms/test", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alertBox.className = "rounded-xl p-2.5 text-xs font-semibold text-center bg-emerald-950/60 border border-emerald-500/50 text-emerald-300 block";
      alertBox.innerText = `✓ ${data.message}`;
    } else {
      alertBox.className = "rounded-xl p-2.5 text-xs font-semibold text-center bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
      alertBox.innerText = `⚠️ ${data.message}`;
    }
  } catch (err) {
    alertBox.className = "rounded-xl p-2.5 text-xs font-semibold text-center bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
    alertBox.innerText = `Connection failed: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>🧪</span> <span>Test Connection</span>`;
  }
}

// -------------------------------------------------------------
// Email Outreach via SMTP2GO (mail.smtp2go.com)
// Brand: 407 Flips (john@407flips.com)
// -------------------------------------------------------------
const EMAIL_TEMPLATES = {
  lis_pendens: {
    name: "Pre-Foreclosure / Stop Foreclosure Auction",
    subject: "Cash Offer & Options to Stop Foreclosure: {Address}",
    bodyText: `Hi {FirstName},

I noticed public county records showing a pending foreclosure filing regarding your property at {Address}. I know how stressful this situation can be, but you still have legal rights and options to protect your equity before an auction date is set.

At 407 Flips, we buy Central Florida homes directly for cash:
• Stop the auction immediately with a binding contract & proof of funds
• Protect your credit and walk away with cash in hand
• $0 Realtor commissions, $0 inspection costs, and $0 closing fees
• We buy 100% As-Is — absolutely no repairs, painting, or cleaning required
• We work directly with your lender to obtain payoff statements

If you'd like to see what a fair cash offer looks like with zero obligation, please reply directly to this email or call/text me at (407) 555-FLIP.

Respectfully,
John Roberts | 407 Flips
Email: john@407flips.com | Phone: (407) 555-FLIP
Orlando, FL | Serving Central Florida Homeowners`,
    htmlTemplate: (vars) => `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; color: #1e293b;">
  <div style="background: linear-gradient(135deg, #0f172a, #1e293b); padding: 24px; text-align: left; border-bottom: 3px solid #0284c7;">
    <div style="font-size: 20px; font-weight: 800; color: #38bdf8; letter-spacing: -0.5px;">407 FLIPS</div>
    <div style="font-size: 11px; color: #94a3b8; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-top: 2px;">Direct Central Florida Property Solutions</div>
  </div>
  <div style="padding: 28px 24px;">
    <p style="font-size: 15px; line-height: 1.6; margin-top: 0;">Hi <strong>${vars.firstName}</strong>,</p>
    <p style="font-size: 14px; line-height: 1.6; color: #334155;">I noticed public county records showing a pending foreclosure filing regarding your property at <strong style="color: #0f172a;">${vars.address}</strong>. I know how overwhelming this can feel, but you still have legal rights and options to protect your home equity before an auction occurs.</p>
    
    <div style="background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 16px; margin: 20px 0;">
      <div style="font-size: 13px; font-weight: 700; color: #0369a1; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">How 407 Flips Can Help You:</div>
      <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #0c4a6e; line-height: 1.8;">
        <li><strong>Halt the Auction:</strong> We provide proof of funds and a binding contract to present to the court/lender.</li>
        <li><strong>Protect Your Equity:</strong> Walk away with cash in hand instead of losing everything at a courthouse sale.</li>
        <li><strong>Zero Fees:</strong> No real estate agent commissions, closing costs, or hidden junk fees.</li>
        <li><strong>Strictly As-Is:</strong> Zero repairs, no open houses, no cleaning necessary.</li>
      </ul>
    </div>

    <p style="font-size: 14px; line-height: 1.6; color: #334155;">Would you be open to a 5-minute phone call or simple cash offer to review your options with zero pressure? Simply reply directly to this email or call/text me at <strong>(407) 555-FLIP</strong>.</p>
    
    <div style="margin-top: 28px; padding-top: 18px; border-top: 1px solid #e2e8f0;">
      <div style="font-weight: 700; font-size: 14px; color: #0f172a;">John Roberts</div>
      <div style="font-size: 12px; color: #64748b;">Direct Buyer &amp; Acquisitions | 407 Flips</div>
      <div style="font-size: 12px; color: #0284c7; margin-top: 3px;">john@407flips.com &bull; (407) 555-FLIP</div>
    </div>
  </div>
  <div style="background: #f8fafc; padding: 16px 24px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8; text-align: center; line-height: 1.5;">
    407 Flips &bull; Orlando, FL (Central Florida)<br>
    If you received this email in error or do not wish to receive property inquiries, reply with "REMOVE" and we will immediately take you off our list.
  </div>
</div>`
  },
  probate: {
    name: "Probate / Inherited Property (Leave Furniture, No Cleanout)",
    subject: "Estate Inquiry & Direct Cash Offer: {Address}",
    bodyText: `Hi {FirstName},

Please accept my condolences if you have recently lost a family member. I am reaching out regarding the estate property at {Address}.

Settling an estate can be an exhausting process, especially when managing cleanouts, repairs, and probate court paperwork. 

At 407 Flips, we specialize in purchasing inherited Florida homes:
• Leave anything you don't want: furniture, old appliances, clothing, or clutter. We handle full disposal.
• No repairs needed — we buy strictly in current As-Is condition.
• Cash closing in as little as 7 to 14 days, or on whatever timeline works best for the heirs.
• Zero realtor commissions, no staging, and no open houses.

If you and the family are considering liquidating the property, I'd be honored to make a fair, all-cash offer with zero obligation.

Feel free to reply directly to this email or call/text me at (407) 555-FLIP.

Warm regards,
John Roberts | 407 Flips
Email: john@407flips.com | Phone: (407) 555-FLIP
Orlando, FL`,
    htmlTemplate: (vars) => `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; color: #1e293b;">
  <div style="background: linear-gradient(135deg, #0f172a, #1e293b); padding: 24px; text-align: left; border-bottom: 3px solid #8b5cf6;">
    <div style="font-size: 20px; font-weight: 800; color: #a78bfa; letter-spacing: -0.5px;">407 FLIPS</div>
    <div style="font-size: 11px; color: #94a3b8; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-top: 2px;">Central Florida Estate &amp; Inherited Property Solutions</div>
  </div>
  <div style="padding: 28px 24px;">
    <p style="font-size: 15px; line-height: 1.6; margin-top: 0;">Hi <strong>${vars.firstName}</strong>,</p>
    <p style="font-size: 14px; line-height: 1.6; color: #334155;">Please accept my condolences if you have recently lost a loved one. I am reaching out respectfully regarding the estate property at <strong style="color: #0f172a;">${vars.address}</strong>.</p>
    <p style="font-size: 14px; line-height: 1.6; color: #334155;">Handling an inherited home can be emotionally and financially draining — especially having to coordinate repairs, cleanouts, and heir distributions. We make this transition simple and stress-free.</p>
    
    <div style="background: #faf5ff; border: 1px solid #e9d5ff; border-radius: 8px; padding: 16px; margin: 20px 0;">
      <div style="font-size: 13px; font-weight: 700; color: #7e22ce; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">The 407 Flips Estate Promise:</div>
      <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #581c87; line-height: 1.8;">
        <li><strong>No Cleanout Required:</strong> Take only what you want. Leave behind old furniture, clothes, or unwanted items — we handle the rest.</li>
        <li><strong>100% As-Is Cash:</strong> No spending estate funds on paint, roofing, or updates.</li>
        <li><strong>Flexible Timeline:</strong> Close in as little as 10 days, or take all the time your family needs.</li>
        <li><strong>Zero Commissions:</strong> Keep 100% of the proceeds without real estate agent fees.</li>
      </ul>
    </div>

    <p style="font-size: 14px; line-height: 1.6; color: #334155;">If you are open to receiving a quick, hassle-free cash offer, simply reply to this email or call/text me directly at <strong>(407) 555-FLIP</strong>.</p>
    
    <div style="margin-top: 28px; padding-top: 18px; border-top: 1px solid #e2e8f0;">
      <div style="font-weight: 700; font-size: 14px; color: #0f172a;">John Roberts</div>
      <div style="font-size: 12px; color: #64748b;">Direct Buyer &amp; Acquisitions | 407 Flips</div>
      <div style="font-size: 12px; color: #7c3aed; margin-top: 3px;">john@407flips.com &bull; (407) 555-FLIP</div>
    </div>
  </div>
  <div style="background: #f8fafc; padding: 16px 24px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8; text-align: center; line-height: 1.5;">
    407 Flips &bull; Orlando, FL (Central Florida)<br>
    If you received this email in error or prefer not to receive property inquiries, reply with "REMOVE".
  </div>
</div>`
  },
  code_violation: {
    name: "Code Violations / Heavy Repairs (Taking Over Liens As-Is)",
    subject: "As-Is Cash Offer (We Take Over Violations): {Address}",
    bodyText: `Hi {FirstName},

I am contacting you regarding your property at {Address}. 

I work with local Florida homeowners who are dealing with burdensome code enforcement citations, daily municipal fines, open permits, or substantial deferred maintenance. Dealing with the city and contractors can quickly turn into a financial nightmare.

At 407 Flips, we buy houses in ANY physical condition:
• We take over existing city code violations and municipal liens
• Zero repair demands — roof damage, plumbing, electrical, or structural issues welcome
• All-cash purchase with no appraisal contingencies or bank inspection delays
• Fast closing on your preferred date (7–14 days)
• Zero fees or closing expenses to you

If you'd like to walk away with cash and let us handle the city and repairs, reply directly to this email or call/text me at (407) 555-FLIP.

Best regards,
John Roberts | 407 Flips
Email: john@407flips.com | Phone: (407) 555-FLIP
Orlando, FL`,
    htmlTemplate: (vars) => `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; color: #1e293b;">
  <div style="background: linear-gradient(135deg, #0f172a, #1e293b); padding: 24px; text-align: left; border-bottom: 3px solid #f59e0b;">
    <div style="font-size: 20px; font-weight: 800; color: #fbbf24; letter-spacing: -0.5px;">407 FLIPS</div>
    <div style="font-size: 11px; color: #94a3b8; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-top: 2px;">Central Florida As-Is Distressed Property Solutions</div>
  </div>
  <div style="padding: 28px 24px;">
    <p style="font-size: 15px; line-height: 1.6; margin-top: 0;">Hi <strong>${vars.firstName}</strong>,</p>
    <p style="font-size: 14px; line-height: 1.6; color: #334155;">I am reaching out regarding your property at <strong style="color: #0f172a;">${vars.address}</strong>. We frequently work with homeowners who are dealing with municipal code enforcement citations, accruing daily fines, or major deferred maintenance.</p>
    
    <div style="background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 16px; margin: 20px 0;">
      <div style="font-size: 13px; font-weight: 700; color: #b45309; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">We Buy As-Is — No Fixes Required:</div>
      <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #78350f; line-height: 1.8;">
        <li><strong>We Take Over City Fines:</strong> We purchase subject to existing municipal code liens and open permits.</li>
        <li><strong>Any Condition:</strong> Roof leaks, termite issues, electrical/plumbing problems, or major damage.</li>
        <li><strong>Guaranteed Cash Close:</strong> No mortgage underwriters or appraisal red tape.</li>
        <li><strong>$0 Commissions:</strong> You pay zero agent commissions or title closing costs.</li>
      </ul>
    </div>

    <p style="font-size: 14px; line-height: 1.6; color: #334155;">Would you be interested in receiving an all-cash offer to walk away cleanly and let us handle the headaches? Reply to this email or call/text me at <strong>(407) 555-FLIP</strong>.</p>
    
    <div style="margin-top: 28px; padding-top: 18px; border-top: 1px solid #e2e8f0;">
      <div style="font-weight: 700; font-size: 14px; color: #0f172a;">John Roberts</div>
      <div style="font-size: 12px; color: #64748b;">Direct Buyer &amp; Acquisitions | 407 Flips</div>
      <div style="font-size: 12px; color: #d97706; margin-top: 3px;">john@407flips.com &bull; (407) 555-FLIP</div>
    </div>
  </div>
  <div style="background: #f8fafc; padding: 16px 24px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8; text-align: center; line-height: 1.5;">
    407 Flips &bull; Orlando, FL (Central Florida)<br>
    If you received this email in error or do not wish to receive property inquiries, reply with "REMOVE".
  </div>
</div>`
  },
  quick_cash: {
    name: "Quick As-Is Cash Offer (Close in 7–14 Days)",
    subject: "Direct Cash Offer for {Address} - No Fees or Repairs",
    bodyText: `Hi {FirstName},

My name is John with 407 Flips. I am a local Florida private cash buyer actively purchasing homes in your neighborhood.

I am interested in making a direct, all-cash offer on your property at {Address}.

Why homeowners choose to work with 407 Flips:
• All-Cash Offer — No bank approvals, no appraisal hurdles
• As-Is Condition — No repairs, painting, or cleaning needed
• Fast & Flexible Closing — Close in 7–14 days or on your chosen date
• Zero Expenses — No 6% Realtor commissions and no seller closing costs

If you have considered selling or simply want to know what a cash offer on your property would look like, please reply to this email or call/text me at (407) 555-FLIP.

Best regards,
John Roberts | 407 Flips
Email: john@407flips.com | Phone: (407) 555-FLIP
Orlando, FL`,
    htmlTemplate: (vars) => `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; color: #1e293b;">
  <div style="background: linear-gradient(135deg, #0f172a, #1e293b); padding: 24px; text-align: left; border-bottom: 3px solid #06b6d4;">
    <div style="font-size: 20px; font-weight: 800; color: #22d3ee; letter-spacing: -0.5px;">407 FLIPS</div>
    <div style="font-size: 11px; color: #94a3b8; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-top: 2px;">Direct Central Florida Property Acquisitions</div>
  </div>
  <div style="padding: 28px 24px;">
    <p style="font-size: 15px; line-height: 1.6; margin-top: 0;">Hi <strong>${vars.firstName}</strong>,</p>
    <p style="font-size: 14px; line-height: 1.6; color: #334155;">My name is John with <strong>407 Flips</strong>. I am a local private buyer actively purchasing homes in your neighborhood, and I am reaching out to see if you would be open to a direct cash offer for <strong style="color: #0f172a;">${vars.address}</strong>.</p>
    
    <div style="background: #ecfeff; border: 1px solid #a5f3fc; border-radius: 8px; padding: 16px; margin: 20px 0;">
      <div style="font-size: 13px; font-weight: 700; color: #0e7490; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">The 407 Flips Cash Advantage:</div>
      <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #164e63; line-height: 1.8;">
        <li><strong>All Cash:</strong> No bank mortgage delays, appraisal gaps, or lender red tape.</li>
        <li><strong>Strictly As-Is:</strong> Sell in whatever condition it's in. Zero repairs or cleaning.</li>
        <li><strong>You Pick the Date:</strong> Fast close in 7–14 days, or take several months if needed.</li>
        <li><strong>Zero Commissions:</strong> Keep 100% of your net proceeds. We cover closing costs.</li>
      </ul>
    </div>

    <p style="font-size: 14px; line-height: 1.6; color: #334155;">If you are interested in a fair, no-obligation cash offer, simply reply directly to this email or call/text me at <strong>(407) 555-FLIP</strong>.</p>
    
    <div style="margin-top: 28px; padding-top: 18px; border-top: 1px solid #e2e8f0;">
      <div style="font-weight: 700; font-size: 14px; color: #0f172a;">John Roberts</div>
      <div style="font-size: 12px; color: #64748b;">Direct Buyer &amp; Acquisitions | 407 Flips</div>
      <div style="font-size: 12px; color: #0891b2; margin-top: 3px;">john@407flips.com &bull; (407) 555-FLIP</div>
    </div>
  </div>
  <div style="background: #f8fafc; padding: 16px 24px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8; text-align: center; line-height: 1.5;">
    407 Flips &bull; Orlando, FL (Central Florida)<br>
    If you received this email in error or do not wish to receive property inquiries, reply with "REMOVE".
  </div>
</div>`
  }
};

let emailSettingsCache = null;

async function loadEmailSettings() {
  try {
    const res = await fetch("/api/email/settings");
    if (res.ok) {
      emailSettingsCache = await res.json();
    }
  } catch (err) {
    console.warn("Could not load email settings:", err);
  }
}

function openEmailModal(parcelId, email, ownerName, propertyAddress) {
  const modal = document.getElementById("emailModal");
  if (!modal) return;

  modal.classList.remove("hidden");
  modal.style.display = "flex";

  try {
    const pidEl = document.getElementById("emailParcelId");
    if (pidEl) pidEl.value = parcelId || "";
    const cntyEl = document.getElementById("emailCounty");
    if (cntyEl) cntyEl.value = selectedCountyKey || "Pinellas";
    const ownEl = document.getElementById("emailOwnerName");
    if (ownEl) ownEl.value = ownerName || "";
    const addrEl = document.getElementById("emailPropertyAddress");
    if (addrEl) addrEl.value = propertyAddress || "";

    const ownDisp = document.getElementById("emailOwnerDisplay");
    if (ownDisp) ownDisp.innerText = ownerName || "Homeowner";
    const addrDisp = document.getElementById("emailAddressDisplay");
    if (addrDisp) addrDisp.innerText = propertyAddress || "Florida Property";
    const emailInput = document.getElementById("emailRecipientInput");
    if (emailInput) emailInput.value = email || "";

    const banner = document.getElementById("emailStatusBanner");
    if (banner) {
      banner.className = "hidden p-3 rounded-xl text-xs font-semibold";
      banner.innerText = "";
    }

    // Refresh email template dropdown options from cache
    const tmplSelect = document.getElementById("emailTemplateSelect");
    if (tmplSelect && outreachTemplatesCache && outreachTemplatesCache.email) {
      const curVal = tmplSelect.value;
      tmplSelect.innerHTML = "";
      outreachTemplatesCache.email.forEach(t => {
        const opt = document.createElement("option");
        opt.value = t.id;
        opt.textContent = t.name;
        tmplSelect.appendChild(opt);
      });
      if (curVal && outreachTemplatesCache.email.some(t => t.id === curVal)) {
        tmplSelect.value = curVal;
      } else {
        // Auto select by filter
        let defId = "lis_pendens";
        if (currentFilter === "probate") defId = "probate";
        else if (currentFilter === "code") defId = "code_violation";
        tmplSelect.value = outreachTemplatesCache.email.some(t => t.id === defId) ? defId : outreachTemplatesCache.email[0]?.id;
      }
    }

    const activeKey = tmplSelect ? tmplSelect.value : "lis_pendens";
    applyEmailTemplate(activeKey);
  } catch (err) {
    console.error("Error setting up email modal:", err);
  }
}

function closeEmailModal() {
  const modal = document.getElementById("emailModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

function applyEmailTemplate(templateKey) {
  let tmpl = null;
  if (outreachTemplatesCache && outreachTemplatesCache.email) {
    tmpl = outreachTemplatesCache.email.find(t => t.id === templateKey);
  }
  if (!tmpl) {
    tmpl = EMAIL_TEMPLATES[templateKey] || EMAIL_TEMPLATES.lis_pendens;
  }

  const rawOwner = document.getElementById("emailOwnerName")?.value || "Homeowner";
  const rawAddr = document.getElementById("emailPropertyAddress")?.value || "your property";

  const nameParts = rawOwner.trim().split(/\s+/);
  let firstName = nameParts[0] || "Homeowner";
  firstName = firstName.charAt(0).toUpperCase() + firstName.slice(1).toLowerCase();
  const lastName = nameParts.length > 1 ? nameParts[nameParts.length - 1] : "";

  const addrParts = rawAddr.split(",");
  const streetAddr = addrParts[0]?.trim() || rawAddr;
  const city = selectedCountyKey || "Orlando";

  const vars = {
    firstName: firstName,
    lastName: lastName,
    address: streetAddr,
    city: city,
    fullName: rawOwner,
    state: currentState || "FL",
    county: selectedCountyKey || "Pinellas",
    phone: "(407) 555-FLIP"
  };

  const subjectTemplate = tmpl.subject || "Direct Cash Offer: {Address}";
  const subject = subjectTemplate
    .replace(/{FirstName}/g, firstName)
    .replace(/{LastName}/g, lastName)
    .replace(/{Address}/g, streetAddr)
    .replace(/{City}/g, city)
    .replace(/{State}/g, currentState || "FL")
    .replace(/{County}/g, selectedCountyKey || "Pinellas")
    .replace(/{Phone}/g, "(407) 555-FLIP");

  const subjectEl = document.getElementById("emailSubjectInput");
  if (subjectEl) subjectEl.value = subject;

  const rawBody = tmpl.body || tmpl.bodyText || "";
  const textBody = rawBody
    .replace(/{FirstName}/g, firstName)
    .replace(/{LastName}/g, lastName)
    .replace(/{Address}/g, streetAddr)
    .replace(/{City}/g, city)
    .replace(/{State}/g, currentState || "FL")
    .replace(/{County}/g, selectedCountyKey || "Pinellas")
    .replace(/{Phone}/g, "(407) 555-FLIP");

  const textEl = document.getElementById("emailMessageText");
  if (textEl) textEl.value = textBody;

  const htmlPreviewEl = document.getElementById("emailHtmlPreview");
  if (htmlPreviewEl) {
    htmlPreviewEl.innerHTML = formatEmailHtml(textBody, vars, tmpl.category);
  }
}

async function handleSendEmail(e) {
  e.preventDefault();
  const recipientEmail = document.getElementById("emailRecipientInput").value.trim();
  const subject = document.getElementById("emailSubjectInput").value.trim();
  const messageBody = document.getElementById("emailMessageText").value.trim();
  const parcelId = document.getElementById("emailParcelId").value;
  const county = document.getElementById("emailCounty").value;
  const ownerName = document.getElementById("emailOwnerName").value;
  const propertyAddress = document.getElementById("emailPropertyAddress").value;
  const templateType = document.getElementById("emailTemplateSelect").value;

  const nameParts = (ownerName || "Homeowner").trim().split(/\s+/);
  let firstName = nameParts[0] || "Homeowner";
  firstName = firstName.charAt(0).toUpperCase() + firstName.slice(1).toLowerCase();
  const streetAddr = (propertyAddress || "").split(",")[0]?.trim() || propertyAddress;
  
  const vars = {
    firstName: firstName,
    lastName: nameParts.length > 1 ? nameParts[nameParts.length - 1] : "",
    address: streetAddr,
    city: selectedCountyKey || "Orlando",
    fullName: ownerName,
    state: currentState || "FL",
    county: county || "Pinellas",
    phone: "(407) 555-FLIP"
  };

  const htmlContent = formatEmailHtml(messageBody, vars, templateType);

  const btn = document.getElementById("btnSendEmailSubmit");
  const banner = document.getElementById("emailStatusBanner");

  if (!recipientEmail || !subject || !messageBody) {
    alert("Please provide recipient email, subject line, and message content.");
    return;
  }

  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> <span>Sending via SMTP2GO...</span>`;
  banner.className = "hidden p-3 rounded-xl text-xs font-semibold";

  try {
    const res = await fetch("/api/email/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recipient_email: recipientEmail,
        recipient_name: ownerName,
        property_address: propertyAddress,
        subject: subject,
        html_content: htmlContent,
        parcel_id: parcelId,
        county: county,
        template_type: templateType
      })
    });

    const data = await res.json();
    if (data.status === "success") {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-cyan-950/60 border border-cyan-500/50 text-cyan-300 block";
      banner.innerHTML = `✓ Email offer dispatched successfully to <b>${recipientEmail}</b> via SMTP2GO! Replies will route to your 407 Flips inbox.`;

      // Update local contacts cache
      if (parcelId) {
        if (!savedContactsCache[parcelId]) savedContactsCache[parcelId] = {};
        savedContactsCache[parcelId].email = recipientEmail;
        savedContactsCache[parcelId].last_email_sent = "Just now";
        savedContactsCache[parcelId].last_email_status = "SENT";
        updateSavedPipelineCount();
        updateFilterCounts();
        if (liveRecords && liveRecords.length > 0) filterLiveRecords(currentFilter);
      }
      fetchOutreachHistory();

      setTimeout(() => {
        closeEmailModal();
      }, 2400);
    } else {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
      banner.innerHTML = `⚠️ <b>Send Failed:</b> ${data.message}`;
    }
  } catch (err) {
    banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
    banner.innerHTML = `⚠️ <b>Error:</b> Could not reach backend server or SMTP2GO: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>🚀</span> <span>Send Email Offer via SMTP2GO</span>`;
  }
}

function openEmailSettingsModal() {
  const modal = document.getElementById("emailSettingsModal");
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }

  const s = emailSettingsCache || {};
  const serverEl = document.getElementById("emailSmtpServer");
  if (serverEl) serverEl.value = s.smtp_server || "mail.smtp2go.com";
  const portEl = document.getElementById("emailSmtpPort");
  if (portEl) portEl.value = s.smtp_port || 2525;
  const userEl = document.getElementById("emailSmtpUser");
  if (userEl) userEl.value = s.smtp_user || "407flips.com";
  const passEl = document.getElementById("emailSmtpPassword");
  if (passEl) passEl.value = s.smtp_password || "";
  const nameEl = document.getElementById("emailSenderName");
  if (nameEl) nameEl.value = s.sender_name || "John Roberts | 407 Flips";
  const fromEl = document.getElementById("emailSenderEmail");
  if (fromEl) fromEl.value = s.sender_email || "john@407flips.com";
  const replyEl = document.getElementById("emailReplyTo");
  if (replyEl) replyEl.value = s.reply_to || "john@407flips.com";
  const phoneEl = document.getElementById("emailCompanyPhone");
  if (phoneEl) phoneEl.value = s.company_phone || "(407) 555-FLIP";

  const alertBox = document.getElementById("emailSettingsAlert");
  if (alertBox) alertBox.className = "hidden rounded-xl p-2.5 text-xs font-semibold text-center";

  // Re-fetch in background
  loadEmailSettings().then(() => {
    if (!emailSettingsCache) return;
    const latest = emailSettingsCache;
    if (serverEl && document.activeElement !== serverEl) serverEl.value = latest.smtp_server || "mail.smtp2go.com";
    if (portEl && document.activeElement !== portEl) portEl.value = latest.smtp_port || 2525;
    if (userEl && document.activeElement !== userEl) userEl.value = latest.smtp_user || "407flips.com";
    if (passEl && document.activeElement !== passEl) passEl.value = latest.smtp_password || "";
    if (nameEl && document.activeElement !== nameEl) nameEl.value = latest.sender_name || "John Roberts | 407 Flips";
    if (fromEl && document.activeElement !== fromEl) fromEl.value = latest.sender_email || "john@407flips.com";
    if (replyEl && document.activeElement !== replyEl) replyEl.value = latest.reply_to || "john@407flips.com";
    if (phoneEl && document.activeElement !== phoneEl) phoneEl.value = latest.company_phone || "(407) 555-FLIP";
  }).catch(() => {});
}

function closeEmailSettingsModal() {
  const modal = document.getElementById("emailSettingsModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

async function handleSaveEmailSettings(e) {
  e.preventDefault();
  const payload = {
    smtp_server: document.getElementById("emailSmtpServer").value.trim() || "mail.smtp2go.com",
    smtp_port: parseInt(document.getElementById("emailSmtpPort").value || "2525", 10),
    smtp_user: document.getElementById("emailSmtpUser").value.trim() || "407flips.com",
    smtp_password: document.getElementById("emailSmtpPassword").value.trim(),
    sender_name: document.getElementById("emailSenderName").value.trim() || "John Roberts | 407 Flips",
    sender_email: document.getElementById("emailSenderEmail").value.trim() || "john@407flips.com",
    reply_to: document.getElementById("emailReplyTo").value.trim() || "john@407flips.com",
    company_name: "407 Flips",
    company_phone: document.getElementById("emailCompanyPhone").value.trim() || "(407) 555-FLIP",
    business_address: "Orlando, FL (Central Florida)"
  };

  const alertBox = document.getElementById("emailSettingsAlert");

  try {
    const res = await fetch("/api/email/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      emailSettingsCache = payload;
      alertBox.className = "rounded-xl p-2.5 text-xs font-semibold text-center bg-cyan-950/50 border border-cyan-500/50 text-cyan-300 block";
      alertBox.innerText = "✓ SMTP2GO Email Gateway settings saved successfully!";
      setTimeout(() => closeEmailSettingsModal(), 1200);
    } else {
      throw new Error(`Server returned ${res.status}`);
    }
  } catch (err) {
    alertBox.className = "rounded-xl p-2.5 text-xs font-semibold text-center bg-rose-950/50 border border-rose-500/50 text-rose-300 block";
    alertBox.innerText = `Error saving settings: ${err.message}`;
  }
}

async function testEmailGatewayConnection() {
  const btn = document.getElementById("btnTestEmailConn");
  const alertBox = document.getElementById("emailSettingsAlert");

  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> <span>Testing SMTP2GO...</span>`;
  alertBox.className = "hidden rounded-xl p-2.5 text-xs font-semibold text-center";

  // First save what the user typed in the inputs
  const payload = {
    smtp_server: document.getElementById("emailSmtpServer").value.trim() || "mail.smtp2go.com",
    smtp_port: parseInt(document.getElementById("emailSmtpPort").value || "2525", 10),
    smtp_user: document.getElementById("emailSmtpUser").value.trim() || "407flips.com",
    smtp_password: document.getElementById("emailSmtpPassword").value.trim(),
    sender_name: document.getElementById("emailSenderName").value.trim() || "John Roberts | 407 Flips",
    sender_email: document.getElementById("emailSenderEmail").value.trim() || "john@407flips.com",
    reply_to: document.getElementById("emailReplyTo").value.trim() || "john@407flips.com",
    company_name: "407 Flips",
    company_phone: document.getElementById("emailCompanyPhone").value.trim() || "(407) 555-FLIP",
    business_address: "Orlando, FL (Central Florida)"
  };

  try {
    await fetch("/api/email/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const res = await fetch("/api/email/test", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alertBox.className = "rounded-xl p-2.5 text-xs font-semibold text-center bg-cyan-950/60 border border-cyan-500/50 text-cyan-300 block";
      alertBox.innerText = `✓ ${data.message}`;
    } else {
      alertBox.className = "rounded-xl p-2.5 text-xs font-semibold text-center bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
      alertBox.innerText = `⚠️ ${data.message}`;
    }
  } catch (err) {
    alertBox.className = "rounded-xl p-2.5 text-xs font-semibold text-center bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
    alertBox.innerText = `Connection failed: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>🧪</span> <span>Test Connection</span>`;
  }
}

// -------------------------------------------------------------
// Outreach Script & Template Manager Controller
// -------------------------------------------------------------

async function fetchOutreachTemplates() {
  try {
    const res = await fetch("/api/templates");
    if (res.ok) {
      outreachTemplatesCache = await res.json();
      updateTemplateCounters();
      updateDropdownSelectors();
    }
  } catch (err) {
    console.error("Error fetching outreach templates:", err);
  }
}

function updateTemplateCounters() {
  if (!outreachTemplatesCache) return;
  const smsCount = (outreachTemplatesCache.sms || []).length;
  const emailCount = (outreachTemplatesCache.email || []).length;
  const smsBadge = document.getElementById("countTemplatesSms");
  if (smsBadge) smsBadge.innerText = smsCount;
  const emailBadge = document.getElementById("countTemplatesEmail");
  if (emailBadge) emailBadge.innerText = emailCount;
}

function updateDropdownSelectors() {
  if (!outreachTemplatesCache) return;

  // SMS Dropdown
  const smsSelect = document.getElementById("smsTemplateSelect");
  if (smsSelect && outreachTemplatesCache.sms) {
    const prev = smsSelect.value;
    smsSelect.innerHTML = "";
    outreachTemplatesCache.sms.forEach(t => {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = t.name;
      smsSelect.appendChild(opt);
    });
    if (prev && outreachTemplatesCache.sms.some(t => t.id === prev)) {
      smsSelect.value = prev;
    }
  }

  // Email Dropdown
  const emailSelect = document.getElementById("emailTemplateSelect");
  if (emailSelect && outreachTemplatesCache.email) {
    const prev = emailSelect.value;
    emailSelect.innerHTML = "";
    outreachTemplatesCache.email.forEach(t => {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = t.name;
      emailSelect.appendChild(opt);
    });
    if (prev && outreachTemplatesCache.email.some(t => t.id === prev)) {
      emailSelect.value = prev;
    }
  }
}

function openTemplatesModal(channel = 'sms') {
  const modal = document.getElementById("templatesModal");
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }

  // Ensure latest templates are loaded
  if (!outreachTemplatesCache) {
    fetchOutreachTemplates().then(() => {
      switchTemplatesChannel(channel);
    });
  } else {
    switchTemplatesChannel(channel);
  }
}

function closeTemplatesModal() {
  const modal = document.getElementById("templatesModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

function switchTemplatesChannel(channel) {
  activeTemplatesChannel = channel;
  const tabSms = document.getElementById("tabTemplatesSms");
  const tabEmail = document.getElementById("tabTemplatesEmail");
  const subjectGroup = document.getElementById("tplSubjectGroup");

  if (channel === 'sms') {
    if (tabSms) tabSms.className = "px-4 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-2 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm cursor-pointer";
    if (tabEmail) tabEmail.className = "px-4 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-2 bg-slate-800 text-slate-400 hover:text-white border border-slate-700 cursor-pointer";
    if (subjectGroup) subjectGroup.classList.add("hidden");
  } else {
    if (tabSms) tabSms.className = "px-4 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-2 bg-slate-800 text-slate-400 hover:text-white border border-slate-700 cursor-pointer";
    if (tabEmail) tabEmail.className = "px-4 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-2 bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm cursor-pointer";
    if (subjectGroup) subjectGroup.classList.remove("hidden");
  }

  const searchInput = document.getElementById("tplSearchInput");
  if (searchInput) searchInput.value = "";

  renderTemplatesList();
  
  // Select first template by default if available
  const list = (outreachTemplatesCache && outreachTemplatesCache[activeTemplatesChannel]) || [];
  if (list.length > 0) {
    selectTemplateForEdit(list[0].id);
  } else {
    clearTemplateEditor();
  }
}

function filterTemplateList(query) {
  renderTemplatesList(query);
}

function renderTemplatesList(filterText = '') {
  const container = document.getElementById("templateItemsList");
  if (!container) return;

  const rawList = (outreachTemplatesCache && outreachTemplatesCache[activeTemplatesChannel]) || [];
  const q = (filterText || "").trim().toLowerCase();

  const list = q ? rawList.filter(t => 
    (t.name || "").toLowerCase().includes(q) ||
    (t.body || "").toLowerCase().includes(q) ||
    (t.category || "").toLowerCase().includes(q) ||
    (t.subject || "").toLowerCase().includes(q)
  ) : rawList;

  if (list.length === 0) {
    container.innerHTML = `
      <div class="p-6 text-center text-slate-500 text-xs">
        ${q ? 'No templates match your search.' : 'No templates found in this category.'}
      </div>
    `;
    return;
  }

  container.innerHTML = "";
  list.forEach(t => {
    const isSelected = (t.id === selectedTemplateId);
    const card = document.createElement("div");
    card.className = `p-3 rounded-xl border cursor-pointer transition flex flex-col gap-1.5 ${
      isSelected 
        ? (activeTemplatesChannel === 'sms' ? 'bg-emerald-950/40 border-emerald-500/60 ring-1 ring-emerald-500/40' : 'bg-cyan-950/40 border-cyan-500/60 ring-1 ring-cyan-500/40')
        : 'bg-[#0d1424] border-slate-800 hover:border-slate-700 hover:bg-slate-900/60'
    }`;
    
    // Category label formatting
    const catLabels = {
      cash_offer: "Cash Offer",
      lis_pendens: "Pre-Foreclosure",
      probate: "Probate / Estate",
      probate_estate: "Probate / Estate",
      code_violations: "Code Violation",
      code_violation: "Code Violation",
      followup: "Follow-up",
      custom: "Custom"
    };
    const catName = catLabels[t.category] || t.category || "General";
    const snippet = (t.body || "").slice(0, 75) + ((t.body || "").length > 75 ? "..." : "");

    card.innerHTML = `
      <div class="flex items-center justify-between gap-1.5">
        <span class="text-xs font-bold text-white truncate">${t.name}</span>
        <span class="px-2 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider shrink-0 bg-slate-800 text-slate-300 border border-slate-700">${catName}</span>
      </div>
      <div class="text-[11px] text-slate-400 line-clamp-2 leading-relaxed font-sans">${snippet}</div>
    `;
    card.onclick = () => selectTemplateForEdit(t.id);
    container.appendChild(card);
  });
}

function selectTemplateForEdit(id) {
  selectedTemplateId = id;
  const list = (outreachTemplatesCache && outreachTemplatesCache[activeTemplatesChannel]) || [];
  const t = list.find(item => item.id === id);
  if (!t) return;

  const idEl = document.getElementById("tplId");
  if (idEl) idEl.value = t.id;

  const nameEl = document.getElementById("tplName");
  if (nameEl) nameEl.value = t.name || "";

  const catEl = document.getElementById("tplCategory");
  if (catEl) {
    let catVal = t.category || "custom";
    if (catVal === "probate_estate") catVal = "probate";
    if (catVal === "code_violation") catVal = "code_violations";
    catEl.value = catVal;
  }

  const subjEl = document.getElementById("tplSubject");
  if (subjEl) subjEl.value = t.subject || "";

  const bodyEl = document.getElementById("tplBody");
  if (bodyEl) bodyEl.value = t.body || "";

  const statusBanner = document.getElementById("tplStatusBanner");
  if (statusBanner) {
    statusBanner.className = "hidden p-3 rounded-xl text-xs font-semibold text-center";
    statusBanner.innerText = "";
  }

  // Update char count and live preview
  handleTemplateBodyChange();

  // Re-highlight active card in list
  renderTemplatesList(document.getElementById("tplSearchInput")?.value || "");
}

function clearTemplateEditor() {
  selectedTemplateId = null;
  const idEl = document.getElementById("tplId");
  if (idEl) idEl.value = "";
  const nameEl = document.getElementById("tplName");
  if (nameEl) nameEl.value = "";
  const subjEl = document.getElementById("tplSubject");
  if (subjEl) subjEl.value = "";
  const bodyEl = document.getElementById("tplBody");
  if (bodyEl) bodyEl.value = "";
  const countEl = document.getElementById("tplCharCount");
  if (countEl) countEl.innerText = "0 chars";
  const previewEl = document.getElementById("tplLivePreviewContainer");
  if (previewEl) previewEl.innerHTML = `<div class="text-xs text-slate-500 italic p-4 text-center">No template selected. Create or select a template to preview.</div>`;
}

function handleTemplateBodyChange() {
  const bodyEl = document.getElementById("tplBody");
  const countEl = document.getElementById("tplCharCount");
  const text = bodyEl ? bodyEl.value : "";

  if (countEl) {
    const len = text.length;
    if (activeTemplatesChannel === 'sms') {
      const segs = Math.ceil(len / 160) || 1;
      countEl.innerText = `${len} chars (${segs} SMS segment${segs > 1 ? 's' : ''})`;
    } else {
      const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;
      countEl.innerText = `${len} chars • ${wordCount} words`;
    }
  }

  updateLivePreview();
}

function updateLivePreview() {
  const container = document.getElementById("tplLivePreviewContainer");
  if (!container) return;

  const bodyText = document.getElementById("tplBody")?.value || "";
  const sampleVars = {
    firstName: "Joseph",
    lastName: "Ibrahim",
    address: "10440 66th Ave",
    city: "Seminole",
    state: currentState || "FL",
    county: selectedCountyKey || "Pinellas",
    phone: "(407) 555-FLIP"
  };

  if (activeTemplatesChannel === 'sms') {
    let filled = bodyText
      .replace(/{FirstName}/g, sampleVars.firstName)
      .replace(/{LastName}/g, sampleVars.lastName)
      .replace(/{Address}/g, sampleVars.address)
      .replace(/{City}/g, sampleVars.city)
      .replace(/{State}/g, sampleVars.state)
      .replace(/{County}/g, sampleVars.county)
      .replace(/{Phone}/g, sampleVars.phone);

    container.innerHTML = `
      <div class="max-w-sm mx-auto bg-slate-900 rounded-2xl p-3 border border-slate-800 shadow-lg">
        <div class="flex items-center justify-between text-[10px] text-slate-400 pb-2 border-b border-slate-800 mb-2 font-mono">
          <span>Cellular Recipient Phone</span>
          <span>(727) 555-0199</span>
        </div>
        <div class="flex flex-col gap-1 items-start">
          <div class="bg-blue-600 text-white text-xs px-3.5 py-2.5 rounded-2xl rounded-tl-sm max-w-[90%] leading-relaxed shadow font-sans">
            ${filled || '<span class="text-blue-200 italic">Empty message...</span>'}
          </div>
          <span class="text-[9px] text-slate-500 ml-1">Delivered &bull; Just now</span>
        </div>
      </div>
    `;
  } else {
    // Email preview
    const subjText = document.getElementById("tplSubject")?.value || "Offer for {Address}";
    const filledSubj = subjText
      .replace(/{FirstName}/g, sampleVars.firstName)
      .replace(/{LastName}/g, sampleVars.lastName)
      .replace(/{Address}/g, sampleVars.address)
      .replace(/{City}/g, sampleVars.city)
      .replace(/{State}/g, sampleVars.state)
      .replace(/{County}/g, sampleVars.county)
      .replace(/{Phone}/g, sampleVars.phone);

    const emailHtml = formatEmailHtml(bodyText, sampleVars);

    container.innerHTML = `
      <div class="space-y-2">
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-2.5 text-xs text-slate-300">
          <div class="flex items-center gap-2 text-slate-400 text-[11px] mb-1">
            <span class="font-bold text-slate-300">Subject:</span>
            <span class="text-white font-medium">${filledSubj}</span>
          </div>
          <div class="text-[10px] text-slate-500">From: John Roberts &lt;john@407flips.com&gt; &bull; To: joseph.ibrahim@example.com</div>
        </div>
        <div class="max-h-64 overflow-y-auto rounded-xl border border-slate-800 bg-white">
          ${emailHtml}
        </div>
      </div>
    `;
  }
}

function insertTagIntoTemplate(tag) {
  const textarea = document.getElementById("tplBody");
  if (!textarea) return;

  const start = textarea.selectionStart || 0;
  const end = textarea.selectionEnd || 0;
  const current = textarea.value;

  textarea.value = current.substring(0, start) + tag + current.substring(end);
  textarea.focus();
  const nextPos = start + tag.length;
  textarea.setSelectionRange(nextPos, nextPos);

  handleTemplateBodyChange();
}

function createNewTemplatePrompt() {
  if (!outreachTemplatesCache) outreachTemplatesCache = { sms: [], email: [] };
  if (!outreachTemplatesCache[activeTemplatesChannel]) outreachTemplatesCache[activeTemplatesChannel] = [];

  const newId = `custom_${Date.now()}`;
  const isEmail = (activeTemplatesChannel === 'email');
  const newTpl = {
    id: newId,
    name: isEmail ? "✨ New Custom Email Script" : "✨ New Custom SMS Script",
    category: "custom",
    body: isEmail 
      ? "Hi {FirstName},\n\nI am contacting you regarding your property at {Address}.\n\nAt 407 Flips, we buy properties in any condition for cash with zero fees.\n\nLet me know if you would be open to a quick call!\n\nBest regards,\nJohn Roberts | 407 Flips\nPhone: (407) 555-FLIP"
      : "Hi {FirstName}, I noticed your property at {Address}. I'm a local cash buyer and would love to make an as-is cash offer. Would you be open to an offer? Thanks!"
  };
  if (isEmail) {
    newTpl.subject = "Quick cash inquiry regarding {Address}";
  }

  outreachTemplatesCache[activeTemplatesChannel].unshift(newTpl);
  updateTemplateCounters();
  renderTemplatesList();
  selectTemplateForEdit(newId);

  const nameEl = document.getElementById("tplName");
  if (nameEl) {
    nameEl.focus();
    nameEl.select();
  }
}

async function handleSaveCurrentTemplate(e) {
  e.preventDefault();
  if (!outreachTemplatesCache) return;

  const id = document.getElementById("tplId")?.value;
  if (!id) {
    alert("Please select or create a template to save.");
    return;
  }

  const name = document.getElementById("tplName")?.value.trim();
  const category = document.getElementById("tplCategory")?.value;
  const body = document.getElementById("tplBody")?.value.trim();
  const subject = document.getElementById("tplSubject")?.value.trim();

  if (!name || !body) {
    alert("Please provide both a Template Name and Body content.");
    return;
  }

  const list = outreachTemplatesCache[activeTemplatesChannel] || [];
  let item = list.find(t => t.id === id);
  if (!item) {
    item = { id: id };
    list.push(item);
  }

  item.name = name;
  item.category = category;
  item.body = body;
  if (activeTemplatesChannel === 'email') {
    item.subject = subject || `Direct inquiry: {Address}`;
  }

  const banner = document.getElementById("tplStatusBanner");
  const saveBtn = document.getElementById("btnSaveTpl");

  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.innerHTML = `<span>⏳</span> <span>Saving...</span>`;
  }

  try {
    const res = await fetch("/api/templates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(outreachTemplatesCache)
    });

    if (res.ok) {
      if (banner) {
        banner.className = "p-3 rounded-xl text-xs font-semibold text-center bg-emerald-950/60 border border-emerald-500/50 text-emerald-300 block";
        banner.innerText = `✓ Template "${name}" saved successfully!`;
      }
      updateTemplateCounters();
      updateDropdownSelectors();
      renderTemplatesList(document.getElementById("tplSearchInput")?.value || "");
      setTimeout(() => {
        if (banner) banner.className = "hidden p-3 rounded-xl text-xs font-semibold text-center";
      }, 2500);
    } else {
      throw new Error(`Server returned HTTP ${res.status}`);
    }
  } catch (err) {
    if (banner) {
      banner.className = "p-3 rounded-xl text-xs font-semibold text-center bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
      banner.innerText = `⚠️ Failed to save template: ${err.message}`;
    }
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.innerHTML = `<span>💾</span> <span>Save Template</span>`;
    }
  }
}

async function handleDeleteCurrentTemplate() {
  const id = document.getElementById("tplId")?.value;
  if (!id) return;

  const list = (outreachTemplatesCache && outreachTemplatesCache[activeTemplatesChannel]) || [];
  const item = list.find(t => t.id === id);
  const name = item ? item.name : "this template";

  if (!confirm(`Are you sure you want to delete "${name}"?`)) {
    return;
  }

  outreachTemplatesCache[activeTemplatesChannel] = list.filter(t => t.id !== id);

  try {
    await fetch("/api/templates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(outreachTemplatesCache)
    });

    updateTemplateCounters();
    updateDropdownSelectors();
    renderTemplatesList();

    const remaining = outreachTemplatesCache[activeTemplatesChannel];
    if (remaining.length > 0) {
      selectTemplateForEdit(remaining[0].id);
    } else {
      clearTemplateEditor();
    }
  } catch (err) {
    alert("Could not delete template from server: " + err.message);
  }
}

async function handleResetTemplatesToDefaults() {
  if (!confirm("Are you sure you want to restore all factory SMS and Email templates back to defaults? Any custom scripts will be reset.")) {
    return;
  }

  try {
    const res = await fetch("/api/templates/reset", { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      outreachTemplatesCache = data.templates;
      updateTemplateCounters();
      updateDropdownSelectors();
      switchTemplatesChannel(activeTemplatesChannel);

      const banner = document.getElementById("tplStatusBanner");
      if (banner) {
        banner.className = "p-3 rounded-xl text-xs font-semibold text-center bg-blue-950/60 border border-blue-500/50 text-blue-300 block";
        banner.innerText = "✓ Templates reset to factory defaults!";
        setTimeout(() => {
          banner.className = "hidden p-3 rounded-xl text-xs font-semibold text-center";
        }, 2200);
      }
    }
  } catch (err) {
    alert("Error resetting templates: " + err.message);
  }
}

function formatEmailHtml(bodyText, vars, category = "") {
  let text = bodyText || "";
  text = text
    .replace(/{FirstName}/g, vars?.firstName || "Homeowner")
    .replace(/{LastName}/g, vars?.lastName || "")
    .replace(/{Address}/g, vars?.address || "your property")
    .replace(/{City}/g, vars?.city || "Orlando")
    .replace(/{State}/g, vars?.state || "FL")
    .replace(/{County}/g, vars?.county || "Orange")
    .replace(/{Phone}/g, "(407) 555-FLIP");

  const lines = text.split("\n");
  let bodyHtml = "";
  let inList = false;

  for (let line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (inList) {
        bodyHtml += "</ul></div>";
        inList = false;
      }
      bodyHtml += "<div style='height: 12px;'></div>";
      continue;
    }

    if (trimmed.startsWith("•") || trimmed.startsWith("-") || trimmed.startsWith("*")) {
      if (!inList) {
        bodyHtml += `<div style="background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 14px 18px; margin: 14px 0;"><ul style="margin: 0; padding-left: 18px; font-size: 13px; color: #0c4a6e; line-height: 1.8;">`;
        inList = true;
      }
      const itemText = trimmed.replace(/^[•\-\*]\s*/, "");
      bodyHtml += `<li>${itemText}</li>`;
    } else {
      if (inList) {
        bodyHtml += "</ul></div>";
        inList = false;
      }
      bodyHtml += `<p style="font-size: 14px; line-height: 1.6; color: #334155; margin: 0 0 10px 0;">${trimmed}</p>`;
    }
  }

  if (inList) {
    bodyHtml += "</ul></div>";
  }

  return `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; color: #1e293b;">
  <div style="background: linear-gradient(135deg, #0f172a, #1e293b); padding: 22px 24px; text-align: left; border-bottom: 3px solid #0284c7;">
    <div style="font-size: 20px; font-weight: 800; color: #38bdf8; letter-spacing: -0.5px;">407 FLIPS</div>
    <div style="font-size: 11px; color: #94a3b8; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-top: 2px;">Direct Central Florida Property Solutions</div>
  </div>
  <div style="padding: 26px 24px;">
    ${bodyHtml}
  </div>
  <div style="background: #f8fafc; padding: 16px 24px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8; text-align: center; line-height: 1.5;">
    407 Flips &bull; Orlando, FL (Central Florida)<br>
    If you received this email in error or do not wish to receive property inquiries, reply with "REMOVE".
  </div>
</div>`;
}

// -------------------------------------------------------------
// Wholesale Contract 1 & PandaDoc E-Sign Controller
// -------------------------------------------------------------

function getOrdinalDay(day) {
  if (day > 3 && day < 21) return day + "th";
  switch (day % 10) {
    case 1:  return day + "st";
    case 2:  return day + "nd";
    case 3:  return day + "rd";
    default: return day + "th";
  }
}

function calculateClosingDate30Days() {
  const d = new Date();
  d.setDate(d.getDate() + 30);
  // Auto-roll weekend: Saturday (6) -> Monday (+2 days), Sunday (0) -> Monday (+1 day)
  if (d.getDay() === 6) {
    d.setDate(d.getDate() + 2);
  } else if (d.getDay() === 0) {
    d.setDate(d.getDate() + 1);
  }
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

async function loadPandadocSettings() {
  try {
    const res = await fetch("/api/pandadoc/settings");
    if (res.ok) {
      pandadocSettingsCache = await res.json();
      updatePandadocModeUI();
    }
  } catch (err) {
    console.error("Error loading PandaDoc settings:", err);
  }
}

function updatePandadocModeUI() {
  const mode = (pandadocSettingsCache?.mode || "sandbox").toLowerCase();
  const badge = document.getElementById("contractModeBadge");
  if (badge) {
    if (mode === "production") {
      badge.className = "px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 cursor-pointer";
      badge.innerHTML = "🚀 Production Mode (Live)";
    } else {
      badge.className = "px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 cursor-pointer";
      badge.innerHTML = "🧪 Sandbox Mode (Free Testing)";
    }
  }
}

async function togglePandadocMode() {
  if (!pandadocSettingsCache) pandadocSettingsCache = {};
  const currentMode = (pandadocSettingsCache.mode || "sandbox").toLowerCase();
  const newMode = currentMode === "sandbox" ? "production" : "sandbox";
  
  const confirmMsg = newMode === "production"
    ? "Switch to LIVE PRODUCTION MODE? Documents sent in this mode will count towards your 60 free production agreements."
    : "Switch back to SANDBOX MODE for unlimited free testing?";
  
  if (!confirm(confirmMsg)) return;

  pandadocSettingsCache.mode = newMode;
  try {
    const res = await fetch("/api/pandadoc/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pandadocSettingsCache)
    });
    if (res.ok) {
      updatePandadocModeUI();
      const banner = document.getElementById("contractStatusBanner");
      if (banner) {
        banner.className = `px-3.5 py-1.5 rounded-xl text-xs font-semibold ${newMode === 'production' ? 'bg-emerald-950/60 border border-emerald-500/50 text-emerald-300' : 'bg-amber-950/60 border border-amber-500/50 text-amber-300'} block`;
        banner.innerHTML = `Switched to <b>${newMode.toUpperCase()} MODE</b>.`;
        setTimeout(() => { banner.className = "hidden"; }, 3000);
      }
    }
  } catch (err) {
    console.error("Error toggling PandaDoc mode:", err);
  }
}

function openPandadocSettingsModal() {
  const modal = document.getElementById("pandadocSettingsModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.style.display = "flex";

  const s = pandadocSettingsCache || {};
  const mode = s.mode || "sandbox";
  const rSand = document.getElementById("pdModeSandbox");
  const rProd = document.getElementById("pdModeProduction");
  if (mode === "production" && rProd) rProd.checked = true;
  else if (rSand) rSand.checked = true;

  const sandKeyEl = document.getElementById("pdSandboxKey");
  if (sandKeyEl) sandKeyEl.value = s.sandbox_key || "";

  const prodKeyEl = document.getElementById("pdProductionKey");
  if (prodKeyEl) prodKeyEl.value = s.production_key || "";

  const buyerEl = document.getElementById("pdBuyerName");
  if (buyerEl) buyerEl.value = s.buyer_name || "Peak Investments LLC";

  const buyerSignerEl = document.getElementById("pdBuyerSignerName");
  if (buyerSignerEl) buyerSignerEl.value = s.buyer_signer_name || "Johnathan Roberts";

  const banner = document.getElementById("pdSettingsStatusBanner");
  if (banner) banner.className = "hidden";
}

function closePandadocSettingsModal() {
  const modal = document.getElementById("pandadocSettingsModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

async function handleSavePandadocSettings(e) {
  e.preventDefault();
  const mode = document.querySelector('input[name="pdMode"]:checked')?.value || "sandbox";
  const sandboxKey = document.getElementById("pdSandboxKey").value.trim();
  const prodKey = document.getElementById("pdProductionKey").value.trim();
  const buyerName = document.getElementById("pdBuyerName").value.trim() || "Peak Investments LLC";
  const buyerSignerName = document.getElementById("pdBuyerSignerName")?.value.trim() || "Johnathan Roberts";

  const payload = {
    mode: mode,
    sandbox_key: sandboxKey,
    production_key: prodKey,
    buyer_name: buyerName,
    buyer_signer_name: buyerSignerName,
    sender_email: "john@407flips.com",
    default_title_company: "TBD",
    default_inspection_days: 14,
    default_deposit: 100.0
  };

  const banner = document.getElementById("pdSettingsStatusBanner");
  try {
    const res = await fetch("/api/pandadoc/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      pandadocSettingsCache = payload;
      updatePandadocModeUI();
      if (banner) {
        banner.className = "p-3 rounded-xl text-xs font-semibold bg-emerald-950/60 border border-emerald-500/50 text-emerald-300 block";
        banner.innerHTML = "✓ PandaDoc settings saved successfully!";
      }
      setTimeout(closePandadocSettingsModal, 1500);
    } else {
      if (banner) {
        banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
        banner.innerHTML = "⚠️ Failed to save settings.";
      }
    }
  } catch (err) {
    if (banner) {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
      banner.innerHTML = `⚠️ Error: ${err.message}`;
    }
  }
}

async function testPandadocConnection() {
  const mode = document.querySelector('input[name="pdMode"]:checked')?.value || "sandbox";
  const key = mode === "production" 
    ? document.getElementById("pdProductionKey").value.trim() 
    : document.getElementById("pdSandboxKey").value.trim();

  const banner = document.getElementById("pdSettingsStatusBanner");
  if (!key) {
    if (banner) {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-amber-950/60 border border-amber-500/50 text-amber-300 block";
      banner.innerHTML = `Please enter a ${mode.toUpperCase()} API key to test.`;
    }
    return;
  }

  const btn = document.getElementById("btnTestPandadoc");
  if (btn) btn.innerHTML = "<span>⏳</span> <span>Connecting...</span>";

  try {
    const res = await fetch("https://api.pandadoc.com/public/v1/templates", {
      headers: { "Authorization": `API-Key ${key}` }
    });
    if (res.ok) {
      if (banner) {
        banner.className = "p-3 rounded-xl text-xs font-semibold bg-emerald-950/60 border border-emerald-500/50 text-emerald-300 block";
        banner.innerHTML = `✓ Successfully authenticated with PandaDoc ${mode.toUpperCase()} API!`;
      }
    } else {
      if (banner) {
        banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
        banner.innerHTML = `⚠️ Authentication failed (HTTP ${res.status}): Check your key.`;
      }
    }
  } catch (err) {
    if (banner) {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
      banner.innerHTML = `⚠️ Network Error: ${err.message}`;
    }
  } finally {
    if (btn) btn.innerHTML = "<span>⚡</span> <span>Test API Connection</span>";
  }
}

function openContractModal(parcelId, phone, email, ownerName, propertyAddress, propertyCity, propertyZip, marketVal) {
  const modal = document.getElementById("contractModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.style.display = "flex";

  // Hidden Inputs
  document.getElementById("contractParcelId").value = parcelId || "";
  document.getElementById("contractCounty").value = selectedCountyKey || "Pinellas";
  document.getElementById("contractPropertyStreet").value = propertyAddress || "";
  document.getElementById("contractPropertyCity").value = propertyCity || "St Petersburg";
  document.getElementById("contractPropertyState").value = currentState || "FL";
  document.getElementById("contractPropertyZip").value = propertyZip || "";

  // Visual header tags
  document.getElementById("contractDisplayPin").innerText = `PIN: ${parcelId || 'N/A'}`;
  document.getElementById("contractDisplayAddress").innerText = propertyAddress || "Unknown Address";
  document.getElementById("contractDisplayCity").innerText = `${propertyCity || 'Pinellas'}, ${currentState || 'FL'} ${propertyZip || ''}`;

  // Form Fields
  document.getElementById("contractSellerName").value = ownerName || "Property Owner";
  document.getElementById("contractBuyerName").value = pandadocSettingsCache?.buyer_name || "Peak Investments LLC";
  const buyerSignerEl = document.getElementById("contractBuyerSignerName");
  if (buyerSignerEl) buyerSignerEl.value = pandadocSettingsCache?.buyer_signer_name || "Johnathan Roberts";
  
  // Default Purchase Price suggestion (e.g. 65-70% of market value if available, or clean empty/round figure)
  const defaultPrice = (marketVal && marketVal > 10000) ? Math.round((marketVal * 0.65) / 1000) * 1000 : 120000;
  document.getElementById("contractPurchasePrice").value = defaultPrice;
  document.getElementById("contractDeposit").value = pandadocSettingsCache?.default_deposit || 100;
  
  // Auto-calculated 30-day closing date with Saturday/Sunday -> Monday roll
  document.getElementById("contractClosingDate").value = calculateClosingDate30Days();
  document.getElementById("contractInspectionDays").value = pandadocSettingsCache?.default_inspection_days || 14;
  document.getElementById("contractTitleCompany").value = pandadocSettingsCache?.default_title_company || "TBD";
  document.getElementById("contractRecipientEmail").value = email || "";

  // Reset status banner
  const banner = document.getElementById("contractStatusBanner");
  if (banner) banner.className = "hidden";

  updatePandadocModeUI();
  calculateContractFinancials();
}

function closeContractModal() {
  const modal = document.getElementById("contractModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

function calculateContractFinancials() {
  const price = parseFloat(document.getElementById("contractPurchasePrice").value) || 0;
  const deposit = parseFloat(document.getElementById("contractDeposit").value) || 0;
  const cashDue = Math.max(0, price - deposit);

  const cashDisplay = document.getElementById("contractDisplayCashDue");
  if (cashDisplay) {
    cashDisplay.innerText = `$${cashDue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  updateContractPreview();
}

function updateContractPreview() {
  const preview = document.getElementById("contractPaperPreview");
  if (!preview) return;

  const now = new Date();
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const dateFormatted = `${getOrdinalDay(now.getDate())} day of ${months[now.getMonth()]}, 20${String(now.getFullYear()).slice(-2)}`;

  const seller = document.getElementById("contractSellerName").value || "_________________________";
  const buyer = document.getElementById("contractBuyerName").value || "Peak Investments LLC";
  const address = document.getElementById("contractPropertyStreet").value || "_________________________";
  const city = document.getElementById("contractPropertyCity").value || "St Petersburg";
  const state = document.getElementById("contractPropertyState").value || "FL";
  const zip = document.getElementById("contractPropertyZip").value || "";
  const pin = document.getElementById("contractParcelId").value || "_________________________";

  const price = parseFloat(document.getElementById("contractPurchasePrice").value) || 0;
  const deposit = parseFloat(document.getElementById("contractDeposit").value) || 0;
  const cashDue = Math.max(0, price - deposit);

  const closingDate = document.getElementById("contractClosingDate").value || "_________________________";
  const inspectionDays = document.getElementById("contractInspectionDays").value || "14";
  const titleCompany = document.getElementById("contractTitleCompany").value || "TBD";
  const additionalTerms = document.getElementById("contractAdditionalTerms").value || "";

  const buyerSigner = document.getElementById("contractBuyerSignerName")?.value || "Johnathan Roberts";

  preview.innerHTML = `
    <div style="text-align: center; font-weight: 800; font-size: 13.5pt; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; color: #000;">
      PURCHASE AND SALE AGREEMENT
    </div>

    <div style="margin-bottom: 8px; line-height: 1.4;">
      This agreement is made this <span style="font-weight: bold; border-bottom: 1px solid #000; padding: 0 4px; color: #1e3a8a;">${dateFormatted}</span> between <span style="font-weight: bold; border-bottom: 1px solid #000; padding: 0 4px; color: #1e3a8a;">${seller}</span> Seller(s) and <span style="font-weight: bold; border-bottom: 1px solid #000; padding: 0 4px; color: #1e3a8a;">${buyer}</span> Buyer(s).
    </div>

    <div style="margin-bottom: 8px; line-height: 1.4;">
      Seller agrees to sell and buyer agrees to buy the following described real property together with all improvements and fixtures and the personal property described below:
      <div style="margin-top: 3px;">Street Address: <span style="font-weight: bold; border-bottom: 1px solid #000; padding: 0 4px; color: #1e3a8a;">${address}</span></div>
      <div>City, State, Zip: <span style="font-weight: bold; border-bottom: 1px solid #000; padding: 0 4px; color: #1e3a8a;">${city}, ${state} ${zip}</span></div>
      <div>Legal description: <span style="font-weight: bold; border-bottom: 1px solid #000; padding: 0 4px; color: #1e3a8a;">Parcel ID / PIN: ${pin}</span></div>
    </div>

    <div style="margin: 8px 0; padding: 6px 12px; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 10.5px;">
      <div style="font-weight: bold; margin-bottom: 3px;">The purchase price to be paid as follows:</div>
      <div style="display: flex; justify-content: space-between; padding: 2px 0;">
        <span>Total Deposit</span>
        <span><b>$${deposit.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b></span>
      </div>
      <div style="display: flex; justify-content: space-between; padding: 2px 0;">
        <span>Cash due to Seller at Closing</span>
        <span><b>$${cashDue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b></span>
      </div>
      <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #e2e8f0; margin-top: 2px; font-weight: bold;">
        <span>Total Price</span>
        <span><b>$${price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b></span>
      </div>
    </div>

    <div style="margin-bottom: 5px; text-align: justify; font-size: 9.5px; line-height: 1.25;">
      <b>1. EARNEST MONEY</b> to be deposited with a licensed title company or attorney within 48 hours of acceptance and ratification of offer.
    </div>

    <div style="margin-bottom: 5px; text-align: justify; font-size: 9.5px; line-height: 1.25;">
      <b>2. PRORATIONS, IMPOUNDS & SECURITY DEPOSITS:</b> Loan interest, property taxes, insurance, and rents shall be prorated as of the date of closing. All security deposits shall be transferred to buyer at closing. All impound accounts for taxes and insurance are included in the purchase price and shall be transferred to buyer at closing. Any shortage in these accounts shall be charged to seller at closing.
    </div>

    <div style="margin-bottom: 5px; text-align: justify; font-size: 9.5px; line-height: 1.25;">
      <b>3. CLOSING DATE AND TRANSFER OF TITLE:</b> This transaction shall close on or before <span style="font-weight: bold; border-bottom: 1px solid #000; padding: 0 4px; color: #1e3a8a;">${closingDate}</span>. Closing will be held at <span style="font-weight: bold; border-bottom: 1px solid #000; padding: 0 4px; color: #1e3a8a;">${titleCompany}</span> and Seller(s) agree to transfer marketable title free and clear of all encumbrances except those listed and pay any required state taxes or stamps required to record deed and mortgage. Seller agrees to furnish title insurance in the amount of the purchase price, showing no encumbrances or exceptions other than previously noted.
    </div>

    <div style="margin-bottom: 5px; text-align: justify; font-size: 9.5px; line-height: 1.25;">
      <b>4. DAMAGE TO PROPERTY:</b> Seller shall maintain property in its current condition and keep it insured against all loss until closing. In the event of destruction covered by insurance, buyer may elect to close and collect the insurance proceeds.
    </div>

    <div style="margin-bottom: 5px; text-align: justify; font-size: 9.5px; line-height: 1.25;">
      <b>5. DEFAULTS:</b> If buyer defaults under this contract, any and all monies deposited by buyer(s) shall be retained by seller as full liquidated damages. If seller defaults, buyer may pursue all remedies allowed by law and seller agrees to be responsible for all costs incurred by buyer as a result of sellers default.
    </div>

    <div style="margin-bottom: 5px; text-align: justify; font-size: 9.5px; line-height: 1.25;">
      <b>6. SUCCESSORS AND ASSIGNEES:</b> The terms and conditions of this contract shall bind all successors, heirs, administrators, trustees, executors and assignees of the respective parties.
    </div>

    <div style="margin-bottom: 5px; text-align: justify; font-size: 9.5px; line-height: 1.25;">
      <b>7. ACCESS:</b> Sellers agree that buyers may advertise property and have access during reasonable hours to show property to others.
    </div>

    <div style="margin-bottom: 5px; text-align: justify; font-size: 9.5px; line-height: 1.25;">
      <b>8. ASSIGNABLE:</b> This contract is assignable by the buyer.
    </div>

    <div style="margin-bottom: 5px; text-align: justify; font-size: 9.5px; line-height: 1.25;">
      <b>9. INSPECTION:</b> (a) Buyer shall have <span style="font-weight: bold; border-bottom: 1px solid #000; padding: 0 4px; color: #1e3a8a;">${inspectionDays}</span> days from Effective Date ("Inspection Period") within which to have such inspections of the Property performed as Buyer shall desire and utilities service shall be made available by the Seller during the Inspection Period; (b) Buyer shall be responsible for prompt payment for such inspections and repair of damage to and restoration of the Property resulting from such inspections; and (c) If Buyer determines, in Buyer's sole discretion, that the condition of the Property is not acceptable to Buyer, Buyer may cancel this Contract by delivering written notice of such election to Seller prior to the expiration of the Inspection Period. If Buyer timely cancels this Contract, the deposit(s) paid shall be immediately returned to Buyer; thereupon, Buyer and Seller shall be released of all further obligations under this Contract.
    </div>

    <div style="font-weight: bold; font-size: 9.5px; margin-top: 6px; margin-bottom: 2px;">10. ADDITIONAL TERMS AND CONDITIONS:</div>
    <div style="border: 1px solid #94a3b8; border-radius: 4px; padding: 5px 8px; min-height: 38px; font-size: 9.5px; background: #f8fafc; line-height: 1.35; margin-bottom: 8px;">
      ${additionalTerms}
    </div>

    <div style="border-top: 1px solid #475569; padding-top: 6px; margin-top: 8px; font-size: 9px;">
      <div style="font-style: italic; font-weight: 600; text-align: center; margin-bottom: 10px;">The undersigned have read the above information, understand it and verify that it is correct.</div>
      <div style="display: flex; justify-content: space-between; gap: 30px;">
        <div style="width: 48%;">
          <div style="margin-bottom: 6px; font-weight: bold;">DATE: <span style="font-weight: normal; text-decoration: underline; color: #1e3a8a;">${dateFormatted}</span></div>
          <div style="height: 36px; display: flex; align-items: flex-end; padding-bottom: 2px;">
            <span style="font-size: 8.5px; color: #7c3aed; font-weight: 600; background: #ede9fe; padding: 2px 8px; border-radius: 4px; border: 1px dashed #7c3aed;">🖋️ PandaDoc E-Sign (Seller Signs 1st)</span>
          </div>
          <div style="border-top: 1px solid #000; margin-top: 2px; padding-top: 2px; display: flex; justify-content: space-between;">
            <span>SELLER: ${seller}</span>
            <span style="color:#64748b; font-size:8px;">Primary</span>
          </div>
          <div style="border-top: 1px solid #000; margin-top: 14px; padding-top: 2px; display: flex; justify-content: space-between;">
            <span>SELLER: _________________________</span>
            <span style="color:#64748b; font-size:8px;">Co-Principal</span>
          </div>
        </div>
        <div style="width: 48%;">
          <div style="margin-bottom: 6px; font-weight: bold;">DATE: <span style="font-weight: normal; text-decoration: underline; color: #1e3a8a;">${dateFormatted}</span></div>
          <div style="height: 36px; display: flex; align-items: flex-end; padding-bottom: 2px;">
            <span style="font-size: 8.5px; color: #0284c7; font-weight: 600; background: #e0f2fe; padding: 2px 8px; border-radius: 4px; border: 1px dashed #0284c7;">🖋️ PandaDoc E-Sign (You Countersign 2nd)</span>
          </div>
          <div style="border-top: 1px solid #000; margin-top: 2px; padding-top: 2px; display: flex; justify-content: space-between;">
            <span>BUYER: ${buyer}</span>
            <span style="color:#475569; font-size:8px;">By: ${buyerSigner}</span>
          </div>
          <div style="border-top: 1px solid #000; margin-top: 14px; padding-top: 2px; display: flex; justify-content: space-between;">
            <span>BUYER: __________________________</span>
            <span style="color:#64748b; font-size:8px;">Co-Principal</span>
          </div>
        </div>
      </div>
    </div>
  `;
}

function getContractPayloadFromForm() {
  const price = parseFloat(document.getElementById("contractPurchasePrice").value) || 0;
  const deposit = parseFloat(document.getElementById("contractDeposit").value) || 0;
  const cashDue = Math.max(0, price - deposit);

  return {
    parcel_id: document.getElementById("contractParcelId").value,
    county: document.getElementById("contractCounty").value || "Pinellas",
    agreement_date: "",
    seller_name: document.getElementById("contractSellerName").value.trim(),
    buyer_name: document.getElementById("contractBuyerName").value.trim() || "Peak Investments LLC",
    buyer_signer_name: document.getElementById("contractBuyerSignerName")?.value.trim() || "Johnathan Roberts",
    property_address: document.getElementById("contractPropertyStreet").value.trim(),
    property_city: document.getElementById("contractPropertyCity").value.trim() || "St Petersburg",
    property_state: document.getElementById("contractPropertyState").value.trim() || "FL",
    property_zip: document.getElementById("contractPropertyZip").value.trim(),
    legal_description: document.getElementById("contractParcelId").value,
    purchase_price: price,
    deposit_amount: deposit,
    cash_due_closing: cashDue,
    closing_date: document.getElementById("contractClosingDate").value.trim(),
    closing_location: document.getElementById("contractTitleCompany").value.trim() || "TBD",
    inspection_days: parseInt(document.getElementById("contractInspectionDays").value) || 14,
    additional_terms: document.getElementById("contractAdditionalTerms").value.trim(),
    recipient_email: document.getElementById("contractRecipientEmail").value.trim(),
    recipient_name: document.getElementById("contractSellerName").value.trim(),
    notes: ""
  };
}

async function downloadContractPdf() {
  const payload = getContractPayloadFromForm();
  if (!payload.purchase_price || payload.purchase_price <= 0) {
    alert("Please enter a valid purchase price.");
    return;
  }

  const btn = document.getElementById("btnDownloadPdf");
  btn.disabled = true;
  btn.innerHTML = "<span>⏳</span> <span>Generating PDF...</span>";

  try {
    const res = await fetch("/api/contract/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Purchase_Agreement_${payload.property_address.replace(/[^a-zA-Z0-9_-]/g, '_')}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } else {
      alert("Failed to generate PDF. Check backend console.");
    }
  } catch (err) {
    alert(`Error generating PDF: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = "<span>📥</span> <span>Download Printable PDF</span>";
  }
}

async function sendContractViaPandaDoc() {
  const payload = getContractPayloadFromForm();
  const banner = document.getElementById("contractStatusBanner");
  const btn = document.getElementById("btnSendPandaDoc");

  if (!payload.purchase_price || payload.purchase_price <= 0) {
    alert("Please enter an agreed purchase price.");
    return;
  }
  if (!payload.recipient_email || !payload.recipient_email.includes("@")) {
    alert("Please enter a valid recipient email address for e-signature.");
    return;
  }

  const mode = (pandadocSettingsCache?.mode || "sandbox").toUpperCase();
  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> <span>Uploading to PandaDoc (${mode})...</span>`;
  banner.className = "hidden";

  try {
    const res = await fetch("/api/contract/pandadoc/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (data.status === "success") {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-emerald-950/60 border border-emerald-500/50 text-emerald-300 block";
      banner.innerHTML = `
        <div class="flex flex-col gap-1 text-left">
          <div class="flex items-center gap-1.5 font-bold text-emerald-300">
            <span>✓</span> <span>Contract Dispatched via PandaDoc (${mode})!</span>
          </div>
          <div class="text-[11px] text-slate-300">An invitation was sent to <b>${payload.recipient_email}</b>.</div>
          ${data.shared_link ? `<div class="mt-1"><a href="${data.shared_link}" target="_blank" class="underline text-cyan-300 text-[11px] font-mono">Open Signing Link ↗</a></div>` : ''}
        </div>
      `;

      // Update saved contacts cache with email & contract date
      if (payload.parcel_id) {
        if (!savedContactsCache[payload.parcel_id]) savedContactsCache[payload.parcel_id] = {};
        savedContactsCache[payload.parcel_id].email = payload.recipient_email;
        savedContactsCache[payload.parcel_id].last_contract_sent = "Just now";
        savedContactsCache[payload.parcel_id].last_contract_status = "SENT";
        updateSavedPipelineCount();
        updateFilterCounts();
        if (liveRecords && liveRecords.length > 0) filterLiveRecords(currentFilter);
      }

      fetchOutreachHistory();
    } else {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
      banner.innerHTML = `⚠️ <b>Send Failed:</b> ${data.message}`;
    }
  } catch (err) {
    banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/50 text-rose-300 block";
    banner.innerHTML = `⚠️ <b>Connection Error:</b> ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = "<span>🖋️</span> <span>Send for E-Sign (PandaDoc)</span>";
  }
}

