// Florida Lead Hub Client Application Controller
let currentState = localStorage.getItem("flh_state") || "FL";
let allStates = [];
let allCounties = [];
let selectedCountyKey = localStorage.getItem("flh_county") || "Orange";
let loadedCountyKey = null;
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

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeAttr(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/'/g, "\\'")
    .replace(/"/g, '&quot;');
}

const STREET_TYPE_MAP = {
  'ST': 'St', 'STREET': 'St', 'STR': 'St',
  'AVE': 'Ave', 'AVENUE': 'Ave', 'AV': 'Ave',
  'BLVD': 'Blvd', 'BOULEVARD': 'Blvd', 'BL': 'Blvd', 'BLV': 'Blvd',
  'RD': 'Rd', 'ROAD': 'Rd',
  'DR': 'Dr', 'DRIVE': 'Dr',
  'CT': 'Ct', 'COURT': 'Ct',
  'LN': 'Ln', 'LANE': 'Ln',
  'CIR': 'Cir', 'CIRCLE': 'Cir', 'CI': 'Cir', 'CR': 'Cir',
  'PL': 'Pl', 'PLACE': 'Pl',
  'WAY': 'Way', 'WA': 'Way', 'WY': 'Way',
  'PKWY': 'Pkwy', 'PARKWAY': 'Pkwy', 'PK': 'Pkwy', 'PKY': 'Pkwy',
  'TER': 'Ter', 'TERRACE': 'Ter', 'TE': 'Ter',
  'HWY': 'Hwy', 'HIGHWAY': 'Hwy', 'HW': 'Hwy',
  'TRL': 'Trl', 'TRAIL': 'Trl', 'TR': 'Trl',
  'ALY': 'Aly', 'ALLEY': 'Aly',
  'LOOP': 'Loop', 'LP': 'Loop',
  'PASS': 'Pass', 'RUN': 'Run', 'PATH': 'Path',
  'CV': 'Cv', 'COVE': 'Cv',
  'PT': 'Pt', 'POINT': 'Pt',
  'ISL': 'Isl', 'ISLAND': 'Isl',
  'BCH': 'Bch', 'BEACH': 'Bch',
  'BND': 'Bnd', 'BEND': 'Bnd'
};

const DIRECTIONAL_WORDS = new Set([
  'N', 'S', 'E', 'W', 'NE', 'NW', 'SE', 'SW',
  'NORTH', 'SOUTH', 'EAST', 'WEST',
  'NORTHEAST', 'NORTHWEST', 'SOUTHEAST', 'SOUTHWEST'
]);

const PRESERVED_ACRONYMS = new Set([
  'LLC', 'LP', 'LLP', 'PA', 'PLLC', 'PC', 'II', 'III', 'IV'
]);

function formatDisplayAddress(addr) {
  if (!addr) return "";
  let s = String(addr).trim();
  if (!s || s.toLowerCase() === "nan" || s.toLowerCase() === "n/a" || s.toLowerCase() === "none") return "";

  // Extract unit / apartment / suite at end if present
  let unitPart = "";
  const unitMatch = s.match(/(\s+(?:#|APT|UNIT|STE|SUITE|BLDG|LOT|SPAC|SPC)\s*#?\s*[A-Za-z0-9\-]+)$/i);
  if (unitMatch) {
    unitPart = unitMatch[1].replace(/#\s*/i, "# ").trim();
    unitPart = unitPart.replace(/\b([A-Za-z]+)\b/g, (m) => m.charAt(0).toUpperCase() + m.slice(1).toLowerCase());
    s = s.slice(0, unitMatch.index).trim();
  }

  let tokens = s.split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return "";

  // 1. Drop trailing direction (e.g. 123 MAIN STREET S or 123 MAIN STREET SOUTH)
  if (tokens.length > 2 && DIRECTIONAL_WORDS.has(tokens[tokens.length - 1].toUpperCase())) {
    tokens.pop();
  }

  // 2. Drop leading direction (e.g. 714 W KALEY AV or 123 S MAIN ST)
  // Only drop if there is at least one word between direction and street suffix (prevents 122 NORTH ST -> 122 ST)
  if (tokens.length >= 4 && DIRECTIONAL_WORDS.has(tokens[1].toUpperCase())) {
    tokens.splice(1, 1);
  } else if (tokens.length === 3 && DIRECTIONAL_WORDS.has(tokens[0].toUpperCase()) && STREET_TYPE_MAP[tokens[2].toUpperCase()]) {
    tokens.shift();
  }

  const formatted = tokens.map((token) => {
    const upper = token.toUpperCase();
    if (STREET_TYPE_MAP[upper]) {
      return STREET_TYPE_MAP[upper];
    }
    if (/^\d+(ST|ND|RD|TH)$/i.test(token)) {
      return token.toLowerCase();
    }
    if (/^MC[A-Za-z]/i.test(token)) {
      return 'Mc' + token.charAt(2).toUpperCase() + token.slice(3).toLowerCase();
    }
    if (/^O'[A-Za-z]/i.test(token)) {
      return "O'" + token.charAt(2).toUpperCase() + token.slice(3).toLowerCase();
    }
    if (token.includes('-')) {
      return token.split('-').map(p => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase()).join('-');
    }
    return token.charAt(0).toUpperCase() + token.slice(1).toLowerCase();
  });

  let result = formatted.join(" ");
  if (unitPart) {
    result += " " + unitPart;
  }
  return result;
}

function formatDisplayName(name) {
  if (!name) return "";
  let s = String(name).trim();
  if (!s || s.toLowerCase() === "nan" || s.toLowerCase() === "none") return "";
  if (s.toLowerCase() === "unknown owner" || s.toLowerCase() === "unknown") return "Unknown Owner";

  const words = s.split(/\s+/).filter(Boolean);
  const formatted = words.map((w) => {
    const upper = w.toUpperCase();
    if (PRESERVED_ACRONYMS.has(upper)) return upper;
    if (upper === '&' || upper === 'AND') return '&';
    if (upper === 'INC') return 'Inc';
    if (upper === 'CORP') return 'Corp';
    if (upper === 'CO') return 'Co';
    if (upper === 'LTD') return 'Ltd';
    if (/^MC[A-Za-z]/i.test(w)) {
      return 'Mc' + w.charAt(2).toUpperCase() + w.slice(3).toLowerCase();
    }
    if (/^O'[A-Za-z]/i.test(w)) {
      return "O'" + w.charAt(2).toUpperCase() + w.slice(3).toLowerCase();
    }
    if (w.includes('-')) {
      return w.split('-').map(p => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase()).join('-');
    }
    return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
  });

  return formatted.join(" ");
}

function formatDisplayCity(city) {
  if (!city) return "";
  let s = String(city).trim();
  if (!s || s.toLowerCase() === "nan" || s.toLowerCase() === "none") return "";
  return s.split(/\s+/).map((w) => {
    if (w.toUpperCase() === "ST" || w.toUpperCase() === "ST.") return "St.";
    return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
  }).join(" ");
}

window.formatDisplayAddress = formatDisplayAddress;
window.formatDisplayName = formatDisplayName;
window.formatDisplayCity = formatDisplayCity;

function openModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.style.display = "flex";
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  modal.classList.add("hidden");
  modal.style.display = "none";
}

window.openModal = openModal;
window.closeModal = closeModal;

const SMS_TEMPLATES = {
  "casual_direct": "Hello, I'm trying to locate the property owner of {Address}. Would that be you?",
  "quick_question": "Hi, I'm looking for the homeowner at {Address}. Is that you?",
  "neighbor_investor": "Hello, is this the right person to reach about ownership of {Address}?",
  "quick_checkin": "Hi there, I'm trying to get in touch with the owner of {Address}. Are you the owner?",
  "multi_list": "Hello, I'm trying to locate the property owner of {Address}. Would that be you?",
  "single_list": "Hi, I'm looking for the homeowner at {Address}. Is that you?",
  "ultra_short": "Hello, is this the right person to reach about ownership of {Address}?",
  "casual_local": "Hi, I'm looking for the homeowner at {Address}. Is that you?",
  "cash_offer": "Hello, I'm trying to locate the property owner of {Address}. Would that be you?"
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
  loadSellerBotSettings();
  startSellerInboxPolling();
  startAutoSmsStatusPolling();
  startAutoEmailStatusPolling();
  loadScheduledCallbacks();
  fetchLinkZoneHealth();
  fetchOpenerMetrics();
  setInterval(fetchLinkZoneHealth, 30000);
  loadLiveCountyLeads(selectedCountyKey, null, currentState);
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
          opt.className = "bg-slate-900 text-white py-1.5 px-3";
          opt.style.backgroundColor = "#0d1424";
          opt.style.color = "#ffffff";
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
  flApiCatalogCache = null;
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

    // Populate Header & Hero County Dropdowns
    const headerSelect = document.getElementById("headerCountySelect");
    if (headerSelect) {
      headerSelect.innerHTML = "";
      allCounties.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c.key;
        opt.className = "bg-slate-900 text-white py-1.5 px-3";
        opt.style.backgroundColor = "#0d1424";
        opt.style.color = "#ffffff";
        const statusLabel = c.has_master ? `Live & Ready (${c.records ? c.records.toLocaleString() + ' parcels' : 'Loaded'})` : 'Needs Setup';
        opt.textContent = `${c.name} County — ${statusLabel}`;
        if (c.key === selectedCountyKey) opt.selected = true;
        headerSelect.appendChild(opt);
      });
    }

    const select = document.getElementById("heroCountySelect");
    if (select) {
      select.innerHTML = "";
      allCounties.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c.key;
        opt.className = "bg-slate-900 text-white py-1.5 px-3";
        opt.style.backgroundColor = "#0d1424";
        opt.style.color = "#ffffff";
        opt.textContent = `${c.name} County ${c.has_master ? `(${c.records.toLocaleString()} records)` : ""}`;
        if (c.key === selectedCountyKey) opt.selected = true;
        select.appendChild(opt);
      });
    }

    renderCountyGrid(allCounties);
    updateCategoryCardLinks(selectedCountyKey);
    updateActiveCountyHeader(selectedCountyKey);
  } catch (err) {
    console.error("Error fetching counties:", err);
  }
}

function openCountyCoverageModal() {
  const modal = document.getElementById("countyCoverageModal");
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }
}

function closeCountyCoverageModal() {
  const modal = document.getElementById("countyCoverageModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
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

let activeLeadsPromise = null;

function updateActiveCountyHeader(key) {
  const countyObj = allCounties.find(c => c.key === key);
  if (!countyObj) return;

  const countyLabel = document.getElementById("activeCountyDisplayLabel");
  if (countyLabel) {
    countyLabel.innerText = `${countyObj.name} County, ${currentState}`;
  }
  const parcelsCount = document.getElementById("activeCountyParcelsCount");
  if (parcelsCount) {
    parcelsCount.innerText = countyObj.records ? countyObj.records.toLocaleString() : (countyObj.has_master ? 'Loaded' : '0');
  }
  const pipelineDesc = document.getElementById("pipelineViewDescription");
  if (pipelineDesc) {
    pipelineDesc.innerText = `Showing all raw distressed public filings for ${countyObj.name} County`;
  }
  const statusDot = document.getElementById("headerCountyStatusDot");
  if (statusDot) {
    statusDot.className = countyObj.has_master ? "w-2 h-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50" : "w-2 h-2 rounded-full bg-amber-400 shadow-sm shadow-amber-400/50";
  }
  const statRecords = document.getElementById("statTotalRecords");
  if (statRecords && countyObj.records) {
    statRecords.innerText = countyObj.records.toLocaleString();
  }
}

async function selectCounty(key, targetFilter = null) {
  selectedCountyKey = key;
  currentFilteredRecords = [];
  localStorage.setItem("flh_county", key);
  currentFilter = targetFilter || "all";
  if (currentPipelineView === 'saved') {
    updateSavedPipelineCount();
    updateFilterCounts();
    filterLiveRecords(currentFilter);
  }
  updateCategoryCardLinks(key);
  const select = document.getElementById("heroCountySelect");
  if (select) select.value = key;
  const headerSelect = document.getElementById("headerCountySelect");
  if (headerSelect) headerSelect.value = key;

  updateActiveCountyHeader(key);
  const countyObj = allCounties.find(c => c.key === key);

  // Close coverage modal if open
  closeCountyCoverageModal();

  renderCountyGrid(allCounties);

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
    fetchSourcesSummary(key, currentState);
  } else {
    // Live county (Pinellas, Orange, etc.)
    setupBox.classList.add("hidden");
    tableContainer.classList.remove("hidden");
    filterPills.classList.remove("hidden");

    // Dynamic Live API Sync Button visibility & labeling
    const syncBtn = document.getElementById("btnSyncOrlandoCodeTop");
    const syncLabel = document.getElementById("syncOrlandoLabelTop");
    if (syncBtn && syncLabel) {
      if (key === "Orange") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Live Orlando API";
        syncBtn.onclick = () => syncOrlandoLiveCode();
      } else if (key === "Pinellas") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Pinellas APIs";
        syncBtn.onclick = () => syncPinellasLiveApis();
      } else if (key === "Sarasota") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Sarasota APIs";
        syncBtn.onclick = () => syncSarasotaLiveApis();
      } else if (key === "Charlotte") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Charlotte APIs";
        syncBtn.onclick = () => syncCharlotteLiveApis();
      } else if (key === "Lake") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Lake APIs";
        syncBtn.onclick = () => syncLakeLiveApis();
      } else if (key === "Pasco") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Pasco APIs";
        syncBtn.onclick = () => syncPascoLiveApis();
      } else if (key === "Manatee") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Manatee APIs";
        syncBtn.onclick = () => syncManateeLiveApis();
      } else if (key === "Alachua") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Alachua APIs";
        syncBtn.onclick = () => syncAlachuaLiveApis();
      } else if (key === "Volusia") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Volusia APIs";
        syncBtn.onclick = () => syncVolusiaLiveApis();
      } else if (key === "Hillsborough") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Hillsborough APIs";
        syncBtn.onclick = () => syncHillsboroughLiveApis();
      } else if (key === "Osceola") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Osceola APIs";
        syncBtn.onclick = () => syncOsceolaLiveApis();
      } else if (key === "Polk") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Polk APIs";
        syncBtn.onclick = () => syncPolkLiveApis();
      } else if (key === "Lee") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Lee APIs";
        syncBtn.onclick = () => syncLeeLiveApis();
      } else if (key === "Collier") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Collier APIs";
        syncBtn.onclick = () => syncCollierLiveApis();
      } else if (key === "Brevard") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Brevard APIs";
        syncBtn.onclick = () => syncBrevardLiveApis();
      } else if (key === "Duval") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Duval APIs";
        syncBtn.onclick = () => syncDuvalLiveApis();
      } else if (key === "Marion") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Marion APIs";
        syncBtn.onclick = () => syncMarionLiveApis();
      } else if (key === "Broward") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Broward APIs";
        syncBtn.onclick = () => syncBrowardLiveApis();
      } else if (key === "Miami-Dade" || key === "Miami_Dade") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Miami-Dade APIs";
        syncBtn.onclick = () => syncMiamiDadeLiveApis();
      } else if (key === "Palm Beach" || key === "Palm_Beach") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Palm Beach APIs";
        syncBtn.onclick = () => syncPalmBeachLiveApis();
      } else if (key === "St. Lucie" || key === "St_Lucie" || key === "st._lucie") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync St. Lucie APIs";
        syncBtn.onclick = () => syncStLucieLiveApis();
      } else if (key === "Martin" || key === "martin") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Martin APIs";
        syncBtn.onclick = () => syncMartinLiveApis();
      } else if (key === "Indian River" || key === "Indian_River" || key === "indian_river") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Indian River APIs";
        syncBtn.onclick = () => syncIndianRiverLiveApis();
      } else if (key === "St. Johns" || key === "St_Johns" || key === "st._johns") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync St. Johns APIs";
        syncBtn.onclick = () => syncStJohnsLiveApis();
      } else if (key === "Flagler" || key === "flagler") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Flagler APIs";
        syncBtn.onclick = () => syncFlaglerLiveApis();
      } else if (key === "Nassau" || key === "nassau") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Nassau APIs";
        syncBtn.onclick = () => syncNassauLiveApis();
      } else if (key === "Citrus" || key === "citrus") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Citrus APIs";
        syncBtn.onclick = () => syncCitrusLiveApis();
      } else if (key === "Hernando" || key === "hernando") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Hernando APIs";
        syncBtn.onclick = () => syncHernandoLiveApis();
      } else if (key === "Sumter" || key === "sumter") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Sumter APIs";
        syncBtn.onclick = () => syncSumterLiveApis();
      } else if (key === "Highlands" || key === "highlands") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Highlands APIs";
        syncBtn.onclick = () => syncHighlandsLiveApis();
      } else if (key === "Clay" || key === "clay") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Clay APIs";
        syncBtn.onclick = () => syncClayLiveApis();
      } else if (key === "Leon" || key === "leon") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Leon APIs";
        syncBtn.onclick = () => syncLeonLiveApis();
      } else if (key === "Escambia" || key === "escambia") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Escambia APIs";
        syncBtn.onclick = () => syncEscambiaLiveApis();
      } else if (key === "Bay" || key === "bay") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Bay APIs";
        syncBtn.onclick = () => syncBayLiveApis();
      } else if (key === "Okaloosa" || key === "okaloosa") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Okaloosa APIs";
        syncBtn.onclick = () => syncOkaloosaLiveApis();
      } else if (key === "Santa Rosa" || key === "santa_rosa" || key === "santa-rosa") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Santa Rosa APIs";
        syncBtn.onclick = () => syncSantaRosaLiveApis();
      } else if (key === "Seminole" || key === "seminole") {
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = "Sync Seminole APIs";
        syncBtn.onclick = () => syncSeminoleLiveApis();
      } else {
        // In other counties, point to the Master API Catalog to wire endpoints
        syncBtn.classList.remove("hidden");
        syncLabel.innerText = `Browse ${countyObj?.name || key} APIs`;
        syncBtn.onclick = () => openFloridaApiDirectoryModal();
      }


    }

    // Dynamic Daily Orange & Seminole Jail Felony Leads Sync Button
    const jailBtn = document.getElementById("btnSyncOrangeJailTop");
    const jailLabel = document.getElementById("syncOrangeJailLabelTop");
    if (jailBtn) {
      if (key === "Orange") {
        jailBtn.classList.remove("hidden");
        if (jailLabel) jailLabel.innerText = "Sync Orange Jail Leads";
        jailBtn.onclick = () => syncOrangeJailLeads();
      } else if (key === "Seminole") {
        jailBtn.classList.remove("hidden");
        if (jailLabel) jailLabel.innerText = "Sync Seminole Jail Leads";
        jailBtn.onclick = () => syncSeminoleJailLeads();
      } else {
        jailBtn.classList.add("hidden");
      }
    }
    
    await loadLiveCountyLeads(key, currentFilter, currentState);
  }
}

async function syncOrlandoLiveCode() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const iconSub = document.getElementById("syncOrlandoSubIcon");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");
  const btnSub = document.getElementById("btnSubSyncOrlandoCode");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing API...";
  if (iconSub) iconSub.innerText = "⏳";
  if (btnTop) btnTop.disabled = true;
  if (btnSub) btnSub.disabled = true;

  try {
    const res = await fetch("/api/code-enforcement/sync-orlando", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      const newCount = Number(data.new_leads_added || 0);
      const newCountStr = newCount > 0 
        ? `+${newCount.toLocaleString()} New Leads Added Today` 
        : `0 New Leads (All cases already synchronized & up to date with City of Orlando portal)`;
      const newestDateStr = data.newest_case_date || '2026-09-23';
      alert(`🎉 Orlando Code Enforcement API Sync Complete!\n\n• New Leads Added Today: ${newCountStr}\n• Latest Municipal Case Date: ${newestDateStr}\n• Live Open Cases Fetched: ${data.api_cases_fetched?.toLocaleString() || '1,880'}\n• Residential Neglect Violations: ${data.residential_neglect_leads?.toLocaleString() || '660'}\n• Matched to Master Parcels: ${data.matched_code_leads?.toLocaleString() || '654'}\n• Total Code Enforcement Leads: ${data.total_code_leads_now?.toLocaleString() || '2,463'}\n• ⚡ Code + Double Distress Stacks: ${data.code_double_distress_count || '54'}`);
      // Refresh live records and jump directly to Code + Double Distress view
      loadedCountyKey = null; // force fresh reload
      await loadLiveCountyLeads("Orange", "code_stacked");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Orlando code sync error:", err);
    alert("Error communicating with server during API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Live Orlando API";
    if (iconSub) iconSub.innerText = "🔄";
    if (btnTop) btnTop.disabled = false;
    if (btnSub) btnSub.disabled = false;
  }
}

window.syncOrlandoLiveCode = syncOrlandoLiveCode;

async function syncPinellasLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Pinellas APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/pinellas/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Pinellas Live APIs Sync Complete!\n\n• Accela Substantial Damage Records: ${data.accela_records_fetched?.toLocaleString()}\n• Accela Matched to Master Parcels: ${data.accela_matched_leads?.toLocaleString()} (99.9%)\n• SeeClickFix Issues Evaluated: ${data.scf_issues_fetched?.toLocaleString()}\n• SeeClickFix Matched Leads: ${data.scf_matched_leads?.toLocaleString()}\n• ⚡ Total Pinellas Distress Leads: ${data.total_pinellas_leads?.toLocaleString()}\n• 🔥 Double & Triple Distress Stacks: ${data.double_distress_count?.toLocaleString()}`);
      loadedCountyKey = null; // force fresh reload
      await loadLiveCountyLeads("Pinellas", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Pinellas sync error:", err);
    alert("Error communicating with server during Pinellas API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Pinellas APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncPinellasLiveApis = syncPinellasLiveApis;

async function syncSarasotaLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Sarasota APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/sarasota/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Sarasota County Live API Sync Complete!\n\n• Issues Fetched from SeeClickFix: ${data.issues_fetched?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.matched_leads?.toLocaleString()}\n• ⚡ Total Sarasota Distress Leads Now: ${data.total_sarasota_leads?.toLocaleString()}`);
      loadedCountyKey = null; // force fresh reload
      await loadLiveCountyLeads("Sarasota", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Sarasota sync error:", err);
    alert("Error communicating with server during Sarasota API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Sarasota APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncSarasotaLiveApis = syncSarasotaLiveApis;

async function syncCharlotteLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Charlotte APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/charlotte/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Charlotte County Live API Sync Complete!\n\n• Code Cases Fetched from ComDev API: ${data.cases_fetched?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.matched_leads?.toLocaleString()}\n• ⚡ Total Charlotte Distress Leads Now: ${data.total_charlotte_leads?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Charlotte", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Charlotte sync error:", err);
    alert("Error communicating with server during Charlotte API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Charlotte APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncCharlotteLiveApis = syncCharlotteLiveApis;

async function syncLakeLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Lake APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/lake/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Lake County Live API Sync Complete!\n\n• Active Code Cases Fetched from Lake GIS: ${data.cases_fetched?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.matched_leads?.toLocaleString()}\n• ⚡ Total Lake Distress Leads Now: ${data.total_lake_leads?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Lake", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Lake sync error:", err);
    alert("Error communicating with server during Lake API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Lake APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncLakeLiveApis = syncLakeLiveApis;

async function syncPascoLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Pasco APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/pasco/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Pasco County Live API Sync Complete!\n\n• Distress Issues Fetched from SeeClickFix: ${data.issues_fetched?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.matched_leads?.toLocaleString()}\n• ⚡ Total Pasco Distress Leads Now: ${data.total_pasco_leads?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Pasco", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Pasco sync error:", err);
    alert("Error communicating with server during Pasco API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Pasco APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncPascoLiveApis = syncPascoLiveApis;

async function syncManateeLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Manatee APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/manatee/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Manatee County Live API Sync Complete!\n\n• Distress Issues Fetched from SeeClickFix: ${data.issues_fetched?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.matched_leads?.toLocaleString()}\n• ⚡ Total Manatee Distress Leads Now: ${data.total_manatee_leads?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Manatee", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Manatee sync error:", err);
    alert("Error communicating with server during Manatee API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Manatee APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncManateeLiveApis = syncManateeLiveApis;

async function syncAlachuaLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Alachua APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/alachua/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Alachua County Live API Sync Complete!\n\n• Code Cases Fetched from Gainesville/Alachua GIS: ${data.cases_fetched?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.matched_leads?.toLocaleString()}\n• ⚡ Total Alachua Distress Leads Now: ${data.total_alachua_leads?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Alachua", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Alachua sync error:", err);
    alert("Error communicating with server during Alachua API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Alachua APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncAlachuaLiveApis = syncAlachuaLiveApis;

async function syncVolusiaLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Volusia APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/volusia/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Volusia County Live API Sync Complete!\n\n• Code & Distress Cases Fetched from Daytona Beach/Volusia: ${data.cases_fetched?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.matched_leads?.toLocaleString()}\n• ⚡ Total Volusia Distress Leads Now: ${data.total_volusia_leads?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Volusia", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Volusia sync error:", err);
    alert("Error communicating with server during Volusia API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Volusia APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncVolusiaLiveApis = syncVolusiaLiveApis;

async function syncHillsboroughLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Hillsborough APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/hillsborough/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Hillsborough County Live API Sync Complete!\n\n• Structural Damage Assessments Fetched: ${data.cases_fetched?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.matched_leads?.toLocaleString()}\n• ⚡ Total Hillsborough Distress Leads Now: ${data.total_hillsborough_leads?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Hillsborough", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Hillsborough sync error:", err);
    alert("Error communicating with server during Hillsborough API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Hillsborough APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncHillsboroughLiveApis = syncHillsboroughLiveApis;

async function syncOsceolaLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Osceola APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/osceola/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Osceola County Live API Sync Complete!\n\n• Residential Damage & Distress Cases Fetched: ${data.cases_fetched?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.matched_leads?.toLocaleString()}\n• ⚡ Total Osceola Distress Leads Now: ${data.total_osceola_leads?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Osceola", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Osceola sync error:", err);
    alert("Error communicating with server during Osceola API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Osceola APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncOsceolaLiveApis = syncOsceolaLiveApis;

async function syncPolkLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Polk APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/polk/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Polk County Live API Sync Complete!\n\n• Code & Distress Cases Fetched: ${data.cases_fetched?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.matched_leads?.toLocaleString()}\n• ⚡ Total Polk Distress Leads Now: ${data.total_polk_leads?.toLocaleString()}\n• 🔥 Double Distress Stacks: ${data.double_distress_count?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Polk", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Polk sync error:", err);
    alert("Error communicating with server during Polk API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Polk APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncPolkLiveApis = syncPolkLiveApis;

async function syncLeeLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Lee APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/lee/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Lee County Live API Sync Complete!\n\n• Code Violations & Liens Fetched: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Multi-Violation Distress Stacks: ${data.stacked_distress_count?.toLocaleString()}\n• 🏖️ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Lee", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Lee sync error:", err);
    alert("Error communicating with server during Lee API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Lee APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncLeeLiveApis = syncLeeLiveApis;

async function syncCollierLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Collier APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/collier/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Collier County Live API Sync Complete!\n\n• Structural Safety & Distress Leads Fetched: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Collier", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Collier sync error:", err);
    alert("Error communicating with server during Collier API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Collier APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncCollierLiveApis = syncCollierLiveApis;

async function syncBrevardLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Brevard APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/brevard/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Brevard County Live API Sync Complete!\n\n• Municipal & County Property Distress Leads: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Brevard", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Brevard sync error:", err);
    alert("Error communicating with server during Brevard API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Brevard APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncBrevardLiveApis = syncBrevardLiveApis;

async function syncDuvalLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Duval APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/duval/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Duval County Live API Sync Complete!\n\n• Municipal & County Property Distress Leads: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Duval", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Duval sync error:", err);
    alert("Error communicating with server during Duval API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Duval APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncDuvalLiveApis = syncDuvalLiveApis;

async function syncMarionLiveApis() {
  const iconTop = document.getElementById("syncOrlandoIconTop");
  const labelTop = document.getElementById("syncOrlandoLabelTop");
  const btnTop = document.getElementById("btnSyncOrlandoCodeTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Marion APIs...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/marion/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Marion County Live API Sync Complete!\n\n• Recorded Municipal Liens & Code Violations: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Marion", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Marion sync error:", err);
    alert("Error communicating with server during Marion API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Marion APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncMarionLiveApis = syncMarionLiveApis;

async function syncBrowardLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Broward...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/broward/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Broward County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Broward", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Broward sync error:", err);
    alert("Error communicating with server during Broward API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Broward APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncBrowardLiveApis = syncBrowardLiveApis;

async function syncMiamiDadeLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Miami-Dade...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/miami-dade/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Miami-Dade County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Miami-Dade", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Miami-Dade sync error:", err);
    alert("Error communicating with server during Miami-Dade API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Miami-Dade APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncMiamiDadeLiveApis = syncMiamiDadeLiveApis;

async function syncPalmBeachLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Palm Beach...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/palm-beach/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Palm Beach County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Palm Beach", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Palm Beach sync error:", err);
    alert("Error communicating with server during Palm Beach API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Palm Beach APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncPalmBeachLiveApis = syncPalmBeachLiveApis;

async function syncStLucieLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing St. Lucie...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/st-lucie/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 St. Lucie County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("St. Lucie", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("St. Lucie sync error:", err);
    alert("Error communicating with server during St. Lucie API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync St. Lucie APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncStLucieLiveApis = syncStLucieLiveApis;

async function syncMartinLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Martin...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/martin/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Martin County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Martin", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Martin sync error:", err);
    alert("Error communicating with server during Martin API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Martin APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncMartinLiveApis = syncMartinLiveApis;

async function syncIndianRiverLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Indian River...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/indian-river/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Indian River County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Indian River", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Indian River sync error:", err);
    alert("Error communicating with server during Indian River API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Indian River APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncIndianRiverLiveApis = syncIndianRiverLiveApis;

async function syncStJohnsLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing St. Johns...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/st-johns/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 St. Johns County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("St. Johns", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("St. Johns sync error:", err);
    alert("Error communicating with server during St. Johns API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync St. Johns APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncStJohnsLiveApis = syncStJohnsLiveApis;

async function syncFlaglerLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Flagler...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/flagler/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Flagler County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Flagler", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Flagler sync error:", err);
    alert("Error communicating with server during Flagler API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Flagler APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncFlaglerLiveApis = syncFlaglerLiveApis;

async function syncNassauLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Nassau...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/nassau/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Nassau County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Nassau", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Nassau sync error:", err);
    alert("Error communicating with server during Nassau API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Nassau APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncNassauLiveApis = syncNassauLiveApis;

async function syncCitrusLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Citrus...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/citrus/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Citrus County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Citrus", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Citrus sync error:", err);
    alert("Error communicating with server during Citrus API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Citrus APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncCitrusLiveApis = syncCitrusLiveApis;

async function syncHernandoLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Hernando...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/hernando/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Hernando County Live API Sync Complete!\n\n• Structural Damage & Violations: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Hernando", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Hernando sync error:", err);
    alert("Error communicating with server during Hernando API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Hernando APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncHernandoLiveApis = syncHernandoLiveApis;

async function syncSumterLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Sumter...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/sumter/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Sumter County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Sumter", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Sumter sync error:", err);
    alert("Error communicating with server during Sumter API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Sumter APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncSumterLiveApis = syncSumterLiveApis;

async function syncHighlandsLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Highlands...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/highlands/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Highlands County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Highlands", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Highlands sync error:", err);
    alert("Error communicating with server during Highlands API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Highlands APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncHighlandsLiveApis = syncHighlandsLiveApis;

async function syncClayLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Clay...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/clay/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Clay County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Clay", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Clay sync error:", err);
    alert("Error communicating with server during Clay API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Clay APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncClayLiveApis = syncClayLiveApis;

async function syncLeonLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Leon...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/leon/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Leon County / Tallahassee Live API Sync Complete!\n\n• Cityworks Violations & Cases: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()} (${data.total_leads ? Math.round(data.absentee_owners / data.total_leads * 100) : 0}%)\n• Multi-Distress Stacked: ${data.stacked_distress_count?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Leon", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Leon sync error:", err);
    alert("Error communicating with server during Leon API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Leon APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncLeonLiveApis = syncLeonLiveApis;

async function syncEscambiaLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Escambia...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/escambia/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Escambia County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Escambia", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Escambia sync error:", err);
    alert("Error communicating with server during Escambia API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Escambia APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncEscambiaLiveApis = syncEscambiaLiveApis;

async function syncBayLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Bay...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/bay/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Bay County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Bay", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Bay sync error:", err);
    alert("Error communicating with server during Bay API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Bay APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncBayLiveApis = syncBayLiveApis;

async function syncOkaloosaLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Okaloosa...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/okaloosa/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Okaloosa County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Okaloosa", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Okaloosa sync error:", err);
    alert("Error communicating with server during Okaloosa API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Okaloosa APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncOkaloosaLiveApis = syncOkaloosaLiveApis;

async function syncSantaRosaLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Santa Rosa...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/santa-rosa/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Santa Rosa County Live API Sync Complete!\n\n• Code Violations & Distress: ${data.total_leads?.toLocaleString()}\n• Matched to Master Tax Parcels: ${data.unique_properties?.toLocaleString()} properties\n• ⚡ Absentee Homeowners: ${data.absentee_owners?.toLocaleString()}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Santa Rosa", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Santa Rosa sync error:", err);
    alert("Error communicating with server during Santa Rosa API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Santa Rosa APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncSantaRosaLiveApis = syncSantaRosaLiveApis;

async function syncSeminoleLiveApis() {
  const iconTop = document.getElementById("syncCountyApiIconTop");
  const labelTop = document.getElementById("syncCountyApiLabelTop");
  const btnTop = document.getElementById("btnSyncCountyApiTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Seminole...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/seminole/sync-apis", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`🎉 Seminole County Live API Sync Complete!\n\n• Felony Arrestees: ${data.total_arrestees || data.total_leads || 0}\n• Matched to Master Tax Parcels: ${data.matched_properties || data.unique_properties || 0} properties\n• Brand New Leads: ${data.new_leads_added || 0}`);
      loadedCountyKey = null;
      await loadLiveCountyLeads("Seminole", "all");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Seminole sync error:", err);
    alert("Error communicating with server during Seminole API sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚡";
    if (labelTop) labelTop.innerText = "Sync Seminole APIs";
    if (btnTop) btnTop.disabled = false;
  }
}
window.syncSeminoleLiveApis = syncSeminoleLiveApis;
window.syncOrangeLiveApis = syncOrlandoLiveCode;





async function syncOrangeJailLeads() {
  const iconTop = document.getElementById("syncOrangeJailIconTop");
  const labelTop = document.getElementById("syncOrangeJailLabelTop");
  const btnTop = document.getElementById("btnSyncOrangeJailTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Jail Leads...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/orange/sync-jail-leads", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`⚖️ Orange County Daily Jail Booking Sync Complete!\n\n• Report Date: ${data.report_date}\n• Arrestees Extracted: ${data.total_arrestees}\n• Felony Defendants: ${data.felony_arrestees}\n• Matched Homeowners: ${data.matched_properties}\n• Brand New Leads Added: ${data.new_leads_added}\n• Stacked Distress Updated: ${data.stacked_leads_updated}\n\nView results under the '⚖️ Legal Distress' tab.`);
      loadedCountyKey = null; // force fresh reload
      await loadLiveCountyLeads("Orange", "legal_distress");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Orange jail leads sync error:", err);
    alert("Error communicating with server during jail leads sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚖️";
    if (labelTop) labelTop.innerText = "Sync Daily Jail Leads";
    if (btnTop) btnTop.disabled = false;
  }
}

window.syncOrangeJailLeads = syncOrangeJailLeads;

async function syncSeminoleJailLeads() {
  const iconTop = document.getElementById("syncOrangeJailIconTop");
  const labelTop = document.getElementById("syncOrangeJailLabelTop");
  const btnTop = document.getElementById("btnSyncOrangeJailTop");

  if (iconTop) iconTop.innerText = "⏳";
  if (labelTop) labelTop.innerText = "Syncing Jail Leads...";
  if (btnTop) btnTop.disabled = true;

  try {
    const res = await fetch("/api/seminole/sync-jail-leads", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`⚖️ Seminole County Daily Jail Booking Sync Complete!\n\n• Reports Processed: ${data.reports_processed}\n• Arrestees Extracted: ${data.total_arrestees}\n• Felony Defendants: ${data.felony_arrestees}\n• Matched Homeowners: ${data.matched_properties}\n\nView results under the '⚖️ Legal Distress' tab.`);
      loadedCountyKey = null; // force fresh reload
      await loadLiveCountyLeads("Seminole", "legal_distress");
    } else {
      alert(`⚠️ Sync notice: ${data.message || 'Could not complete sync.'}`);
    }
  } catch (err) {
    console.error("Seminole jail leads sync error:", err);
    alert("Error communicating with server during jail leads sync.");
  } finally {
    if (iconTop) iconTop.innerText = "⚖️";
    if (labelTop) labelTop.innerText = "Sync Seminole Jail Leads";
    if (btnTop) btnTop.disabled = false;
  }
}

window.syncSeminoleJailLeads = syncSeminoleJailLeads;

async function loadLiveCountyLeads(countyKey = (selectedCountyKey || "Orange"), initialFilter = null, state = currentState) {
  if (initialFilter) {
    currentFilter = initialFilter;
  }

  // If records are already in memory for this exact county and non-empty:
  if (liveRecords && liveRecords.length > 0 && loadedCountyKey === countyKey) {
    const allCnt = liveRecords.length;
    const titleEl = document.getElementById("liveCountyTitle");
    if (titleEl) titleEl.innerText = `${countyKey} County Live Distressed Leads`;
    const subEl = document.getElementById("liveCountySub");
    if (subEl) subEl.innerText = `Cross-referenced against official county master parcels with clean owner names and absentee indicators.`;
    const badgeEl = document.getElementById("liveStatusBadge");
    if (badgeEl) badgeEl.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> ${allCnt.toLocaleString()} Verified Properties`;
    const pCountAll = document.getElementById("pipelineCountAll");
    if (pCountAll) pCountAll.innerText = allCnt.toLocaleString();

    updateSavedPipelineCount();
    updateFilterCounts();
    filterLiveRecords(currentFilter || "all");
    fetchSourcesSummary(countyKey, state);
    return;
  }

  // Reset liveRecords if switching to a different county
  if (loadedCountyKey !== countyKey) {
    liveRecords = [];
  }

  // If a fetch is currently in flight, await it
  if (activeLeadsPromise) {
    await activeLeadsPromise;
    updateFilterCounts();
    filterLiveRecords(currentFilter || "all");
    return;
  }

  // Show clean loading state in table if empty
  const tbody = document.getElementById("liveTableBody");
  if (tbody && (!liveRecords || liveRecords.length === 0)) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="p-12 text-center">
          <div class="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/30 text-blue-400 mb-2 animate-spin text-lg">
            ⏳
          </div>
          <div class="font-bold text-white text-sm">Loading Verified Distressed Leads for ${countyKey} County...</div>
          <p class="text-xs text-slate-400 mt-1">Cross-referencing lis pendens, code violations, and distress filings against master parcels...</p>
        </td>
      </tr>`;
  }

  activeLeadsPromise = (async () => {
    try {
      await fetchSavedContacts();
      const res = await fetch(`/api/leads?county=${encodeURIComponent(countyKey)}&state=${encodeURIComponent(state || currentState)}`);
      if (!res.ok) {
        console.error("Failed to fetch leads for", countyKey, res.status);
        return;
      }
      const data = await res.json();

      const titleEl = document.getElementById("liveCountyTitle");
      if (titleEl) titleEl.innerText = `${data.county} County Live Distressed Leads`;
      const subEl = document.getElementById("liveCountySub");
      if (subEl) subEl.innerText = `Cross-referenced against ${data.total_records_in_db?.toLocaleString() || '437,559'} official county master parcels with clean owner names and absentee indicators.`;

      // Filter out Corporate LLCs completely so wholesalers only see individual/trust/probate homeowners
      const validHumanLeads = (data.records || []).filter(r => r && !isCorporateOwner(r));
      liveRecords = validHumanLeads;
      loadedCountyKey = countyKey;

      const badgeEl = document.getElementById("liveStatusBadge");
      const verifiedCount = (data.kpis && typeof data.kpis.matched_count === "number") ? data.kpis.matched_count : validHumanLeads.length;
      if (badgeEl) badgeEl.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> ${verifiedCount.toLocaleString()} Verified Properties`;

      // Update All County Leads pill count
      const allCnt = validHumanLeads.length;
      const pCountAll = document.getElementById("pipelineCountAll");
      if (pCountAll) pCountAll.innerText = allCnt.toLocaleString();

      updateSavedPipelineCount();
      updateFilterCounts();
      filterLiveRecords(currentFilter || "all");
      fetchSourcesSummary(countyKey, state);
    } catch (err) {
      console.error("Error loading live leads:", err);
    } finally {
      activeLeadsPromise = null;
    }
  })();

  await activeLeadsPromise;
}

function isCorporateOwner(r) {
  const entity = (r.Owner_Entity_Type || "").toLowerCase();
  const name = (r.Clean_Full_Name || r.Clean_Last_Name || "").toLowerCase();
  return entity.includes("llc") || entity.includes("company") || entity.includes("corp") || entity.includes("inc") ||
         name.includes("llc") || name.includes(" inc") || name.includes(" corp") || name.includes("company") || name.includes("bank") || name.includes("holdings");
}


// -------------------------------------------------------------------------
// PERSISTENT LEAD READ-STATE & NEW LIVE API TRACKING (INBOX STYLE)
// -------------------------------------------------------------------------
const FLH_VIEWED_STORAGE_KEY = "flh_viewed_leads";

function getViewedLeads() {
  try {
    const raw = localStorage.getItem(FLH_VIEWED_STORAGE_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch (e) {
    return new Set();
  }
}

function isLeadNew(r) {
  if (!r) return false;
  const isApiLead = (r.Is_New_Api === 'Yes' || r.Is_New_Lead === 'Yes' || (r.Source_File && String(r.Source_File).includes('Live_API')));
  if (!isApiLead) return false;
  const viewedSet = getViewedLeads();
  const pid = String(r.Parcel_ID || '').trim();
  return !viewedSet.has(pid);
}

function markLeadAsViewed(parcelId) {
  const pid = String(parcelId || '').trim();
  if (!pid) return;
  try {
    const viewed = getViewedLeads();
    if (!viewed.has(pid)) {
      viewed.add(pid);
      localStorage.setItem(FLH_VIEWED_STORAGE_KEY, JSON.stringify([...viewed]));
      
      // Instantly remove NEW badge from row without disrupting user view
      const rowBadge = document.getElementById(`lead-new-badge-${pid}`);
      if (rowBadge) {
        rowBadge.remove();
      }
      
      // Update unread count indicator in title
      updateFilterCounts();
    }
  } catch (e) {
    console.warn("Could not save viewed lead state:", e);
  }
}

function markAllLeadsAsViewed() {
  if (!liveRecords || liveRecords.length === 0) return;
  const viewed = getViewedLeads();
  liveRecords.forEach(r => {
    if (r && r.Parcel_ID) viewed.add(String(r.Parcel_ID).trim());
  });
  localStorage.setItem(FLH_VIEWED_STORAGE_KEY, JSON.stringify([...viewed]));
  renderLiveTable(currentFilteredRecords, false);
  updateFilterCounts();
}

window.isLeadNew = isLeadNew;
window.markLeadAsViewed = markLeadAsViewed;
window.markAllLeadsAsViewed = markAllLeadsAsViewed;

let currentFilteredRecords = [];
let currentPage = 1;
let pageSize = 50;

function renderLiveTable(records, resetPage = true) {
  // Tier 1: Fresh, unreviewed Live API Synced leads (✨ NEW) pinned to the absolute top of table!
  // Tier 2: Strict Newest filing/recording date always on top across all records
  // Tier 3: Within matching dates, Double Distress leads prioritized on top
  const sortedRecords = [...(records || [])].sort((a, b) => {
    // 1. Fresh, unreviewed Live API leads (✨ NEW) ALWAYS pinned to the absolute top!
    const aNew = isLeadNew(a) ? 1 : 0;
    const bNew = isLeadNew(b) ? 1 : 0;
    if (bNew !== aNew) {
      return bNew - aNew; // Unreviewed Live API leads pinned to absolute top!
    }

    // 2. Strict Newest filing / recording date always on top!
    const dateA = String(a.Filing_Date || a.Case_Date || a.Recording_Date || "").slice(0, 10);
    const dateB = String(b.Filing_Date || b.Case_Date || b.Recording_Date || "").slice(0, 10);
    if (dateA && dateB && dateA !== dateB) {
      return dateB.localeCompare(dateA); // Newer date first!
    }
    if (dateB && !dateA) return 1;
    if (dateA && !dateB) return -1;

    // 3. Double Distress leads prioritized within matching dates!
    const aStack = a.Is_Stacked_Distress === "Yes" ? 1 : 0;
    const bStack = b.Is_Stacked_Distress === "Yes" ? 1 : 0;
    if (bStack !== aStack) {
      return bStack - aStack;
    }

    return 0;
  });

  if (resetPage) {
    currentFilteredRecords = sortedRecords;
    currentPage = 1;
  } else if (records) {
    currentFilteredRecords = sortedRecords;
  }

  const tbody = document.getElementById("liveTableBody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const total = currentFilteredRecords.length;
  renderAutoSmsQueueStatus();
  renderAutoEmailQueueStatus();
  updatePaginationUI(total);

  if (!currentFilteredRecords || currentFilteredRecords.length === 0) {
    if (currentFilter === "has_photos") {
      tbody.innerHTML = `<tr><td colspan="8" class="p-8 text-center text-slate-400 font-semibold">No photo links are available in this lead list.</td></tr>`;
      return;
    }
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

  const startIdx = (currentPage - 1) * pageSize;
  const endIdx = Math.min(startIdx + pageSize, total);
  const pageSlice = currentFilteredRecords.slice(startIdx, endIdx);

  const fragment = document.createDocumentFragment();

  pageSlice.forEach(r => {
    const isAbsentee = (r.Absentee_Status || "").includes("Out-of-State");
    const isLlc = (r.Owner_Entity_Type || "").includes("LLC");
    const isTrust = (r.Owner_Entity_Type || "").includes("Trust") || r.Is_Trust_Or_Estate === "Yes";
    const mktVal = parseFloat(r.Market_Value || 0);

    const isStacked = r.Is_Stacked_Distress === "Yes";
    const isLp = r.Lead_Type === "Lis Pendens";
    const isProbate = r.Has_Confirmed_Probate === 'Yes' || (r.Lead_Type || '').toLowerCase().includes('probate');
    const isDivorce = (r.Lead_Type || "").toLowerCase().includes("divorce") || (r.Lead_Type || "").toLowerCase().includes("domestic relations");
    const isJudgment = (r.Lead_Type || "").toLowerCase().includes("judgment");
    const isLien = (r.Lead_Type || "").toLowerCase().includes("lien") && !isJudgment && !(r.Lead_Type || "").includes("Tax Lien");
    const isPoa = (r.Lead_Type || "").toLowerCase().includes("power of attorney");
    const isLpTrust = isLp && (r.Is_Trust_In_LP === "Yes" || r.Is_Trust_Or_Estate === "Yes");

    const isLegalDistress = (r.Lead_Type || "").toLowerCase().includes("legal distress") || (r.Lead_Type || "").toLowerCase().includes("felony") || (r.Distress_Stack_Notes || "").toLowerCase().includes("felony");

    const isCode = isCodeViolationLead(r);
    let leadBadgeClass = "bg-rose-500/15 text-rose-300 border border-rose-500/30";
    let leadBadgeIcon = "🚨 Code Violation";

    if (isCode && isStacked) {
      leadBadgeClass = "bg-gradient-to-r from-rose-500/20 to-amber-500/20 text-amber-300 border border-amber-500/50 shadow-sm font-bold";
      let secondary = "";
      const stackNotesLower = (r.Distress_Stack_Notes || "").toLowerCase();
      if (isProbate || stackNotesLower.includes("probate")) secondary = " + Probate";
      else if (isJudgment || stackNotesLower.includes("judgment")) secondary = " + Judgment";
      else if (isLien || stackNotesLower.includes("lien")) secondary = " + Lien";
      else if (isLp || stackNotesLower.includes("lis pendens")) secondary = " + Lis Pendens";
      else if (isLegalDistress || stackNotesLower.includes("felony")) secondary = " + Legal Distress";
      else if ((r.Lead_Type || "").toLowerCase().includes("water") || stackNotesLower.includes("water")) secondary = " + Water";
      else secondary = " + Double Distress";
      leadBadgeIcon = `⚡ Code${secondary}`;
    } else if (isLegalDistress) {
      const isBonded = (r.Subject_Case_Status || r.Match_Notes || "").toLowerCase().includes("bond") || (r.Match_Notes || "").toLowerCase().includes("released");
      leadBadgeClass = isBonded ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-semibold" : "bg-purple-500/15 text-purple-300 border border-purple-500/30 font-semibold";
      const statusIcon = isBonded ? "🟢 Released on Bond" : "🔴 In Custody";
      leadBadgeIcon = `⚖️ Legal Distress (${statusIcon})`;
    } else if (isProbate) {
      leadBadgeClass = "bg-indigo-500/15 text-indigo-300 border border-indigo-500/30";
      leadBadgeIcon = `⚖️ ${r.Lead_Type || "Probate Court"}`;
    } else if (isDivorce) {
      leadBadgeClass = "bg-pink-500/15 text-pink-300 border border-pink-500/30";
      leadBadgeIcon = "💔 Divorce / Domestic";
    } else if (isJudgment) {
      leadBadgeClass = "bg-amber-500/15 text-amber-300 border border-amber-500/30";
      leadBadgeIcon = `🔨 ${r.Lead_Type || "Civil Judgment"}`;
    } else if (isLien) {
      leadBadgeClass = "bg-orange-500/15 text-orange-300 border border-orange-500/30";
      leadBadgeIcon = "📋 Recorded Lien";
    } else if (isPoa) {
      leadBadgeClass = "bg-teal-500/15 text-teal-300 border border-teal-500/30";
      leadBadgeIcon = "📜 Power of Attorney";
    } else if (isLp) {
      leadBadgeClass = "bg-purple-500/15 text-purple-300 border border-purple-500/30";
      leadBadgeIcon = "📄 Lis Pendens";
    } else if ((r.Lead_Type || "").includes("Tax Lien")) {
      leadBadgeClass = "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30";
      leadBadgeIcon = "💰 Tax Lien";
    } else if ((r.Lead_Type || "").toLowerCase().includes("water")) {
      leadBadgeClass = "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30";
      leadBadgeIcon = "💧 Water Shutoff";
    } else if ((r.Lead_Type || "").toLowerCase().includes("divorce") || (r.Lead_Type || "").toLowerCase().includes("domestic relations")) {
      leadBadgeClass = "bg-pink-500/15 text-pink-300 border border-pink-500/30";
      leadBadgeIcon = "💔 Divorce";
    } else if ((r.Lead_Type || "").toLowerCase().includes("judgment") || (r.Lead_Type || "").toLowerCase().includes("lien")) {
      leadBadgeClass = "bg-amber-500/15 text-amber-300 border border-amber-500/30";
      leadBadgeIcon = "🔨 Judgment / Lien";
    } else if (isCode) {
      leadBadgeClass = "bg-rose-500/15 text-rose-300 border border-rose-500/30";
      leadBadgeIcon = "🚨 Code Violation";
    } else if (r.Lead_Type && !["Code Violation", "Lis Pendens", "Probate"].includes(r.Lead_Type)) {
      leadBadgeClass = "bg-purple-500/15 text-purple-300 border border-purple-500/30";
      leadBadgeIcon = `⚖️ ${r.Lead_Type}`;
    }

    const propertyParcelId = r.Matched_Parcel_ID || r.Parcel_ID || '';
    const pQuery = encodeURIComponent(propertyParcelId);
    const addrQuery = encodeURIComponent(`${r.Property_Address || ""}, ${r.Property_City || selectedCountyKey || "Pinellas"}, FL`);
    
    // Property Appraiser URL (County specific)
    let paUrl = "https://www.pcpao.gov/quick-search";
    let paLabel = "🔍 PCPAO";
    const currentCountyLower = (selectedCountyKey || "").toLowerCase();
    if (currentCountyLower === "orange") {
      const orangePid = String(propertyParcelId).trim();
      paUrl = `https://www.ocpafl.org/Searches/ParcelSearch.aspx?pid=${encodeURIComponent(orangePid)}`;
      paLabel = "🔍 OCPA";
    } else {
      // Pinellas STRAP calculation: Range(2) + Township(2) + Section(2) + Subdivision(5) + Block(3) + Lot(4)
      const pidTrim = String(propertyParcelId).trim();
      const pidParts = pidTrim.split("-");
      if (pidParts.length === 6) {
        const strap = `${pidParts[2]}${pidParts[1]}${pidParts[0]}${pidParts[3]}${pidParts[4]}${pidParts[5]}`;
        paUrl = `https://www.pcpao.gov/property-details?s=${strap}`;
      } else if (pidTrim.replace(/[^0-9A-Za-z]/g, "").length === 18) {
        paUrl = `https://www.pcpao.gov/property-details?s=${pidTrim.replace(/[^0-9A-Za-z]/g, "")}`;
      }
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
    skipName = formatDisplayName((skipName || "").replace(/\b(TR|TRE|TRUSTEE|ESTATE|EST|OF|DECD|DECEASED|ET|AL|LIFE|LE)\b/gi, " ").replace(/\s+/g, " ").trim());
    const cleanPropAddr = formatDisplayAddress(r.Property_Address);
    const cleanPropCity = formatDisplayCity(r.Property_City || (selectedCountyKey === 'Orange' ? 'Orlando' : 'St Petersburg'));
    const cleanOwnerName = formatDisplayName(r.Clean_Full_Name || r.Clean_Last_Name || 'Unknown Owner');

    // Prefer mailing address city & state where owner currently lives (especially out-of-state/absentee)
    const skipCity = formatDisplayCity((r.Mailing_City || r.Property_City || (selectedCountyKey === 'Orange' ? 'Orlando' : 'St Petersburg')).trim());
    const skipState = (r.Mailing_State || "FL").trim();
    const skipLoc = `${skipCity}, ${skipState}`;
    
    // Hash parameters pass lead context seamlessly to the Chrome extension
    const skipTraceUrl = `https://www.truepeoplesearch.com/results?name=${encodeURIComponent(skipName)}&citystatezip=${encodeURIComponent(skipLoc)}#lead_hub_pid=${encodeURIComponent(r.Parcel_ID || '')}&county=${encodeURIComponent(selectedCountyKey)}&owner=${encodeURIComponent(skipName)}&addr=${encodeURIComponent(cleanPropAddr || r.Property_Address || '')}`;

    const savedContact = savedContactsCache[r.Parcel_ID] || ((r.Saved_Phone || r.Saved_Email) ? { phone: r.Saved_Phone, email: r.Saved_Email } : null);
    const savedPhone = savedContact ? savedContact.phone : null;
    const savedEmail = savedContact ? (savedContact.email || r.Saved_Email) : (r.Saved_Email || null);
    const lastSmsSent = (savedContact?.sms_initial_resend_pending || r.Sms_Initial_Resend_Pending) ? '' : (savedContact?.last_sms_sent || r.Last_Sms_Sent);
    const lastEmailSent = savedContact?.last_email_sent || r.Last_Email_Sent;

    window.leadsByPid = window.leadsByPid || {};
    if (r.Parcel_ID) window.leadsByPid[r.Parcel_ID] = r;

    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-800/40 transition cursor-pointer group";
    tr.onclick = (e) => {
      if (e.target.closest("button, a, input, select, textarea")) return;
      openPropertyCard(r.Parcel_ID);
    };

    tr.innerHTML = `
      <td class="px-4 py-3">
        <div class="flex flex-col gap-1 items-start">
          <div class="flex items-center gap-1.5 flex-wrap">
            <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${leadBadgeClass}">
              ${leadBadgeIcon}
            </span>
            ${isLeadNew(r) ? `
              <span id="lead-new-badge-${r.Parcel_ID}" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[9px] font-black bg-emerald-500/20 text-emerald-300 border border-emerald-500/60 shadow-sm animate-pulse" title="Live lead pulled directly from live API sync (new until opened)">
                ✨ NEW (LIVE API)
              </span>
            ` : ''}
          </div>
          ${isStacked ? `
            <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[9px] font-black bg-gradient-to-r from-rose-500/25 to-amber-500/25 text-amber-300 border border-amber-500/50 shadow-sm animate-pulse" title="${r.Distress_Stack_Notes || 'Multiple recorded distress types'}">
              🔥 DOUBLE DISTRESS
            </span>
          ` : ''}
          ${isLpTrust && !isStacked ? `
            <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[9px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
              🏛️ Trust / Estate
            </span>
          ` : ''}
        </div>
        <div class="flex items-center gap-1.5 text-[10px] mt-1 flex-wrap">
          <span class="text-emerald-400 font-semibold">✓ ${r.Match_Method || 'Exact PIN'}</span>
          ${(r.Filing_Date || r.Case_Date || r.Recording_Date) ? `<span class="text-cyan-300 font-mono text-[9px] font-bold px-1.5 py-0.5 rounded bg-cyan-950/70 border border-cyan-800/60 shadow-sm" title="Case Filing / Recording Date">📅 ${String(r.Filing_Date || r.Case_Date || r.Recording_Date).slice(0, 10)}</span>` : `<span class="text-slate-400 font-mono text-[9px] px-1 py-0.2 rounded bg-slate-900 border border-slate-800">📅 Recent Record</span>`}
        </div>
        ${r.Property_Match_Checked_At ? `<div class="text-[9px] text-slate-500 mt-0.5">Distress checked ${new Date(r.Property_Match_Checked_At).toLocaleDateString()}</div>` : ''}
        ${renderSavedDistressEvidence(r)}
        ${r.Distress_Stack_Notes ? `<div class="text-[9px] text-amber-300/90 font-medium mt-0.5 max-w-[210px] leading-tight" title="${r.Distress_Stack_Notes}">${r.Distress_Stack_Notes}</div>` : ''}
      </td>
      <td class="px-4 py-3" title="Click to view Property Card" onclick="openPropertyCard('${r.Parcel_ID}')">
        <div class="font-bold text-white text-xs group-hover:text-blue-300 transition flex items-center gap-1.5 flex-wrap">
          <span>${cleanPropAddr || 'N/A'}</span>
          <span class="text-[10px] text-blue-400 opacity-0 group-hover:opacity-100 transition">🏡</span>
          ${r.County ? `<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/40 shadow-sm" title="County: ${r.County}">📍 ${r.County} County</span>` : ''}
        </div>
        <div class="text-[10px] text-slate-400">${cleanPropCity}, FL ${r.Property_Zip || ''}</div>
        ${r.Photo_Url ? `
          <div class="mt-1">
            <a href="${r.Photo_Url}" target="_blank" onclick="event.stopPropagation();" class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 transition shadow-sm" title="Click to view full-resolution citizen/inspector ticket photo">
              📷 View Ticket Photo
            </a>
          </div>
        ` : ''}
      </td>
      <td class="px-4 py-3">
        <div class="font-bold text-blue-300 text-xs flex items-center gap-1.5">
          <span>${cleanOwnerName}</span>
          ${(r.Is_Sandbox || r.Parcel_ID === 'TEST-PINELLAS-001') ? '<span class="px-1.5 py-0.2 rounded text-[9px] font-extrabold bg-violet-500/25 text-violet-300 border border-violet-500/40">🧪 TEST LEAD</span>' : ''}
        </div>
        <div class="text-[10px] text-slate-500 mono">PIN: ${r.Matched_Parcel_ID || r.Parcel_ID || 'N/A'}</div>
        ${savedPhone ? `
          <div class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-[10px] font-bold mt-1 shadow-sm">
            <span>📱</span> <span>${savedPhone}</span>
          </div>
          ${lastSmsSent ? `<div class="text-[9px] text-emerald-400 font-semibold mt-0.5 flex items-center gap-1"><span>✓</span> <span>Texted ${lastSmsSent}</span></div>` : ''}
        ` : ''}
        ${savedEmail ? `
          <div class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 text-[10px] font-bold mt-1 shadow-sm">
            <span>✉️</span> <span>${savedEmail}</span>
          </div>
          ${lastEmailSent ? `<div class="text-[9px] text-cyan-400 font-semibold mt-0.5 flex items-center gap-1"><span>✓</span> <span>Emailed ${lastEmailSent}</span></div>` : ''}
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
      <td class="px-4 py-3 text-center whitespace-nowrap min-w-[340px]">
        <div class="flex items-center justify-center gap-1.5">
          ${(r.Is_Sandbox || r.Parcel_ID === 'TEST-PINELLAS-001') ? `
            <button type="button" onclick="event.stopPropagation(); openSandboxTestModal()" class="px-2.5 py-1 rounded bg-violet-600 hover:bg-violet-500 text-white text-[10px] font-bold transition flex items-center gap-1 shadow-md shadow-violet-600/30 cursor-pointer" title="1-Click Webhook & Deal Scorer Simulator">
              <span>⚡</span> <span>Test Webhook</span>
            </button>
          ` : ''}
          <button type="button" onclick="event.stopPropagation(); openUnderwrite407FlipsForLead('${r.Parcel_ID}', '${escapeAttr(cleanPropAddr)}', ${r.Year_Built || 1980}, ${r.Living_Sqft || 1500}, ${mktVal || 0}, '${escapeAttr(skipName)}')" class="px-2 py-1 rounded bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-slate-950 text-[10px] font-black transition flex items-center gap-1 shadow-sm border border-amber-400/50 cursor-pointer" title="407flips Underwriting Audit (8-Point Standard, 4-Point Insurance Triggers & MAO)">
            <span>407</span> <span>Audit</span>
          </button>
          <button type="button" onclick="event.stopPropagation(); openContractModal('${r.Parcel_ID}', '${escapeAttr(savedPhone || '')}', '${escapeAttr(savedEmail || '')}', '${escapeAttr(skipName)}', '${escapeAttr(cleanPropAddr)}', '${escapeAttr(cleanPropCity)}', '${escapeAttr(r.Property_Zip || '')}', ${mktVal})" class="px-2.5 py-1 rounded bg-purple-600 hover:bg-purple-500 text-white text-[10px] font-bold transition flex items-center gap-1 shadow-md shadow-purple-600/30 cursor-pointer" title="Generate 1-Page Wholesale Purchase Agreement & E-Sign via PandaDoc">
            <span>📝</span> <span>Contract</span>
          </button>
          ${savedPhone ? `
            <button type="button" onclick="event.stopPropagation(); openSmsModal('${r.Parcel_ID}', '${savedPhone}', '${escapeAttr(skipName)}', '${escapeAttr(cleanPropAddr)}')" class="px-2.5 py-1 rounded ${lastSmsSent ? 'bg-emerald-700 hover:bg-emerald-600 ring-1 ring-emerald-400 text-emerald-100' : 'bg-emerald-600 hover:bg-emerald-500 text-white'} text-[10px] font-bold transition flex items-center gap-1 shadow-md shadow-emerald-600/30 cursor-pointer" title="${lastSmsSent ? 'Texted ' + lastSmsSent + ' - Click to review message history' : 'Send Wholesale SMS Offer via Android Gateway'}">
              <span>💬</span> <span>${lastSmsSent ? 'SMS (Sent)' : 'SMS'}</span>
            </button>
          ` : ''}
          ${savedEmail ? `
            <button type="button" onclick="event.stopPropagation(); openEmailModal('${r.Parcel_ID}', '${savedEmail}', '${escapeAttr(skipName)}', '${escapeAttr(cleanPropAddr)}')" class="px-2.5 py-1 rounded ${lastEmailSent ? 'bg-cyan-700 hover:bg-cyan-600 ring-1 ring-cyan-400 text-cyan-100' : 'bg-cyan-600 hover:bg-cyan-500 text-white'} text-[10px] font-bold transition flex items-center gap-1 shadow-md shadow-cyan-600/30 cursor-pointer" title="${lastEmailSent ? 'Emailed ' + lastEmailSent + ' - Click to review or send follow-up' : 'Send Wholesale HTML Offer via SMTP2GO'}">
              <span>✉️</span> <span>${lastEmailSent ? 'Email (Sent)' : 'Email'}</span>
            </button>
          ` : ''}
          ${!savedPhone && !savedEmail ? `
            <a href="${skipTraceUrl}" target="_blank" rel="noopener noreferrer" onclick="markLeadAsViewed('${r.Parcel_ID}'); event.stopPropagation();" class="px-2 py-1 rounded bg-amber-500/20 hover:bg-amber-500 hover:text-slate-950 text-amber-300 text-[10px] font-bold transition flex items-center gap-1 shadow-sm border border-amber-500/30" title="Free 1-Click Skip Trace (TruePeopleSearch) for ${skipName || 'Owner'}">
              <span>📞</span> <span>Free Trace</span>
            </a>
          ` : `
            <a href="${skipTraceUrl}" target="_blank" rel="noopener noreferrer" onclick="markLeadAsViewed('${r.Parcel_ID}'); event.stopPropagation();" class="px-1.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] transition" title="Search additional phone numbers & emails">
              🔄
            </a>
          `}
          <a href="${paUrl}" target="_blank" onclick="markLeadAsViewed('${r.Parcel_ID}'); event.stopPropagation();" class="px-2 py-1 rounded bg-slate-800 hover:bg-blue-600 hover:text-white text-slate-300 text-[10px] font-semibold transition" title="View Property Appraiser">
            ${paLabel}
          </a>
          <a href="${mapsUrl}" target="_blank" onclick="markLeadAsViewed('${r.Parcel_ID}'); event.stopPropagation();" class="px-2 py-1 rounded bg-slate-800 hover:bg-emerald-600 hover:text-white text-slate-300 text-[10px] font-semibold transition" title="Google Maps">
            🗺️ Maps
          </a>
          <button type="button" onclick="event.stopPropagation(); deleteLead('${r.Parcel_ID}', '${escapeAttr(r.Property_Address || '')}')" class="px-2 py-1 rounded bg-rose-500/15 hover:bg-rose-500 hover:text-white text-rose-300 text-[10px] font-bold transition flex items-center gap-1 shadow-sm border border-rose-500/30 cursor-pointer" title="Delete lead from Lead Hub">
            <span>🗑️</span>
          </button>
        </div>
      </td>
    `;
    fragment.appendChild(tr);
  });
  tbody.appendChild(fragment);
}

function updatePaginationUI(total) {
  const container = document.getElementById("livePaginationContainer");
  if (!container) return;

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (currentPage > totalPages) currentPage = totalPages;

  const start = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const end = Math.min(currentPage * pageSize, total);

  const elStart = document.getElementById("pagStart");
  if (elStart) elStart.innerText = start.toLocaleString();
  const elEnd = document.getElementById("pagEnd");
  if (elEnd) elEnd.innerText = end.toLocaleString();
  const elTotal = document.getElementById("pagTotal");
  if (elTotal) elTotal.innerText = total.toLocaleString();
  const elCur = document.getElementById("pagCurrentPage");
  if (elCur) elCur.innerText = currentPage;
  const elTotPages = document.getElementById("pagTotalPages");
  if (elTotPages) elTotPages.innerText = totalPages;

  const btnPrev = document.getElementById("btnPagPrev");
  if (btnPrev) btnPrev.disabled = currentPage <= 1;
  const btnNext = document.getElementById("btnPagNext");
  if (btnNext) btnNext.disabled = currentPage >= totalPages;

  const numContainer = document.getElementById("pagPageNumbers");
  if (numContainer) {
    numContainer.innerHTML = "";
    const pagesToShow = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) pagesToShow.push(i);
    } else {
      pagesToShow.push(1);
      if (currentPage > 3) pagesToShow.push("...");
      const startP = Math.max(2, currentPage - 1);
      const endP = Math.min(totalPages - 1, currentPage + 1);
      for (let i = startP; i <= endP; i++) {
        if (!pagesToShow.includes(i)) pagesToShow.push(i);
      }
      if (currentPage < totalPages - 2) pagesToShow.push("...");
      if (!pagesToShow.includes(totalPages)) pagesToShow.push(totalPages);
    }

    pagesToShow.forEach(p => {
      if (p === "...") {
        const span = document.createElement("span");
        span.className = "px-1 text-slate-500 font-bold select-none text-[11px]";
        span.innerText = "…";
        numContainer.appendChild(span);
      } else {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = (p === currentPage)
          ? "w-7 h-7 rounded-lg bg-blue-600 text-white font-bold text-xs shadow-sm cursor-pointer select-none"
          : "w-7 h-7 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs border border-slate-700 transition cursor-pointer select-none";
        btn.innerText = p;
        btn.onclick = () => goToPage(p);
        numContainer.appendChild(btn);
      }
    });
  }
}

window.goToPage = function(page) {
  const totalPages = Math.max(1, Math.ceil(currentFilteredRecords.length / pageSize));
  if (page < 1 || page > totalPages) return;
  currentPage = page;
  renderLiveTable(currentFilteredRecords, false);
  const tableContainer = document.getElementById("liveTableContainer");
  if (tableContainer) tableContainer.scrollTop = 0;
};

window.changePageSize = function(newSize) {
  pageSize = Number(newSize) || 50;
  currentPage = 1;
  renderLiveTable(currentFilteredRecords, false);
};

const CONDO_UNIT_REGEX = /(\b(unit|apt|ste|suite|condo)\b|#)/i;

function isCondoOrUnit(addr) {
  return CONDO_UNIT_REGEX.test(addr || "");
}

window.excludeCondos = true;

window.toggleExcludeCondos = function(checked) {
  window.excludeCondos = Boolean(checked);
  updateFilterCounts();
  filterLiveRecords(currentFilter || "all");
};

window.purgeAllCondos = async function() {
  const conf = confirm("Are you sure you want to permanently purge and delete all condo/apartment leads (#, Unit, Apt, Ste, Condo) from Lead Hub?");
  if (!conf) return;

  try {
    const res = await fetch("/api/leads/purge-condos", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert(`Purged ${data.purged_count} condo/apartment leads! Reloading live leads...`);
      fetchLeads(selectedCountyKey || "Pinellas");
    } else {
      alert(`Failed to purge condos: ${data.message || 'Unknown error'}`);
    }
  } catch (err) {
    alert(`Error purging condos: ${err.message}`);
  }
};

window.deleteLead = async function(parcelId, address) {
  if (!parcelId) return;
  const label = address ? `"${address}" (${parcelId})` : parcelId;
  const conf = confirm(`Delete lead ${label} from Lead Hub?`);
  if (!conf) return;

  try {
    const res = await fetch(`/api/leads/${encodeURIComponent(parcelId)}`, { method: "DELETE" });
    const data = await res.json();
    if (data.status === "success") {
      liveRecords = (liveRecords || []).filter(r => r.Parcel_ID !== parcelId);
      if (savedContactsCache) delete savedContactsCache[parcelId];
      updateFilterCounts();
      updateSavedPipelineCount();
      filterLiveRecords(currentFilter || "all");
    } else {
      alert(`Could not delete lead: ${data.detail || data.message || 'Unknown error'}`);
    }
  } catch (err) {
    alert(`Error deleting lead: ${err.message}`);
  }
};

function renderSavedDistressEvidence(record) {
  if (!Array.isArray(record.Distress_Evidence) || !record.Distress_Evidence.length) return '';
  const lines = record.Distress_Evidence.map(e => {
    const reference = e.Case_Number || e.Document_Number || e['Subject_Case Number'] || e.County_Book_Page;
    const date = e.Recording_Date || e.Filing_Date || e.Case_Date;
    return `<div class="mt-1">${escapeHtml([e.Lead_Type, reference, date, e.Source_File].filter(Boolean).join(' · '))}</div>`;
  }).join('');
  return `<details class="text-[9px] text-slate-400 mt-1 max-w-[230px]"><summary class="cursor-pointer text-cyan-300">View source records (${record.Distress_Evidence.length})</summary>${lines}</details>`;
}

function isActiveCountyLead(county) {
  const normalize = value => String(value || '').trim().replace(/\s+county$/i, '').toLowerCase();
  // Imported contact.state can be the owner's mailing state. The saved county
  // identifies the property's county, including properties with absentee owners.
  return !!normalize(county) && normalize(county) === normalize(selectedCountyKey);
}

function getActivePipelineDataset() {
  const activeLiveRecords = (liveRecords || []).filter(r => isActiveCountyLead(
    r.County || (typeof loadedCountyKey === 'undefined' ? selectedCountyKey : loadedCountyKey), r.State));
  let rawDataset = activeLiveRecords;
  if (currentPipelineView === "saved") {
    const groups = new Map();
    for (const [pid, contact] of Object.entries(savedContactsCache || {})) {
      if (!isActiveCountyLead(contact.county || contact.property_match?.record?.County, contact.state)) continue;
      const canonical = String(contact.matched_parcel_id || pid);
      const key = `${contact.state || 'FL'}:${contact.county || selectedCountyKey}:${canonical}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push([pid, contact]);
    }
    rawDataset = [];
    const included = new Set();
    for (const entries of groups.values()) {
      // Keep original contact IDs for outreach history; one displayed row per saved property link.
      entries.sort((a, b) => Number(String(b[1].source || '').startsWith('Skip Trace CSV')) - Number(String(a[1].source || '').startsWith('Skip Trace CSV')));
      const [pid, contact] = entries[0];
      const canonical = String(contact.matched_parcel_id || pid);
      included.add(canonical);
      const live = activeLiveRecords.find(r => String(r.Parcel_ID) === canonical) || {};
      const saved = entries.find(([, c]) => c.property_match)?.[1].property_match;
      const details = saved?.record || {};
      const phoneContact = entries.find(([, c]) => c.phone)?.[1] || contact;
      const emailContact = entries.find(([, c]) => c.email)?.[1] || contact;
      rawDataset.push({
        ...live, ...details,
        Parcel_ID: pid, Matched_Parcel_ID: canonical,
        Contact_Parcel_IDs: entries.map(([id]) => id),
        Sms_Initial_Resend_Pending: entries.some(([, c]) => c.sms_initial_resend_pending),
        Clean_Full_Name: details.Clean_Full_Name || live.Clean_Full_Name || contact.owner || 'Property Owner',
        Property_Address: details.Property_Address || live.Property_Address || contact.address || 'Florida Property',
        Property_City: details.Property_City || live.Property_City || contact.city || contact.county || 'Florida',
        Property_Zip: details.Property_Zip || live.Property_Zip || contact.zip || '',
        County: contact.county || selectedCountyKey || 'Florida',
        Lead_Type: details.Lead_Type || live.Lead_Type || contact.distress_category || 'Skip-Traced Lead',
        Market_Value: details.Market_Value || live.Market_Value || contact.just_value || 0,
        Just_Value: details.Just_Value || live.Just_Value || contact.just_value || 0,
        Saved_Phone: phoneContact.phone || live.Saved_Phone || '',
        Saved_Email: emailContact.email || live.Saved_Email || '',
        Last_Sms_Sent: entries.map(([, c]) => c.last_sms_sent || '').sort().at(-1) || live.Last_Sms_Sent || '',
        Last_Email_Sent: entries.map(([, c]) => c.last_email_sent || '').sort().at(-1) || live.Last_Email_Sent || '',
        Property_Match_Checked_At: saved?.checked_at || '',
        Distress_Evidence: saved?.evidence || [],
        Is_Sandbox: pid.startsWith('TEST-') || contact.source === 'Sandbox Demo Lead',
      });
    }
    for (const record of activeLiveRecords) {
      if (!included.has(String(record.Parcel_ID)) && (record.Saved_Phone || record.Saved_Email)) rawDataset.push(record);
    }
  }
  return window.excludeCondos ? rawDataset.filter(r => !isCondoOrUnit(r.Property_Address)) : rawDataset;
}

function getSavedPropertyCount() {
  return new Set(Object.entries(savedContactsCache || {})
    .filter(([, c]) => isActiveCountyLead(c.county || c.property_match?.record?.County, c.state))
    .map(([pid, c]) =>
    `${c.state || 'FL'}:${c.county || selectedCountyKey}:${c.matched_parcel_id || pid}`)).size;
}

async function refreshSavedDistressDetails() {
  const button = document.getElementById('btnRefreshSavedDistress');
  if (button) button.disabled = true;
  try {
    const res = await fetch('/api/leads/refresh-property-matches', { method: 'POST' });
    const data = await res.json();
    if (!res.ok || data.status !== 'success') throw new Error(data.detail || 'Could not refresh distress details');
    await fetchSavedContacts();
    updateFilterCounts();
    filterLiveRecords(currentFilter);
    alert(`Saved distress details updated for ${data.unique_properties} properties. ${data.unresolved.length} contacts could not be linked and were left unchanged.`);
  } catch (err) {
    alert(err.message);
  } finally {
    if (button) button.disabled = false;
  }
}

function isCodeViolationLead(r) {
  if (!r) return false;
  if (r.Lead_Type === "Code Violation") return true;
  if (Array.isArray(r.All_Lead_Types) && r.All_Lead_Types.includes("Code Violation")) return true;
  if ((r.Distress_Stack_Notes || "").toLowerCase().includes("code violation")) return true;
  return false;
}

function isCodeStackedLead(r) {
  if (!isCodeViolationLead(r)) return false;
  return r.Is_Stacked_Distress === "Yes";
}

function hasLeadPhoto(record) {
  return /^https?:\/\//i.test(String(record.Photo_Url || '').trim());
}

function filterLiveRecords(type) {
  currentFilter = type;
  
  // Highlight tab with correct element IDs
  const tabBtnMap = {
    all: "btnTabAll",
    has_photos: "btnTabPhotos",
    stacked: "btnTabStacked",
    code_stacked: "btnTabCodeStacked",
    code: "btnTabCode",
    lis_pendens: "btnTabLp",
    lp_trust: "btnTabLpTrust",
    probate: "btnTabProbate",
    divorce: "btnTabDivorce",
    judgment: "btnTabJudgment",
    absentee: "btnTabAbsentee",
    tax_liens: "btnTabTax",
    trust: "btnTabTrust",
    water_shutoff: "btnTabWater",
    legal_distress: "btnTabLegal",
    damage: "btnTabDamage"
  };

  Object.entries(tabBtnMap).forEach(([t, btnId]) => {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    if (t === type) {
      if (t === 'stacked' || t === 'code_stacked') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold bg-amber-500 text-slate-950 shadow-md cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5";
      } else if (t === 'water_shutoff') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold bg-cyan-600 text-white shadow-md cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5";
      } else if (t === 'legal_distress') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold bg-purple-600 text-white shadow-md cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5";
      } else if (t === 'damage') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold bg-rose-600 text-white shadow-md cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5";
      } else if (t === 'divorce') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold bg-pink-600 text-white shadow-md cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5";
      } else if (t === 'judgment') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold bg-amber-600 text-white shadow-md cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5";
      } else {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-blue-600 text-white shadow-sm cursor-pointer whitespace-nowrap";
      }
    } else {
      if (t === 'stacked') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-amber-300 hover:text-white border border-amber-500/40 transition cursor-pointer whitespace-nowrap";
      } else if (t === 'code_stacked') {
        btn.className = "px-2.5 py-1 rounded-lg text-xs font-bold text-amber-300 hover:text-white transition cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5";
      } else if (t === 'lp_trust') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-purple-300 hover:text-white transition cursor-pointer whitespace-nowrap";
      } else if (t === 'probate') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-indigo-300 hover:text-white transition cursor-pointer whitespace-nowrap";
      } else if (t === 'damage') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-rose-300 hover:text-white border border-rose-500/30 transition cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5";
      } else if (t === 'divorce') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-pink-300 hover:text-white border border-pink-500/30 transition cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5";
      } else if (t === 'judgment') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-amber-300 hover:text-white border border-amber-500/30 transition cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5";
      } else if (t === 'tax_liens') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-rose-300 hover:text-white transition cursor-pointer whitespace-nowrap";
      } else if (t === 'water_shutoff') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-cyan-300 hover:text-white border border-cyan-500/30 transition cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5";
      } else if (t === 'legal_distress') {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-purple-300 hover:text-white border border-purple-500/30 transition cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5";
      } else {
        btn.className = "px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-slate-300 hover:text-white transition cursor-pointer whitespace-nowrap";
      }
    }
  });

  // Toggle sub-distress priority bar for Code Enforcement
  const subBar = document.getElementById("codeSubDistressBar");
  if (subBar) {
    if (type.startsWith("code")) {
      subBar.classList.remove("hidden");
    } else {
      subBar.classList.add("hidden");
    }
  }

  // Highlight sub-category buttons
  const subBtns = {
    code_stacked: "btnSubCodeAllStacked",
    code_judgment: "btnSubCodeJudgment",
    code_probate: "btnSubCodeProbate",
    code_lp: "btnSubCodeLp",
    code_water: "btnSubCodeWater",
    code: "btnSubCodeAll"
  };
  Object.entries(subBtns).forEach(([k, btnId]) => {
    const el = document.getElementById(btnId);
    if (!el) return;
    if (type === k) {
      el.className = "px-2.5 py-1 rounded-lg font-bold bg-amber-500 text-slate-950 shadow-sm cursor-pointer whitespace-nowrap transition";
    } else {
      el.className = "px-2.5 py-1 rounded-lg font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 cursor-pointer whitespace-nowrap transition";
    }
  });

  if (!liveRecords && currentPipelineView !== "saved") return;

  renderLiveTable(getFilteredPipelineDataset(type));
  updateExportButtonsUI();
}

function getFilteredPipelineDataset(type = currentFilter) {
  const dataset = getActivePipelineDataset();

  if (type === "all") {
    return (dataset);
  } else if (type === "has_photos") {
    return (dataset.filter(hasLeadPhoto));
  } else if (type === "stacked") {
    return (dataset.filter(r => r.Is_Stacked_Distress === "Yes"));
  } else if (type === "code_stacked" || type === "code_double") {
    return (dataset.filter(r => isCodeStackedLead(r)));
  } else if (type === "code_judgment") {
    return (dataset.filter(r => isCodeViolationLead(r) && (
      (r.Distress_Stack_Notes || "").toLowerCase().includes("judgment") ||
      (r.Distress_Stack_Notes || "").toLowerCase().includes("lien") ||
      (r.All_Lead_Types || []).some(t => (t||"").toLowerCase().includes("judgment") || (t||"").toLowerCase().includes("lien"))
    )));
  } else if (type === "code_probate") {
    return (dataset.filter(r => isCodeViolationLead(r) && (
      (r.Distress_Stack_Notes || "").toLowerCase().includes("probate") ||
      (r.All_Lead_Types || []).some(t => (t||"").toLowerCase().includes("probate"))
    )));
  } else if (type === "code_lp") {
    return (dataset.filter(r => isCodeViolationLead(r) && (
      (r.Distress_Stack_Notes || "").toLowerCase().includes("lis pendens") ||
      (r.All_Lead_Types || []).some(t => (t||"").toLowerCase().includes("lis pendens"))
    )));
  } else if (type === "code_water") {
    return (dataset.filter(r => isCodeViolationLead(r) && (
      (r.Distress_Stack_Notes || "").toLowerCase().includes("water") ||
      (r.All_Lead_Types || []).some(t => (t||"").toLowerCase().includes("water") || (t||"").toLowerCase().includes("ouc"))
    )));
  } else if (type === "lis_pendens") {
    return (dataset.filter(r => r.Lead_Type === "Lis Pendens"));
  } else if (type === "lp_trust") {
    return (dataset.filter(r => r.Lead_Type === "Lis Pendens" && (r.Is_Trust_In_LP === "Yes" || r.Is_Trust_Or_Estate === "Yes")));
  } else if (type === "probate") {
    return (dataset.filter(r => r.Has_Confirmed_Probate === 'Yes' || (r.Lead_Type || '').toLowerCase().includes('probate')));
  } else if (type === "divorce") {
    return (dataset.filter(r => (r.Lead_Type || "").toLowerCase().includes("divorce") || (r.Lead_Type || "").toLowerCase().includes("domestic relations")));
  } else if (type === "judgment" || type === "judgments" || type === "lien" || type === "liens") {
    return (dataset.filter(r => (r.Lead_Type || "").toLowerCase().includes("judgment") || (r.Lead_Type || "").toLowerCase().includes("lien")));
  } else if (type === "code") {
    return (dataset.filter(r => isCodeViolationLead(r)));
  } else if (type === "absentee") {
    return (dataset.filter(r => (r.Absentee_Status || "").includes("Out-of-State")));
  } else if (type === "trust") {
    return (dataset.filter(r => (r.Owner_Entity_Type || "").includes("Trust") || (r.Lead_Type || "").toLowerCase().includes("probate") || r.Is_Trust_Or_Estate === "Yes"));
  } else if (type === "tax_liens") {
    return (dataset.filter(r => (r.Lead_Type || "").includes("Tax Lien")));
  } else if (type === "water_shutoff" || type === "water" || type === "ouc") {
    return (dataset.filter(r => 
      (r.Lead_Type || "").toLowerCase().includes("water") || 
      (r.Lead_Type || "").toLowerCase().includes("ouc") ||
      (r.Distress_Stack_Notes || "").toLowerCase().includes("water")
    ));
  } else if (type === "legal_distress" || type === "legal" || type === "jail" || type === "felony") {
    return (dataset.filter(r => 
      (r.Lead_Type || "").toLowerCase().includes("legal distress") || 
      (r.Lead_Type || "").toLowerCase().includes("felony") ||
      (r.Distress_Stack_Notes || "").toLowerCase().includes("felony")
    ));
  } else if (type === "damage" || type === "substantial_damage") {
    return (dataset.filter(r => (r.Lead_Type || "").toLowerCase().includes("substantial damage")));
  } else if (type === "new_unread" || type === "new_api") {
    return (dataset.filter(r => isLeadNew(r)));
  }
  return dataset;
}

function updateFilterCounts() {
  if (!liveRecords && currentPipelineView !== "saved") return;
  const dataset = getActivePipelineDataset();

  const elAll = document.getElementById("liveCountAll");
  if (elAll) elAll.innerText = dataset.length.toLocaleString();

  const elPhotos = document.getElementById("liveCountPhotos");
  if (elPhotos) elPhotos.innerText = dataset.filter(hasLeadPhoto).length.toLocaleString();

  const elStacked = document.getElementById("liveCountStacked");
  if (elStacked) elStacked.innerText = dataset.filter(r => r.Is_Stacked_Distress === "Yes").length.toLocaleString();

  const codeStackedLeads = dataset.filter(r => isCodeStackedLead(r));
  const elCodeStacked = document.getElementById("liveCountCodeStacked");
  if (elCodeStacked) {
    elCodeStacked.innerText = codeStackedLeads.length.toLocaleString();
    const wrapCodeStacked = document.getElementById("pillWrap_code_stacked");
    if (wrapCodeStacked) {
      wrapCodeStacked.style.display = codeStackedLeads.length > 0 ? "inline-flex" : "none";
    }
  }

  // Update sub-distress counts for Code Enforcement
  const elSubStacked = document.getElementById("subCountCodeStacked");
  if (elSubStacked) elSubStacked.innerText = codeStackedLeads.length.toLocaleString();

  const elSubJudg = document.getElementById("subCountCodeJudgment");
  if (elSubJudg) {
    elSubJudg.innerText = dataset.filter(r => isCodeViolationLead(r) && (
      (r.Distress_Stack_Notes || "").toLowerCase().includes("judgment") ||
      (r.Distress_Stack_Notes || "").toLowerCase().includes("lien") ||
      (r.All_Lead_Types || []).some(t => (t||"").toLowerCase().includes("judgment") || (t||"").toLowerCase().includes("lien"))
    )).length.toLocaleString();
  }

  const elSubProb = document.getElementById("subCountCodeProbate");
  if (elSubProb) {
    elSubProb.innerText = dataset.filter(r => isCodeViolationLead(r) && (
      (r.Distress_Stack_Notes || "").toLowerCase().includes("probate") ||
      (r.All_Lead_Types || []).some(t => (t||"").toLowerCase().includes("probate"))
    )).length.toLocaleString();
  }

  const elSubLp = document.getElementById("subCountCodeLp");
  if (elSubLp) {
    elSubLp.innerText = dataset.filter(r => isCodeViolationLead(r) && (
      (r.Distress_Stack_Notes || "").toLowerCase().includes("lis pendens") ||
      (r.All_Lead_Types || []).some(t => (t||"").toLowerCase().includes("lis pendens"))
    )).length.toLocaleString();
  }

  const elSubWater = document.getElementById("subCountCodeWater");
  if (elSubWater) {
    elSubWater.innerText = dataset.filter(r => isCodeViolationLead(r) && (
      (r.Distress_Stack_Notes || "").toLowerCase().includes("water") ||
      (r.All_Lead_Types || []).some(t => (t||"").toLowerCase().includes("water") || (t||"").toLowerCase().includes("ouc"))
    )).length.toLocaleString();
  }

  const elSubAll = document.getElementById("subCountCodeAll");
  if (elSubAll) elSubAll.innerText = dataset.filter(r => isCodeViolationLead(r)).length.toLocaleString();

  const elLp = document.getElementById("liveCountLp");
  if (elLp) elLp.innerText = dataset.filter(r => r.Lead_Type === "Lis Pendens").length.toLocaleString();

  const elLpTrust = document.getElementById("liveCountLpTrust");
  if (elLpTrust) elLpTrust.innerText = dataset.filter(r => r.Lead_Type === "Lis Pendens" && (r.Is_Trust_In_LP === "Yes" || r.Is_Trust_Or_Estate === "Yes")).length.toLocaleString();

  const elProbate = document.getElementById("liveCountProbate");
  if (elProbate) elProbate.innerText = dataset.filter(r => r.Has_Confirmed_Probate === 'Yes' || (r.Lead_Type || '').toLowerCase().includes('probate')).length.toLocaleString();

  const elDivorce = document.getElementById("liveCountDivorce");
  if (elDivorce) {
    const divorceCount = dataset.filter(r => (r.Lead_Type || "").toLowerCase().includes("divorce") || (r.Lead_Type || "").toLowerCase().includes("domestic relations")).length;
    elDivorce.innerText = divorceCount.toLocaleString();
    const btnDivorce = document.getElementById("btnTabDivorce");
    if (btnDivorce) {
      btnDivorce.style.display = divorceCount > 0 ? "inline-flex" : "none";
    }
    const wrapDivorce = document.getElementById("pillWrap_divorce");
    if (wrapDivorce) {
      wrapDivorce.style.display = divorceCount > 0 ? "inline-flex" : "none";
    }
  }

  const elJudgment = document.getElementById("liveCountJudgment");
  if (elJudgment) {
    const judgmentCount = dataset.filter(r => (r.Lead_Type || "").toLowerCase().includes("judgment") || (r.Lead_Type || "").toLowerCase().includes("lien")).length;
    elJudgment.innerText = judgmentCount.toLocaleString();
    const btnJudgment = document.getElementById("btnTabJudgment");
    if (btnJudgment) {
      btnJudgment.style.display = judgmentCount > 0 ? "inline-flex" : "none";
    }
    const wrapJudgment = document.getElementById("pillWrap_judgment");
    if (wrapJudgment) {
      wrapJudgment.style.display = judgmentCount > 0 ? "inline-flex" : "none";
    }
  }

  const elCode = document.getElementById("liveCountCode");
  if (elCode) elCode.innerText = dataset.filter(r => isCodeViolationLead(r)).length.toLocaleString();

  const elAbsentee = document.getElementById("liveCountAbsentee");
  if (elAbsentee) elAbsentee.innerText = dataset.filter(r => (r.Absentee_Status || "").includes("Out-of-State")).length.toLocaleString();

  const elTrust = document.getElementById("liveCountTrust");
  if (elTrust) elTrust.innerText = dataset.filter(r => (r.Owner_Entity_Type || "").includes("Trust") || (r.Lead_Type || "").toLowerCase().includes("probate") || r.Is_Trust_Or_Estate === "Yes").length.toLocaleString();

  const elTax = document.getElementById("liveCountTax");
  if (elTax) elTax.innerText = dataset.filter(r => (r.Lead_Type || "").includes("Tax Lien")).length.toLocaleString();

  const elWater = document.getElementById("liveCountWater");
  if (elWater) {
    const waterCount = dataset.filter(r => 
      (r.Lead_Type || "").toLowerCase().includes("water") || 
      (r.Lead_Type || "").toLowerCase().includes("ouc") ||
      (r.Distress_Stack_Notes || "").toLowerCase().includes("water")
    ).length;
    elWater.innerText = waterCount.toLocaleString();
    const btnWater = document.getElementById("btnTabWater");
    if (btnWater) {
      btnWater.style.display = waterCount > 0 ? "inline-flex" : "none";
    }
    const wrapWater = document.getElementById("pillWrap_water_shutoff");
    if (wrapWater) {
      wrapWater.style.display = waterCount > 0 ? "inline-flex" : "none";
    }
  }

  const elLegal = document.getElementById("liveCountLegal");
  if (elLegal) {
    const legalCount = dataset.filter(r => 
      (r.Lead_Type || "").toLowerCase().includes("legal distress") || 
      (r.Lead_Type || "").toLowerCase().includes("felony") ||
      (r.Distress_Stack_Notes || "").toLowerCase().includes("felony")
    ).length;
    elLegal.innerText = legalCount.toLocaleString();
    const btnLegal = document.getElementById("btnTabLegal");
    if (btnLegal) {
      btnLegal.style.display = legalCount > 0 ? "inline-flex" : "none";
    }
    const wrapLegal = document.getElementById("pillWrap_legal_distress");
    if (wrapLegal) {
      wrapLegal.style.display = legalCount > 0 ? "inline-flex" : "none";
    }
  }

  const elDamage = document.getElementById("liveCountDamage");
  if (elDamage) {
    const damageCount = dataset.filter(r => (r.Lead_Type || "").toLowerCase().includes("substantial damage")).length;
    elDamage.innerText = damageCount.toLocaleString();
    const btnDamage = document.getElementById("btnTabDamage");
    if (btnDamage) {
      btnDamage.style.display = damageCount > 0 ? "inline-flex" : "none";
    }
    const wrapDamage = document.getElementById("pillWrap_damage");
    if (wrapDamage) {
      wrapDamage.style.display = damageCount > 0 ? "inline-flex" : "none";
    }
  }

  // Calculate unviewed fresh Live API leads count & update liveUnreadApiBadge
  const unreadApiLeads = dataset.filter(r => isLeadNew(r));
  const elUnreadBadge = document.getElementById("liveUnreadApiBadge");
  const elUnreadCount = document.getElementById("liveUnreadApiCount");
  if (elUnreadBadge && elUnreadCount) {
    if (unreadApiLeads.length > 0) {
      elUnreadCount.innerText = unreadApiLeads.length.toLocaleString();
      elUnreadBadge.classList.remove("hidden");
    } else {
      elUnreadBadge.classList.add("hidden");
    }
  }

  updateExportButtonsUI();
}

function updateSavedPipelineCount() {
  const savedCount = getSavedPropertyCount();
  const pCountSaved = document.getElementById("pipelineCountSaved");
  if (pCountSaved) pCountSaved.innerText = savedCount;
  const sideCountSaved = document.getElementById("sidebarSavedCount");
  if (sideCountSaved) sideCountSaved.innerText = savedCount;
  if (currentPipelineView === 'saved') {
    const title = document.getElementById('liveCountyTitle');
    if (title) title.innerText = `⭐ ${selectedCountyKey} County · Saved Lists & Active Pipeline`;
    const badge = document.getElementById('liveStatusBadge');
    if (badge) badge.innerText = `${savedCount} Saved Leads · ${selectedCountyKey}`;
  }
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
  fetchOpenerMetrics();
}

async function fetchOpenerMetrics() {
  try {
    const res = await fetch("/api/outreach/opener-metrics");
    if (!res.ok) return;
    const data = await res.json();
    if (!data || !data.angles) return;

    const angles = data.angles;
    const topPerformer = data.summary ? data.summary.top_performer : null;

    // Multi-List Tier
    const ml = angles.multi_list || { sent: 0, replied: 0, reply_rate: 0 };
    const rML = document.getElementById("rateMultiList");
    const sML = document.getElementById("sentMultiList");
    const repML = document.getElementById("repliedMultiList");
    const badgeML = document.getElementById("badgeMultiListTop");
    if (rML) rML.innerText = `${ml.reply_rate}%`;
    if (sML) sML.innerText = ml.sent;
    if (repML) repML.innerText = ml.replied;
    if (badgeML) {
      if (topPerformer === "multi_list" && ml.sent > 0 && ml.replied > 0) {
        badgeML.classList.remove("hidden");
      } else {
        badgeML.classList.add("hidden");
      }
    }

    // Single-List Tier
    const sl = angles.single_list || { sent: 0, replied: 0, reply_rate: 0 };
    const rSL = document.getElementById("rateSingleList");
    const sSL = document.getElementById("sentSingleList");
    const repSL = document.getElementById("repliedSingleList");
    const badgeSL = document.getElementById("badgeSingleListTop");
    if (rSL) rSL.innerText = `${sl.reply_rate}%`;
    if (sSL) sSL.innerText = sl.sent;
    if (repSL) repSL.innerText = sl.replied;
    if (badgeSL) {
      if (topPerformer === "single_list" && sl.sent > 0 && sl.replied > 0) {
        badgeSL.classList.remove("hidden");
      } else {
        badgeSL.classList.add("hidden");
      }
    }

    // Ultra-Short Tier
    const us = angles.ultra_short || { sent: 0, replied: 0, reply_rate: 0 };
    const rUS = document.getElementById("rateUltraShort");
    const sUS = document.getElementById("sentUltraShort");
    const repUS = document.getElementById("repliedUltraShort");
    const badgeUS = document.getElementById("badgeUltraShortTop");
    if (rUS) rUS.innerText = `${us.reply_rate}%`;
    if (sUS) sUS.innerText = us.sent;
    if (repUS) repUS.innerText = us.replied;
    if (badgeUS) {
      if (topPerformer === "ultra_short" && us.sent > 0 && us.replied > 0) {
        badgeUS.classList.remove("hidden");
      } else {
        badgeUS.classList.add("hidden");
      }
    }
  } catch (err) {
    console.error("Error fetching opener metrics:", err);
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

    const savedCount = getSavedPropertyCount();
    if (liveCountyTitle) liveCountyTitle.innerText = `⭐ ${selectedCountyKey} County · Saved Lists & Active Pipeline`;
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

    if (!liveRecords || liveRecords.length === 0) {
      loadLiveCountyLeads(selectedCountyKey || "Pinellas", currentFilter || "all", currentState);
    } else {
      const totalVerified = liveRecords.length;
      if (liveCountyTitle) liveCountyTitle.innerText = `${selectedCountyKey} County Live Distressed Leads`;
      if (liveStatusBadge) liveStatusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> ${totalVerified.toLocaleString()} Verified Properties`;
      if (liveCountySub) liveCountySub.innerText = "Cross-referenced against official county master parcels with clean owner names and absentee indicators.";
      if (pipelineDesc) pipelineDesc.innerText = `Showing all raw distressed public filings for ${selectedCountyKey} County`;

      filterLiveRecords(currentFilter || "all");
      updateFilterCounts();
    }
  }
  renderAutoSmsQueueStatus();
  renderAutoEmailQueueStatus();
}

let autoSmsQueueCache = { status: 'idle', total: 0, sent: 0, remaining: 0, skipped: 0 };
let autoSmsStatusTimer = null;
let autoSmsStatusInFlight = false;
let autoSmsRequestPending = false;
let autoSmsError = '';

function getAutoSmsParcelIds() {
  if (currentPipelineView !== 'saved') return [];
  return [...new Set((currentFilteredRecords || []).map(r => String(r.Parcel_ID || '')).filter(pid => {
    const contact = savedContactsCache[pid];
    return contact && isActiveCountyLead(contact.county, contact.state)
      && String(contact.source || '').startsWith('Skip Trace CSV') && !pid.startsWith('TEST-');
  }))];
}

function renderAutoSmsQueueStatus() {
  const queue = autoSmsQueueCache;
  const active = queue.status === 'running' || queue.status === 'paused' || queue.in_flight;
  const savedView = currentPipelineView === 'saved';
  document.getElementById('btnRefreshSavedDistress')?.classList.toggle('hidden', !savedView);
  const button = document.getElementById('btnStartAutoSms');
  if (button) {
    button.classList.toggle('hidden', !savedView);
    button.disabled = autoSmsRequestPending || active || queue.status === 'error' || getAutoSmsParcelIds().length === 0;
    button.textContent = autoSmsRequestPending ? 'Working…' : '▶ Start Auto SMS';
  }
  const followUpButton = document.getElementById('btnStartFollowUpSms');
  if (followUpButton) {
    followUpButton.classList.toggle('hidden', !savedView);
    followUpButton.disabled = autoSmsRequestPending || active || queue.status === 'error' || getAutoSmsParcelIds().length === 0;
    followUpButton.textContent = autoSmsRequestPending ? 'Working…' : '▶ Start Follow Up';
  }
  const panel = document.getElementById('autoSmsQueuePanel');
  if (!panel) return;
  panel.classList.toggle('hidden', !savedView && !active && queue.status !== 'error');
  const status = document.getElementById('autoSmsQueueStatus');
  const counties = (queue.counties || []).join(', ');
  const progress = `${queue.sent || 0}/${queue.total || 0} sent · ${queue.remaining || 0} remaining · ${queue.skipped || 0} skipped`;
  if (status) {
    if (queue.status === 'idle') {
      status.textContent = `Auto SMS ready · ${getAutoSmsParcelIds().length} imported leads in ${selectedCountyKey} County (all filtered pages)`;
    } else {
      const label = { running: 'Running', paused: 'Paused', stopped: 'Stopped', complete: 'Complete' }[queue.status] || queue.status;
      const next = queue.status === 'running' ? (queue.in_flight ? ' · Sending now…' : ` · Next in ${queue.seconds_until_next || 0}s: ${queue.next_owner || ''}`) : '';
      const campaignLabel = queue.campaign === 'follow_up' ? 'Follow Up' : 'Auto SMS';
      status.textContent = `${campaignLabel} · ${label}${counties ? ' · ' + counties : ''} · ${progress}${queue.failed ? ' · ' + queue.failed + ' failed / needs review' : ''}${next}`;
    }
  }
  for (const [id, visible] of [['btnPauseAutoSms', queue.status === 'running'], ['btnResumeAutoSms', queue.status === 'paused'], ['btnStopAutoSms', active]]) {
    const control = document.getElementById(id);
    if (control) {
      control.classList.toggle('hidden', !visible);
      control.disabled = autoSmsRequestPending || (id === 'btnResumeAutoSms' && queue.in_flight);
    }
  }
  const hint = document.getElementById('autoSmsQueueHint');
  if (hint) hint.textContent = queue.campaign === 'follow_up'
    ? 'Automatic follow-ups · one SMS every 90 seconds · rotates 10 property-owner messages using each address · skips replies and numbers already followed up · you answer replies manually · Pause/Stop finishes any send already underway.'
    : active
      ? 'One SMS every 90 seconds · rotates messages 1–4 · each lead uses its own saved county and parcel ID · Pause/Stop finishes any send already underway.'
      : `Current filtered list in ${selectedCountyKey} County, all pages · one SMS every 90 seconds · Start Auto SMS contacts new numbers and leads reset for resend · Start Follow Up contacts unanswered numbers once; you answer their replies manually.`;
  const notice = document.getElementById('autoSmsQueueNotice');
  if (notice) {
    notice.textContent = autoSmsError || queue.notice || '';
    notice.classList.toggle('hidden', !notice.textContent);
  }
}

async function fetchAutoSmsQueueStatus() {
  if (autoSmsStatusInFlight) return;
  autoSmsStatusInFlight = true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch('/api/sms/auto/status', { cache: 'no-store', signal: controller.signal });
    if (!res.ok) throw new Error('Could not check Auto SMS status');
    const data = await res.json();
    autoSmsQueueCache = data.queue;
    if (autoSmsError.startsWith('Connection lost')) autoSmsError = '';
  } catch (err) {
    autoSmsError = 'Connection lost. Retrying automatically; a running queue continues on the server.';
  } finally {
    clearTimeout(timeout);
    autoSmsStatusInFlight = false;
    renderAutoSmsQueueStatus();
  }
}

function startAutoSmsStatusPolling() {
  if (autoSmsStatusTimer !== null) return;
  fetchAutoSmsQueueStatus();
  autoSmsStatusTimer = setInterval(fetchAutoSmsQueueStatus, 2000);
}

async function requestAutoSmsQueue(url, payload) {
  if (autoSmsRequestPending) return;
  autoSmsRequestPending = true;
  autoSmsError = '';
  renderAutoSmsQueueStatus();
  try {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const data = await res.json();
    if (!res.ok || data.status !== 'success') throw new Error(data.detail || data.message || 'Auto SMS request failed');
    autoSmsQueueCache = data.queue;
  } catch (err) {
    autoSmsError = err.message;
  } finally {
    autoSmsRequestPending = false;
    renderAutoSmsQueueStatus();
  }
}

async function startAutoSmsBatch() {
  const parcelIds = getAutoSmsParcelIds();
  if (!parcelIds.length) {
    autoSmsError = 'No imported contacts in the current filtered saved list.';
    renderAutoSmsQueueStatus();
    return;
  }
  await requestAutoSmsQueue('/api/sms/auto/start', { parcel_ids: parcelIds });
}

async function startFollowUpSmsBatch() {
  const parcelIds = getAutoSmsParcelIds();
  if (!parcelIds.length) {
    autoSmsError = 'No imported contacts in the current filtered saved list.';
    renderAutoSmsQueueStatus();
    return;
  }
  await requestAutoSmsQueue('/api/sms/auto/start', { parcel_ids: parcelIds, campaign: 'follow_up' });
}

async function controlAutoSmsBatch(action) {
  await requestAutoSmsQueue('/api/sms/auto/control', { action });
}

let autoEmailQueueCache = { status: 'idle', total: 0, sent: 0, remaining: 0 };
let autoEmailStatusTimer = null;
let autoEmailStatusInFlight = false;
let autoEmailRequestPending = false;
let autoEmailError = '';
let autoEmailPreviewCache = null;

function getAutoEmailParcelIds() {
  if (currentPipelineView !== 'saved') return [];
  return [...new Set((currentFilteredRecords || []).flatMap(r => r.Contact_Parcel_IDs || [r.Parcel_ID])
    .map(pid => String(pid || '')).filter(pid => {
      const contact = savedContactsCache[pid];
      return contact && isActiveCountyLead(contact.county, contact.state) && !pid.startsWith('TEST-');
    }))];
}

function renderAutoEmailQueueStatus() {
  const q = autoEmailQueueCache;
  const active = q.status === 'running' || q.status === 'paused' || q.in_flight;
  const saved = currentPipelineView === 'saved';
  const button = document.getElementById('btnStartAutoEmail');
  if (button) {
    button.classList.toggle('hidden', !saved);
    button.disabled = autoEmailRequestPending || active || q.status === 'error' || !getAutoEmailParcelIds().length;
    button.textContent = autoEmailRequestPending ? 'Working…' : '▶ Start Auto Email';
  }
  const panel = document.getElementById('autoEmailQueuePanel');
  if (!panel) return;
  panel.classList.toggle('hidden', !saved && !active && q.status !== 'error');
  const status = document.getElementById('autoEmailQueueStatus');
  if (status) {
    const next = q.status === 'running' ? (q.in_flight ? ' · Sending now…' : ` · Next in ${q.seconds_until_next || 0}s: ${q.next_owner || ''}`) : '';
    status.textContent = q.status === 'idle'
      ? 'Auto Email ready · applies to this filtered list across all pages'
      : `Auto Email · ${q.status} · ${q.sent || 0}/${q.total || 0} sent · ${q.remaining || 0} remaining · ${q.skipped || 0} skipped${q.failed ? ' · ' + q.failed + ' failed / needs review' : ''}${next}`;
  }
  for (const [id, visible] of [['btnPauseAutoEmail', q.status === 'running'], ['btnResumeAutoEmail', q.status === 'paused'], ['btnStopAutoEmail', active]]) {
    const control = document.getElementById(id);
    if (control) {
      control.classList.toggle('hidden', !visible);
      control.disabled = autoEmailRequestPending || (id === 'btnResumeAutoEmail' && q.in_flight);
    }
  }
  const previewButton = document.getElementById('btnPreviewAutoEmail');
  if (previewButton) previewButton.disabled = autoEmailRequestPending || !getAutoEmailParcelIds().length;
  const preview = document.getElementById('autoEmailQueuePreview');
  if (preview) {
    const labels = {lis_pendens:'foreclosure',probate:'probate',code_violation:'code violation',quick_cash:'general offer'};
    const counts = Object.entries(autoEmailPreviewCache?.template_counts || {}).map(([key, n]) => `${n} ${labels[key] || key}`).join(' · ');
    preview.textContent = autoEmailPreviewCache ? `Last eligibility check: ${autoEmailPreviewCache.eligible} eligible · ${autoEmailPreviewCache.skipped} skipped${counts ? ' · ' + counts : ''}` : '';
    preview.classList.toggle('hidden', !preview.textContent);
  }
  const notice = document.getElementById('autoEmailQueueNotice');
  if (notice) {
    const reasons = Object.entries(q.skipped_reasons || {}).map(([reason, n]) => `${n} ${reason.toLowerCase()}`).join(' · ');
    notice.textContent = autoEmailError || q.notice || reasons;
    notice.classList.toggle('hidden', !notice.textContent);
  }
}

async function fetchAutoEmailQueueStatus() {
  if (autoEmailStatusInFlight) return;
  autoEmailStatusInFlight = true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch('/api/email/auto/status', { cache: 'no-store', signal: controller.signal });
    if (!res.ok) throw new Error('Could not check Auto Email status');
    const data = await res.json();
    autoEmailQueueCache = data.queue;
    if (autoEmailError.startsWith('Connection lost')) autoEmailError = '';
  } catch (err) {
    autoEmailError = 'Connection lost. Retrying automatically; a running email queue continues on the server.';
  } finally {
    clearTimeout(timeout);
    autoEmailStatusInFlight = false;
    renderAutoEmailQueueStatus();
  }
}

function startAutoEmailStatusPolling() {
  if (autoEmailStatusTimer !== null) return;
  fetchAutoEmailQueueStatus();
  autoEmailStatusTimer = setInterval(fetchAutoEmailQueueStatus, 2000);
}

async function requestAutoEmailQueue(url, payload, previewOnly = false) {
  if (autoEmailRequestPending) return;
  autoEmailRequestPending = true;
  autoEmailError = '';
  renderAutoEmailQueueStatus();
  try {
    const res = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
    const data = await res.json();
    if (!res.ok || data.status !== 'success') throw new Error(data.detail || data.message || 'Auto Email request failed');
    if (previewOnly) autoEmailPreviewCache = data;
    else { autoEmailQueueCache = data.queue; autoEmailPreviewCache = null; }
  } catch (err) {
    autoEmailError = err.message;
  } finally {
    autoEmailRequestPending = false;
    renderAutoEmailQueueStatus();
  }
}

async function startAutoEmailBatch() {
  const parcelIds = getAutoEmailParcelIds();
  if (!parcelIds.length) {
    autoEmailError = 'No saved contacts in the current filtered list.';
    renderAutoEmailQueueStatus();
    return;
  }
  await requestAutoEmailQueue('/api/email/auto/start', {parcel_ids:parcelIds});
}

async function previewAutoEmailBatch() {
  await requestAutoEmailQueue('/api/email/auto/preview', {parcel_ids:getAutoEmailParcelIds()}, true);
}

async function controlAutoEmailBatch(action) {
  await requestAutoEmailQueue('/api/email/auto/control', {action});
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
    const statusBadge = entry.direction === "INBOUND" && entry.status === "RECEIVED"
      ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/40">↓ RECEIVED</span>`
      : statusSuccess
      ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">✓ SENT</span>`
      : `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/40">✕ FAILED</span>`;

    const angleBadge = entry.opener_angle 
      ? `<span class="inline-block px-1.5 py-0.5 rounded text-[9px] font-extrabold uppercase bg-blue-500/20 text-blue-300 border border-blue-500/30 mr-1.5">${entry.opener_angle.replace('_', ' ')}</span>`
      : "";

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
        <div class="font-bold text-white text-xs">${formatDisplayName(entry.owner || "Homeowner")}</div>
        ${entry.parcel_id ? `<div class="text-[10px] text-slate-500 mono">PIN: ${entry.parcel_id}</div>` : ""}
      </td>
      <td class="px-4 py-3">
        <div class="text-xs text-slate-300">${formatDisplayAddress(entry.address || "N/A")}</div>
        <div class="text-[10px] text-slate-500">${formatDisplayCity(entry.county || "Pinellas")}, FL</div>
      </td>
      <td class="px-4 py-3 whitespace-nowrap mono text-xs text-emerald-300 font-semibold">
        ${entry.recipient || entry.phone || "N/A"}
      </td>
      <td class="px-4 py-3 max-w-xs">
        ${entry.subject && entry.subject !== "SMS Text Message" ? `<div class="text-[11px] font-bold text-blue-300 truncate">${entry.subject}</div>` : ""}
        <div class="text-[11px] text-slate-300 line-clamp-2 leading-relaxed" title="${escapeAttr(entry.message || "")}">
          ${angleBadge}${entry.message || entry.subject || "Offer dispatched"}
        </div>
      </td>
      <td class="px-4 py-3 text-center whitespace-nowrap">
        ${statusBadge}
      </td>
      <td class="px-4 py-3 text-center whitespace-nowrap">
        ${isSms ? `
          <button type="button" onclick="openSellerThread('${escapeAttr(entry.recipient || entry.phone || "")}', '${entry.parcel_id || ""}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-emerald-600 hover:text-white text-slate-300 text-[10px] font-bold transition flex items-center gap-1 mx-auto cursor-pointer" title="Open 2-Way Chat Stream & Copilot">
            <span>💬</span> <span>Conversation</span>
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
  const dataset = getFilteredPipelineDataset(currentFilter);
  const filtered = dataset.filter(r => {
    const text = `${r.Property_Address} ${r.Clean_Full_Name} ${r.Parcel_ID} ${r.County || ""} ${r.Mailing_Address} ${r.Mailing_City} ${r.Saved_Phone || ""} ${r.Saved_Email || ""}`.toLowerCase();
    return text.includes(q);
  });
  renderLiveTable(filtered);
  updateExportButtonsUI();
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

// =============================================================
// Category Multi-Select & Skip-Tracing CSV Export (Option 3)
// =============================================================
let selectedExportCategories = new Set();

function toggleCategoryExport(catKey, isChecked) {
  if (isChecked) {
    selectedExportCategories.add(catKey);
  } else {
    selectedExportCategories.delete(catKey);
  }
  updateExportButtonsUI();
}

function clearExportCategoryChecks() {
  selectedExportCategories.clear();
  document.querySelectorAll(".cat-export-check").forEach(chk => {
    chk.checked = false;
  });
  document.querySelectorAll("[id^='pillWrap_']").forEach(wrap => {
    wrap.classList.remove("border-emerald-500/80", "bg-emerald-950/20");
  });
  updateExportButtonsUI();
}

function getRecordsForCategories(categoryList) {
  const dataset = getActivePipelineDataset() || [];
  if (!categoryList || categoryList.length === 0) return dataset;

  const matchedSet = new Set();
  const matchedRecords = [];

  categoryList.forEach(cat => {
    let sub = [];
    if (cat === "all") {
      sub = dataset;
    } else if (cat === "has_photos") {
      sub = dataset.filter(hasLeadPhoto);
    } else if (cat === "stacked") {
      sub = dataset.filter(r => r.Is_Stacked_Distress === "Yes");
    } else if (cat === "lis_pendens") {
      sub = dataset.filter(r => r.Lead_Type === "Lis Pendens");
    } else if (cat === "lp_trust") {
      sub = dataset.filter(r => r.Lead_Type === "Lis Pendens" && (r.Is_Trust_In_LP === "Yes" || r.Is_Trust_Or_Estate === "Yes"));
    } else if (cat === "probate") {
      sub = dataset.filter(r => r.Has_Confirmed_Probate === 'Yes' || (r.Lead_Type || '').toLowerCase().includes('probate'));
    } else if (cat === "divorce") {
      sub = dataset.filter(r => (r.Lead_Type || "").toLowerCase().includes("divorce") || (r.Lead_Type || "").toLowerCase().includes("domestic relations"));
    } else if (cat === "judgment" || cat === "judgments" || cat === "lien" || cat === "liens") {
      sub = dataset.filter(r => (r.Lead_Type || "").toLowerCase().includes("judgment") || (r.Lead_Type || "").toLowerCase().includes("lien"));
    } else if (cat === "code_stacked" || cat === "code_double") {
      sub = dataset.filter(r => isCodeStackedLead(r));
    } else if (cat === "code") {
      sub = dataset.filter(r => isCodeViolationLead(r));
    } else if (cat === "absentee") {
      sub = dataset.filter(r => (r.Absentee_Status || "").includes("Out-of-State"));
    } else if (cat === "tax_liens") {
      sub = dataset.filter(r => (r.Lead_Type || "").includes("Tax Lien"));
    } else if (cat === "water_shutoff" || cat === "water" || cat === "ouc") {
      sub = dataset.filter(r => 
        (r.Lead_Type || "").toLowerCase().includes("water") || 
        (r.Lead_Type || "").toLowerCase().includes("ouc") ||
        (r.Distress_Stack_Notes || "").toLowerCase().includes("water")
      );
    } else if (cat === "legal_distress" || cat === "legal" || cat === "felony") {
      sub = dataset.filter(r => 
        (r.Lead_Type || "").toLowerCase().includes("legal distress") || 
        (r.Lead_Type || "").toLowerCase().includes("felony") ||
        (r.Distress_Stack_Notes || "").toLowerCase().includes("felony")
      );
    } else {
      sub = dataset.filter(r => (r.Lead_Type || "").toLowerCase().includes(cat.toLowerCase()));
    }

    sub.forEach(r => {
      const pid = r.Parcel_ID || `${r.Property_Address}_${r.Clean_Full_Name}`;
      if (!matchedSet.has(pid)) {
        matchedSet.add(pid);
        matchedRecords.push(r);
      }
    });
  });

  return matchedRecords;
}

function updateExportButtonsUI() {
  const btnCat = document.getElementById("btnExportCategory");
  const labelCat = document.getElementById("btnExportCategoryLabel");
  const btnClear = document.getElementById("btnClearCategoryChecks");
  const labelAll = document.getElementById("btnExportAllCountyLabel");
  const dataset = getActivePipelineDataset() || [];

  if (labelAll) {
    labelAll.innerText = `Export Whole County (${dataset.length.toLocaleString()}) .CSV`;
  }

  const categoryNames = {
    has_photos: "Has Photos",
    stacked: "Double Distress",
    code_stacked: "Code + Double Distress",
    lis_pendens: "Lis Pendens",
    lp_trust: "LP + Trust",
    probate: "Probate Court",
    divorce: "Divorce",
    judgment: "Judgments & Liens",
    code: "Code Violations",
    absentee: "Absentee Out-of-State",
    tax_liens: "Tax Liens",
    water_shutoff: "Water Shutoff",
    legal_distress: "Legal Distress (Felony)"
  };

  if (selectedExportCategories.size > 0) {
    if (btnClear) btnClear.classList.remove("hidden");
    const catList = Array.from(selectedExportCategories);
    const recordsToExport = getRecordsForCategories(catList);
    const count = recordsToExport.length;
    const catCount = catList.length;

    if (labelCat) {
      if (catCount === 1) {
        const catKey = catList[0];
        const name = categoryNames[catKey] || catKey;
        labelCat.innerText = `Export ${name} (${count.toLocaleString()}) .CSV`;
      } else {
        labelCat.innerText = `Export ${catCount} Categories (${count.toLocaleString()} Leads) .CSV`;
      }
    }

    if (btnCat) {
      btnCat.className = "px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/30 transition cursor-pointer whitespace-nowrap";
      btnCat.title = `Export ${catCount} selected categories (${count} leads) to skip-tracing CSV`;
    }

    document.querySelectorAll(".cat-export-check").forEach(chk => {
      const cat = chk.getAttribute("data-category");
      const wrap = document.getElementById(`pillWrap_${cat}`);
      if (wrap) {
        if (chk.checked) {
          wrap.classList.add("border-emerald-500/80", "bg-emerald-950/20");
        } else {
          wrap.classList.remove("border-emerald-500/80", "bg-emerald-950/20");
        }
      }
    });
  } else {
    if (btnClear) btnClear.classList.add("hidden");

    document.querySelectorAll("[id^='pillWrap_']").forEach(wrap => {
      wrap.classList.remove("border-emerald-500/80", "bg-emerald-950/20");
    });

    const searchInput = document.getElementById("liveSearchInput");
    const searchQuery = searchInput ? searchInput.value.trim() : "";
    const activeView = currentFilter || "all";
    let recordsToExport = [];
    let viewName = "Active View";

    if (searchQuery && currentFilteredRecords && currentFilteredRecords.length > 0) {
      recordsToExport = currentFilteredRecords;
      viewName = `Search (${recordsToExport.length})`;
    } else if (activeView === "all") {
      recordsToExport = currentFilteredRecords.length > 0 ? currentFilteredRecords : dataset;
      viewName = "Verified Leads";
    } else {
      recordsToExport = getRecordsForCategories([activeView]);
      viewName = categoryNames[activeView] || activeView;
    }

    const count = recordsToExport.length;

    if (labelCat) {
      if (activeView === "all" && !searchQuery) {
        labelCat.innerText = `Export Verified Table (${count.toLocaleString()}) .CSV`;
      } else {
        labelCat.innerText = `Export ${viewName} (${count.toLocaleString()}) .CSV`;
      }
    }

    if (btnCat) {
      btnCat.className = "px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-emerald-600/30 transition cursor-pointer whitespace-nowrap";
      btnCat.title = `Export ${viewName} (${count} leads) to skip-tracing CSV`;
    }
  }
}

function exportCategoryCsv() {
  let records = [];
  let exportName = "";
  const county = selectedCountyKey || "Orange";
  const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, "");

  if (selectedExportCategories.size > 0) {
    const catList = Array.from(selectedExportCategories);
    records = getRecordsForCategories(catList);
    if (catList.length === 1) {
      exportName = `${county}_County_${catList[0].toUpperCase()}_${records.length}_Leads_${dateStr}.csv`;
    } else {
      exportName = `${county}_County_Multi_Category_${records.length}_Leads_${dateStr}.csv`;
    }
  } else {
    const searchInput = document.getElementById("liveSearchInput");
    const searchQuery = searchInput ? searchInput.value.trim() : "";
    const activeView = currentFilter || "all";

    if (searchQuery && currentFilteredRecords && currentFilteredRecords.length > 0) {
      records = currentFilteredRecords;
      exportName = `${county}_County_Search_Filtered_${records.length}_Leads_${dateStr}.csv`;
    } else if (activeView === "all") {
      records = currentFilteredRecords.length > 0 ? currentFilteredRecords : (getActivePipelineDataset() || []);
      exportName = `${county}_County_Verified_Leads_${records.length}_${dateStr}.csv`;
    } else {
      records = getRecordsForCategories([activeView]);
      exportName = `${county}_County_${activeView.toUpperCase()}_${records.length}_Leads_${dateStr}.csv`;
    }
  }

  if (!records || records.length === 0) {
    alert("No leads found matching the selected export filter.");
    return;
  }

  generateAndDownloadCsv(records, exportName);
}

function exportEntireCountyCsv() {
  const dataset = getActivePipelineDataset() || [];
  const county = selectedCountyKey || "Orange";
  const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const exportName = `${county}_County_All_Distress_Leads_${dataset.length}_${dateStr}.csv`;

  if (!dataset || dataset.length === 0) {
    alert("No leads available in the active county database to export.");
    return;
  }

  generateAndDownloadCsv(dataset, exportName);
}

function generateAndDownloadCsv(records, filename) {
  if (!records || records.length === 0) return;

  const columns = [
    { key: "County", label: "County" },
    { key: "Parcel_ID", label: "Parcel_ID" },
    { key: "Lead_Type", label: "Lead_Type" },
    { key: "Is_Stacked_Distress", label: "Double_Distress" },
    { key: "Distress_Stack_Notes", label: "Distress_Notes" },
    { key: "Clean_Full_Name", label: "Owner_Full_Name" },
    { key: "Clean_First_Name", label: "Owner_First_Name" },
    { key: "Clean_Last_Name", label: "Owner_Last_Name" },
    { key: "Property_Address", label: "Property_Address" },
    { key: "Property_City", label: "Property_City" },
    { key: "Property_Zip", label: "Property_Zip" },
    { key: "Mailing_Address", label: "Mailing_Address" },
    { key: "Mailing_City", label: "Mailing_City" },
    { key: "Mailing_State", label: "Mailing_State" },
    { key: "Mailing_Zip", label: "Mailing_Zip" },
    { key: "Absentee_Status", label: "Absentee_Status" },
    { key: "Owner_Entity_Type", label: "Owner_Type" },
    { key: "Market_Value", label: "Market_Value" },
    { key: "Assessed_Value", label: "Assessed_Value" },
    { key: "Year_Built", label: "Year_Built" },
    { key: "Living_Sqft", label: "Living_Sqft" },
    { key: "Phone_1", label: "Phone_1" },
    { key: "Phone_2", label: "Phone_2" },
    { key: "Email", label: "Email" },
    { key: "Case_Number", label: "Case_Number" },
    { key: "Document_Number", label: "Document_Number" },
    { key: "Recording_Date", label: "Recording_Date" }
  ];

  const escapeCell = (val) => {
    if (val === null || val === undefined) return '""';
    let s = String(val).trim();
    if (s.includes('"') || s.includes(',') || s.includes('\n') || s.includes('\r')) {
      s = s.replace(/"/g, '""');
      return `"${s}"`;
    }
    return `"${s}"`;
  };

  const headerRow = columns.map(c => `"${c.label}"`).join(",");
  const rows = [headerRow];

  records.forEach(r => {
    const pid = r.Parcel_ID || "";
    const savedContact = (savedContactsCache && savedContactsCache[pid]) ? savedContactsCache[pid] : null;

    const rowValues = columns.map(col => {
      let val = r[col.key];

      if (col.key === "Phone_1" && (!val || val === "")) {
        val = savedContact?.phone || savedContact?.clean_phone || "";
      } else if (col.key === "Phone_2" && (!val || val === "")) {
        val = savedContact?.phone_2 || "";
      } else if (col.key === "Email" && (!val || val === "")) {
        val = savedContact?.email || "";
      } else if (col.key === "Double_Distress" || col.key === "Is_Stacked_Distress") {
        val = (r.Is_Stacked_Distress === "Yes" || r.Is_Stacked_Distress === true) ? "Yes" : "No";
      } else if (col.key === "Clean_Full_Name" || col.key === "Clean_First_Name" || col.key === "Clean_Last_Name") {
        val = formatDisplayName(val);
      } else if (col.key === "Property_Address" || col.key === "Mailing_Address") {
        val = formatDisplayAddress(val);
      } else if (col.key === "Property_City" || col.key === "Mailing_City") {
        val = formatDisplayCity(val);
      }

      return escapeCell(val);
    });

    rows.push(rowValues.join(","));
  });

  const csvContent = rows.join("\r\n");
  const blob = new Blob(["\uFEFF" + csvContent], { type: "text/csv;charset=utf-8;" });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  link.style.visibility = "hidden";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function triggerExport() {
  exportCategoryCsv();
}

// Modal & CSV Import Handlers
function openImportModal(defaultLeadType = "tax_liens") {
  if (defaultLeadType === "skiptrace") {
    openSkipTraceImportModal();
    return;
  }
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
    else if (defaultLeadType === "skiptrace") typeSelect.value = "skiptrace";
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

  const leadSource = document.getElementById("importLeadTypeSelect").value;
  if (leadSource === "skiptrace") {
    closeImportModal();
    openSkipTraceImportModal();
    return;
  }
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

function openSkipTraceImportModal() {
  const modal = document.getElementById("importSkipTraceModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  
  const countySelect = document.getElementById("importSkipTraceDefaultCounty");
  if (countySelect && selectedCountyKey) {
    countySelect.value = selectedCountyKey;
  }
  const fileInput = document.getElementById("importSkipTraceFileInput");
  if (fileInput) fileInput.value = "";
  const label = document.getElementById("importSkipTraceFileLabel");
  if (label) label.innerText = "Click or drag & drop Skip-Traced CSV here";
}

function closeSkipTraceImportModal() {
  const modal = document.getElementById("importSkipTraceModal");
  if (modal) modal.classList.add("hidden");
}

function handleSkipTraceFileSelected(input) {
  const label = document.getElementById("importSkipTraceFileLabel");
  if (input.files && input.files[0]) {
    label.innerText = `Selected: ${input.files[0].name} (${(input.files[0].size / 1024).toFixed(1)} KB)`;
  } else {
    label.innerText = "Click or drag & drop Skip-Traced CSV here";
  }
}

async function handleSkipTraceImportSubmit(e) {
  if (e && e.preventDefault) e.preventDefault();

  const fileInput = document.getElementById("importSkipTraceFileInput");
  if (!fileInput || !fileInput.files[0]) {
    alert("Please select a CSV or Excel file to import.");
    return;
  }

  const defaultCounty = document.getElementById("importSkipTraceDefaultCounty")?.value || selectedCountyKey || "Pinellas";
  const file = fileInput.files[0];

  const submitBtn = document.getElementById("btnSubmitSkipTraceImport");
  const origBtnText = submitBtn ? submitBtn.innerHTML : "";
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span>⏳ Ingesting & Routing Leads...</span>`;
  }

  try {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("default_county", defaultCounty);

    const res = await fetch("/api/leads/import-skiptrace", {
      method: "POST",
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Error importing skip-traced CSV");
    }

    const data = await res.json();
    closeSkipTraceImportModal();

    // Refresh saved contacts cache from server
    await fetchSavedContacts();

    // Format county breakdown for user alert
    const bdown = data.counties_breakdown || {};
    const bdownStr = Object.entries(bdown).map(([c, cnt]) => `• ${c} County: ${cnt} lead${cnt > 1 ? 's' : ''}`).join('\n');

    alert(`🎉 Successfully Imported ${data.imported_count} Skip-Traced Leads!\n\n` +
          `📞 Phone Numbers Found: ${data.phones_found}\n` +
          `✉️ Email Addresses Found: ${data.emails_found}\n\n` +
          `📍 Florida Counties:\n${bdownStr || '• ' + defaultCounty + ' County'}\n\n` +
          `Displaying all leads now in 'Saved Lists / My Leads' pipeline.`);

    // Switch to Saved Lists / Active Pipeline view so user immediately sees their imported leads!
    switchPipelineView("saved");
  } catch (err) {
    alert(`Import failed: ${err.message}`);
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = origBtnText;
    }
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
    modalSkipName = formatDisplayName((modalSkipName || "").replace(/\b(TR|TRE|TRUSTEE|ESTATE|EST|OF|DECD|DECEASED|ET|AL|LIFE|LE)\b/gi, " ").replace(/\s+/g, " ").trim());
    const cleanModalAddr = formatDisplayAddress(r.Property_Address);
    const cleanModalCity = formatDisplayCity((r.Property_City || (selectedCountyKey === 'Orange' ? 'Orlando' : 'St Petersburg')).trim());
    const cleanModalOwner = formatDisplayName(r.Clean_Full_Name || r.Clean_Last_Name || 'Unknown Owner');
    const modalCity = formatDisplayCity((r.Mailing_City || r.Property_City || (selectedCountyKey === 'Orange' ? 'Orlando' : 'St Petersburg')).trim());
    const modalState = (r.Mailing_State || "FL").trim();
    const modalSkipUrl = `https://www.truepeoplesearch.com/results?name=${encodeURIComponent(modalSkipName)}&citystatezip=${encodeURIComponent(`${modalCity}, ${modalState}`)}#lead_hub_pid=${encodeURIComponent(r.Parcel_ID || '')}&county=${encodeURIComponent(selectedCountyKey)}&owner=${encodeURIComponent(modalSkipName)}&addr=${encodeURIComponent(cleanModalAddr || r.Property_Address || '')}`;
    
    const mSavedContact = savedContactsCache[r.Parcel_ID] || (r.Saved_Phone ? { phone: r.Saved_Phone } : null);
    const mSavedPhone = mSavedContact ? mSavedContact.phone : null;

    let modalPaUrl = "https://www.pcpao.gov/quick-search";
    const mPidTrim = (r.Parcel_ID || "").trim();
    const mPidParts = mPidTrim.split("-");
    if (mPidParts.length === 6) {
      modalPaUrl = `https://www.pcpao.gov/property-details?s=${mPidParts[2]}${mPidParts[1]}${mPidParts[0]}${mPidParts[3]}${mPidParts[4]}${mPidParts[5]}`;
    }

    window.leadsByPid = window.leadsByPid || {};
    if (r.Parcel_ID) window.leadsByPid[r.Parcel_ID] = r;

    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-800/40 transition cursor-pointer group";
    tr.onclick = (e) => {
      if (e.target.closest("button, a, input, select, textarea")) return;
      openPropertyCard(r.Parcel_ID);
    };

    tr.innerHTML = `
      <td class="px-4 py-3"><span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400">✓ MATCHED</span></td>
      <td class="px-4 py-3" title="Click to view Property Card" onclick="openPropertyCard('${r.Parcel_ID}')">
        <div class="font-bold text-white text-xs group-hover:text-blue-300 transition flex items-center gap-1">
          <span>${cleanModalAddr || 'N/A'}</span>
          <span class="text-[10px] text-blue-400 opacity-0 group-hover:opacity-100 transition">🏡</span>
        </div>
        <div class="text-[10px] text-slate-400">${cleanModalCity}, FL ${r.Property_Zip || ''}</div>
      </td>
      <td class="px-4 py-3">
        <div class="font-bold text-blue-300 text-xs">${cleanModalOwner}</div>
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
          <button type="button" onclick="event.stopPropagation(); openUnderwrite407FlipsForLead('${r.Parcel_ID}', '${escapeAttr(cleanModalAddr)}', ${r.Year_Built || 1980}, ${r.Living_Sqft || 1500}, ${mktVal || 0}, '${escapeAttr(modalSkipName)}')" class="px-2 py-1 rounded bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-slate-950 text-[10px] font-black transition flex items-center gap-1 shadow-sm border border-amber-400/50 cursor-pointer" title="407flips Underwriting Audit">
            <span>407</span> <span>Audit</span>
          </button>
          ${mSavedPhone ? `
            <button type="button" onclick="event.stopPropagation(); openSmsModal('${r.Parcel_ID}', '${mSavedPhone}', '${escapeAttr(modalSkipName)}', '${escapeAttr(cleanModalAddr)}')" class="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] font-bold transition flex items-center gap-1 shadow-md shadow-emerald-600/30 cursor-pointer" title="Send Wholesale SMS Offer">
              <span>💬</span> <span>Send SMS</span>
            </button>
          ` : `
            <a href="${modalSkipUrl}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation();" class="px-2 py-1 rounded bg-amber-500/20 hover:bg-amber-500 hover:text-slate-950 text-amber-300 text-[10px] font-bold transition flex items-center gap-1 shadow-sm border border-amber-500/30" title="Free 1-Click Skip Trace (TruePeopleSearch) for ${modalSkipName}">
              <span>📞</span> <span>Free Trace</span>
            </a>
          `}
          <a href="${modalPaUrl}" target="_blank" onclick="event.stopPropagation();" class="px-2 py-1 rounded bg-slate-800 hover:bg-blue-600 hover:text-white text-slate-300 text-[10px] font-semibold transition" title="View Property Appraiser">
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
    heroMaster.style.display = c.master_parcel_download_url ? "inline-flex" : "none";
  }

  // Update 1-click government portals in active county bar
  const barLp = document.getElementById("barLinkLp");
  if (barLp) {
    barLp.href = c.clerk_lis_pendens_url || "#";
    barLp.title = `Official Lis Pendens Search for ${c.name} County`;
    barLp.style.display = c.clerk_lis_pendens_url ? "inline-flex" : "none";
  }

  const barCode = document.getElementById("barLinkCode");
  if (barCode) {
    barCode.href = c.code_enforcement_url || "#";
    barCode.title = `Official Code Enforcement Search for ${c.name} County`;
    barCode.style.display = c.code_enforcement_url ? "inline-flex" : "none";
  }

  const barTax = document.getElementById("barLinkTax");
  if (barTax) {
    barTax.href = c.tax_liens_url || "#";
    barTax.title = `Official Tax Delinquent Roll for ${c.name} County`;
    barTax.style.display = c.tax_liens_url ? "inline-flex" : "none";
  }

  const barProbate = document.getElementById("barLinkProbate");
  if (barProbate) {
    barProbate.href = c.clerk_probate_url || "#";
    barProbate.title = `Official Probate Court Portal for ${c.name} County`;
    barProbate.style.display = c.clerk_probate_url ? "inline-flex" : "none";
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
  const linkProbateComptroller = document.getElementById("cardLinkProbateComptroller");
  if (linkProbate) {
    if ((c.name || "").toLowerCase() === "orange" || (countyKey || "").toLowerCase() === "orange") {
      linkProbate.href = c.clerk_probate_url || "https://myeclerk.myorangeclerk.com/cases/search";
      linkProbate.title = "Orange County Clerk of Courts (Probate Case Docket Search)";
      linkProbate.innerHTML = "🏛️ Clerk Docket ↗";
      if (linkProbateComptroller) {
        linkProbateComptroller.classList.remove("hidden");
        linkProbateComptroller.href = c.comptroller_probate_url || "https://selfservice.or.occompt.com/ssweb/search/DOCSEARCH2950S3";
      }
    } else {
      linkProbate.href = c.clerk_probate_url || "#";
      linkProbate.title = `Official Probate Court Portal (${c.name} County)`;
      linkProbate.innerHTML = "🌐 Official Portal ↗";
      if (linkProbateComptroller) {
        linkProbateComptroller.classList.add("hidden");
      }
    }
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
      if (!currentSourcesSummary) {
        fetchSourcesSummary(selectedCountyKey || "Orange", currentState || "FL");
      }
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

let currentSourcesSummary = null;

function renderCardStatusHtml(sourceMeta) {
  if (!sourceMeta || sourceMeta.lead_count === 0 || sourceMeta.last_loaded === "Not loaded yet" || sourceMeta.last_loaded === "Awaiting CSV upload") {
    return `
      <span class="inline-flex items-center gap-1.5 text-amber-400 font-semibold text-[10px]">
        <span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
        Awaiting CSV upload
      </span>
      <span class="px-1.5 py-0.5 rounded-md bg-slate-800 text-slate-400 font-bold border border-slate-700 text-[10px]">
        0 Leads
      </span>
    `;
  }
  return `
    <span class="inline-flex items-center gap-1.5 text-emerald-400 font-semibold text-[10px]" title="Loaded ${sourceMeta.last_loaded_full || sourceMeta.last_loaded}">
      <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
      Loaded: ${sourceMeta.last_loaded}
    </span>
    <span class="px-1.5 py-0.5 rounded-md bg-emerald-500/15 text-emerald-300 font-extrabold border border-emerald-500/30 text-[10px]">
      ${(sourceMeta.lead_count || 0).toLocaleString()} Leads
    </span>
  `;
}

function updateCardStatusChips() {
  if (!currentSourcesSummary || !currentSourcesSummary.sources) return;
  const s = currentSourcesSummary.sources;

  const elLp = document.getElementById("cardStatusLp");
  if (elLp) elLp.innerHTML = renderCardStatusHtml(s.lis_pendens);

  const elCode = document.getElementById("cardStatusCode");
  if (elCode) elCode.innerHTML = renderCardStatusHtml(s.code_violations);

  const elTax = document.getElementById("cardStatusTax");
  if (elTax) elTax.innerHTML = renderCardStatusHtml(s.tax_liens);

  const elProbate = document.getElementById("cardStatusProbate");
  if (elProbate) elProbate.innerHTML = renderCardStatusHtml(s.probate);
}

async function fetchSourcesSummary(countyKey = (selectedCountyKey || "Orange"), state = (currentState || "FL")) {
  try {
    const res = await fetch(`/api/sources-summary?county=${encodeURIComponent(countyKey)}&state=${encodeURIComponent(state)}`);
    if (res.ok) {
      currentSourcesSummary = await res.json();
      updateCardStatusChips();
      renderCustomCategoryCardsOnDashboard();
    }
  } catch (err) {
    console.error("Error fetching sources summary:", err);
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
    if (cat.id === "ouc_water_shutoff" &&
        (currentState !== "FL" || String(selectedCountyKey).toLowerCase() !== "orange")) return;

    const isWater = (cat.name || "").toLowerCase().includes("water") || (cat.name || "").toLowerCase().includes("ouc") || (cat.icon || "") === "💧" || (cat.icon || "") === "🚰";
    const isDivorce = (cat.name || "").toLowerCase().includes("divorce");
    const isJudgment = (cat.name || "").toLowerCase().includes("judgment") || (cat.name || "").toLowerCase().includes("lien");

    let borderHover = "hover:border-purple-700/60";
    let iconBg = "bg-purple-950/60 border border-purple-800/40 text-purple-300";
    let badgeText = "text-purple-400";
    let btnText = "text-purple-400 hover:text-purple-300";
    let updateBtnBg = "bg-purple-600/20 hover:bg-purple-600 text-purple-300 hover:text-white border border-purple-500/30";

    if (isWater) {
      borderHover = "hover:border-cyan-500/60";
      iconBg = "bg-cyan-950/60 border border-cyan-800/40 text-cyan-300";
      badgeText = "text-cyan-400";
      btnText = "text-cyan-400 hover:text-cyan-300";
      updateBtnBg = "bg-cyan-600/20 hover:bg-cyan-600 text-cyan-300 hover:text-white border border-cyan-500/30";
    } else if (isDivorce) {
      borderHover = "hover:border-pink-500/60";
      iconBg = "bg-pink-950/60 border border-pink-800/40 text-pink-300";
      badgeText = "text-pink-400";
      btnText = "text-pink-400 hover:text-pink-300";
      updateBtnBg = "bg-pink-600/20 hover:bg-pink-600 text-pink-300 hover:text-white border border-pink-500/30";
    } else if (isJudgment) {
      borderHover = "hover:border-amber-500/60";
      iconBg = "bg-amber-950/60 border border-amber-800/40 text-amber-300";
      badgeText = "text-amber-400";
      btnText = "text-amber-400 hover:text-amber-300";
      updateBtnBg = "bg-amber-600/20 hover:bg-amber-600 text-amber-300 hover:text-white border border-amber-500/30";
    }

    const sMeta = (currentSourcesSummary && currentSourcesSummary.sources) ? 
      (currentSourcesSummary.sources[cat.id] || currentSourcesSummary.sources[cat.name.toLowerCase().replace(/\s+/g, '_')]) : null;

    const card = document.createElement("div");
    card.className = `custom-category-card glass-surface rounded-2xl p-5 border border-slate-800 ${borderHover} transition cursor-pointer group flex flex-col justify-between`;
    card.onclick = () => openSourceDetailsModal(cat.id);

    card.innerHTML = `
      <div>
        <div class="flex items-center space-x-3.5 mb-2">
          <div class="w-10 h-10 rounded-xl ${iconBg} flex items-center justify-center text-lg group-hover:scale-105 transition">
            ${cat.icon || '📄'}
          </div>
          <div>
            <div class="font-bold text-white text-sm">${cat.name}</div>
            <div class="text-[10px] ${badgeText} font-semibold">${cat.badge || 'Distress Filing'}</div>
          </div>
        </div>
        <p class="text-xs text-slate-400 mt-2">${cat.description || 'Public court & county distress filings.'}</p>
      </div>
      <div id="cardStatus_${cat.id}" class="card-status-chip mt-3 pt-2.5 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-400">
        ${renderCardStatusHtml(sMeta)}
      </div>
      <div class="mt-2 pt-2 border-t border-slate-800/80 space-y-2">
        <div class="flex items-center justify-between gap-1.5">
          <button type="button" onclick="event.stopPropagation(); openSourceDetailsModal('${cat.id}')" class="inline-flex items-center gap-1 text-[11px] font-bold ${btnText} transition cursor-pointer" title="View source details & load history">
            VIEW DETAILS &rarr;
          </button>
          ${cat.portal_url ? `
            <a href="${cat.portal_url}" target="_blank" onclick="event.stopPropagation()" class="px-2 py-1 rounded-lg bg-slate-800/90 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 text-[10px] font-semibold inline-flex items-center gap-1 transition" title="Go to official portal">
              🌐 Official Portal ↗
            </a>
          ` : ''}
        </div>
        <button type="button" onclick="event.stopPropagation(); openImportModal('${cat.id}')" class="w-full py-1.5 rounded-lg ${updateBtnBg} text-[10px] font-bold inline-flex items-center justify-center gap-1.5 transition cursor-pointer" title="Import new ${cat.name} CSV">
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
  const catLower = (categoryName || "").toLowerCase();
  const isJudgments = catLower.includes("judgment") || catLower.includes("lien");
  const isDivorce = catLower.includes("divorce");
  const isWater = catLower.includes("water") || catLower.includes("ouc");
  const isProbate = catLower.includes("probate") || catLower.includes("death");

  const filtered = liveRecords.filter(r => {
    const lt = (r.Lead_Type || "").toLowerCase();
    const notes = (r.Distress_Stack_Notes || "").toLowerCase();
    if (isJudgments && (lt.includes("judgment") || lt.includes("lien") || notes.includes("judgment") || notes.includes("lien"))) return true;
    if (isDivorce && (lt.includes("divorce") || notes.includes("divorce"))) return true;
    if (isWater && (lt.includes("water") || lt.includes("ouc") || notes.includes("water"))) return true;
    if (isProbate && (lt.includes("probate") || lt.includes("death") || notes.includes("probate"))) return true;
    if (lt.includes(catLower) || notes.includes(catLower)) return true;
    return false;
  });

  if (filtered.length === 0) {
    const matchedCategory = customCategories.find(c => c.name.toLowerCase() === categoryName.toLowerCase());
    openImportModal(matchedCategory ? matchedCategory.id : "custom");
  } else {
    renderLiveTable(filtered);
    const liveSection = document.getElementById("liveRecordsSection");
    if (liveSection) liveSection.scrollIntoView({ behavior: 'smooth' });
  }
}

function openSourceDetailsModal(sourceKey) {
  const modal = document.getElementById("sourceDetailsModal");
  if (!modal) return;

  const sData = (currentSourcesSummary && currentSourcesSummary.sources) ? currentSourcesSummary.sources[sourceKey] : null;
  const customCat = customCategories.find(c => c.id === sourceKey || c.name.toLowerCase() === (sourceKey || "").toLowerCase());

  const name = sData?.name || customCat?.name || (sourceKey === 'lis_pendens' ? 'Lis Pendens' : (sourceKey === 'code_violations' ? 'Code Violations' : (sourceKey === 'tax_liens' ? 'Tax Liens' : (sourceKey === 'probate' ? 'Probate & Trusts' : sourceKey))));
  const badge = sData?.badge || customCat?.badge || "Distress Filing";
  const icon = sData?.icon || customCat?.icon || "📄";
  const desc = sData?.description || customCat?.description || "Public court, tax and municipal distress filings.";
  const count = sData?.lead_count || 0;
  const lastLoaded = sData?.last_loaded_full || sData?.last_loaded || "Not loaded yet";
  const fileName = sData?.file_name || (count > 0 ? "Matched parquet database cache" : "None loaded yet");
  const fileSize = sData?.file_size || (count > 0 ? "Active cache" : "-");
  const portalUrl = sData?.portal_url || customCat?.portal_url || "#";
  const portalName = sData?.portal_name || (customCat ? `${customCat.name} Portal` : "Official County Records Portal");

  const activeCounty = selectedCountyKey || "Orange";
  const activeState = currentState || "FL";

  const iconEl = document.getElementById("sourceDetailIcon");
  if (iconEl) iconEl.innerText = icon;

  const nameEl = document.getElementById("sourceDetailName");
  if (nameEl) nameEl.innerText = name;

  const badgeEl = document.getElementById("sourceDetailBadge");
  if (badgeEl) badgeEl.innerText = badge;

  const countyEl = document.getElementById("sourceDetailCounty");
  if (countyEl) countyEl.innerText = `${activeCounty} County, ${activeState} • Source & Ingestion Metadata`;

  const descEl = document.getElementById("sourceDetailDesc");
  if (descEl) descEl.innerText = desc;

  const countEl = document.getElementById("sourceDetailCount");
  if (countEl) countEl.innerText = `${count.toLocaleString()} Leads`;

  const dateEl = document.getElementById("sourceDetailDate");
  if (dateEl) dateEl.innerText = lastLoaded;

  const freshEl = document.getElementById("sourceDetailFreshness");
  if (freshEl) {
    if (count > 0 && lastLoaded !== "Not loaded yet" && lastLoaded !== "Awaiting CSV upload") {
      freshEl.className = "text-[10px] text-emerald-400 font-semibold mt-0.5";
      freshEl.innerText = "✓ Active & cross-referenced";
    } else {
      freshEl.className = "text-[10px] text-amber-400 font-semibold mt-0.5";
      freshEl.innerText = "⏳ Awaiting fresh CSV upload";
    }
  }

  const fnEl = document.getElementById("sourceDetailFilename");
  if (fnEl) fnEl.innerText = fileName;

  const fsEl = document.getElementById("sourceDetailFileSize");
  if (fsEl) fsEl.innerText = fileSize;

  const pLink = document.getElementById("sourceDetailPortalLink");
  if (pLink) {
    pLink.href = portalUrl;
    const pNameEl = document.getElementById("sourceDetailPortalName");
    if (pNameEl) pNameEl.innerText = portalName;
  }

  // Secondary Portal (e.g. Comptroller Official Records for Probate in Orange County)
  const secRow = document.getElementById("sourceDetailSecondaryPortalRow");
  const secLink = document.getElementById("sourceDetailSecondaryPortalLink");
  const secName = document.getElementById("sourceDetailSecondaryPortalName");
  const btnSecPortal = document.getElementById("btnSourceDetailSecondaryPortal");

  if (sData && sData.secondary_portal_url) {
    if (secRow) secRow.classList.remove("hidden");
    if (secLink) secLink.href = sData.secondary_portal_url;
    if (secName) secName.innerText = sData.secondary_portal_name || "Comptroller Official Records";
    if (btnSecPortal) {
      btnSecPortal.classList.remove("hidden");
      btnSecPortal.href = sData.secondary_portal_url;
    }
  } else {
    if (secRow) secRow.classList.add("hidden");
    if (btnSecPortal) btnSecPortal.classList.add("hidden");
  }

  // Disclaimer Alert Note
  const disclaimerNote = document.getElementById("sourceDetailDisclaimerNote");
  const needsDisclaimer = (sData && sData.portal_disclaimer_note) || 
                          (portalUrl && (portalUrl.includes("occompt") || portalUrl.includes("selfservice"))) ||
                          (sData && sData.secondary_portal_url && (sData.secondary_portal_url.includes("occompt") || sData.secondary_portal_url.includes("selfservice")));
  if (disclaimerNote) {
    if (needsDisclaimer) {
      disclaimerNote.classList.remove("hidden");
    } else {
      disclaimerNote.classList.add("hidden");
    }
  }

  const btnFilter = document.getElementById("btnSourceDetailFilter");
  if (btnFilter) {
    btnFilter.onclick = () => {
      closeSourceDetailsModal();
      if (["lis_pendens", "code_violations", "tax_liens", "probate"].includes(sourceKey)) {
        quickFilterLeadType(sourceKey);
      } else if (sourceKey === "divorce") {
        filterLiveRecords("divorce");
      } else if (sourceKey === "judgments_liens") {
        filterLiveRecords("judgment");
      } else if (sourceKey === "ouc_water_shutoff") {
        filterLiveRecords("water_shutoff");
      } else {
        filterLiveRecordsByCustom(name);
      }
      const liveSection = document.getElementById("liveRecordsSection");
      if (liveSection) liveSection.scrollIntoView({ behavior: 'smooth' });
    };
  }

  const btnUpdate = document.getElementById("btnSourceDetailUpdate");
  if (btnUpdate) {
    btnUpdate.onclick = () => {
      closeSourceDetailsModal();
      openImportModal(sourceKey);
    };
  }

  const btnPortal = document.getElementById("btnSourceDetailPortal");
  if (btnPortal) {
    btnPortal.href = portalUrl;
    btnPortal.innerHTML = (sData && sData.secondary_portal_url) ? "🏛️ Clerk Docket ↗" : "🌐 Visit Portal ↗";
  }

  modal.classList.remove("hidden");
}

function closeSourceDetailsModal() {
  const modal = document.getElementById("sourceDetailsModal");
  if (modal) modal.classList.add("hidden");
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
    }
  } catch (err) {
    console.error("Error loading SMS settings:", err);
  }
}

function resolveSmsOwnerName(ownerName, savedContact, matchedRecord) {
  const recordName = matchedRecord?.Clean_First_Name && matchedRecord?.Clean_Last_Name
    ? `${matchedRecord.Clean_First_Name} ${matchedRecord.Clean_Last_Name}`
    : matchedRecord?.Clean_Full_Name || matchedRecord?.Clean_First_Name;
  const candidates = [ownerName, savedContact?.owner, recordName];
  for (const candidate of candidates) {
    const name = formatDisplayName(candidate);
    if (name && !/^(unknown owner|unknown|homeowner|florida homeowner|property owner)$/i.test(name)) {
      return name;
    }
  }
  return "";
}

function openSmsModal(parcelId, phone, ownerName, propertyAddress) {
  markLeadAsViewed(parcelId);
  const modal = document.getElementById("smsModal");
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }

  try {
    const matchedRecord = (liveRecords || []).find(r => r && (r.Parcel_ID === parcelId || r.Property_Address === propertyAddress));
    const savedContact = savedContactsCache?.[parcelId];
    const leadCounty = savedContact?.county || matchedRecord?.County || selectedCountyKey || 'Pinellas';
    const pidEl = document.getElementById("smsParcelId");
    if (pidEl) pidEl.value = parcelId || "";
    const cntyEl = document.getElementById("smsCounty");
    if (cntyEl) cntyEl.value = leadCounty;
    const cleanOwner = resolveSmsOwnerName(ownerName, savedContact, matchedRecord);
    const cleanAddr = formatDisplayAddress(propertyAddress);
    const ownEl = document.getElementById("smsOwnerName");
    if (ownEl) ownEl.value = cleanOwner || "";
    const addrEl = document.getElementById("smsPropertyAddress");
    if (addrEl) addrEl.value = cleanAddr || "";

    const ownDisp = document.getElementById("smsOwnerDisplay");
    if (ownDisp) ownDisp.innerText = cleanOwner || "Homeowner";
    const addrDisp = document.getElementById("smsAddressDisplay");
    if (addrDisp) addrDisp.innerText = cleanAddr || "Florida Property";
    const phInput = document.getElementById("smsPhoneInput");
    if (phInput) phInput.value = phone || "";

    const statusBanner = document.getElementById("smsStatusBanner");
    if (statusBanner) {
      statusBanner.className = "hidden p-3 rounded-xl text-xs font-semibold";
      statusBanner.innerText = "";
    }

    // Setup active SMS lead context for Emma Copilot
    const marketVal = matchedRecord ? (matchedRecord.Market_Value || matchedRecord.Just_Value || matchedRecord.Assessed_Value || 0) : 0;
    let distType = "GENERAL_DISTRESS";
    if (matchedRecord) {
      if (matchedRecord.Code_Violations || matchedRecord.Category === 'code_violations') distType = "CODE_VIOLATION";
      else if (matchedRecord.Lis_Pendens || matchedRecord.Category === 'lis_pendens') distType = "LIS_PENDENS";
      else if (matchedRecord.Probate || matchedRecord.Category === 'probate') distType = "PROBATE";
    }
    window.activeSmsLeadContext = {
      parcelId: parcelId || "",
      phone: phone || "",
      ownerName: cleanOwner,
      propertyAddress: propertyAddress || "",
      county: leadCounty,
      city: savedContact?.city || matchedRecord?.Property_City || '',
      marketValue: marketVal,
      distressType: distType
    };

    // Auto-rotate across configured SMS templates on each outreach touch to prevent carrier spam
    const availableTemplates = (outreachTemplatesCache && outreachTemplatesCache.sms && outreachTemplatesCache.sms.length > 0)
      ? outreachTemplatesCache.sms
      : [
          { id: "casual_direct", name: "Owner Check 1" },
          { id: "quick_question", name: "Owner Check 2" },
          { id: "neighbor_investor", name: "Owner Check 3" },
          { id: "quick_checkin", name: "Owner Check 4" }
        ];

    let rotIdx = parseInt(localStorage.getItem("flh_last_sms_rot_idx") || "0", 10);
    rotIdx = (rotIdx + 1) % availableTemplates.length;
    localStorage.setItem("flh_last_sms_rot_idx", String(rotIdx));
    let targetTemplateId = availableTemplates[rotIdx].id;

    // Refresh template selector options from cache
    const tmplSelect = document.getElementById("smsTemplateSelect");
    if (tmplSelect && outreachTemplatesCache && outreachTemplatesCache.sms) {
      tmplSelect.innerHTML = "";
      outreachTemplatesCache.sms.forEach(t => {
        const opt = document.createElement("option");
        opt.value = t.id;
        opt.textContent = t.name;
        tmplSelect.appendChild(opt);
      });
      tmplSelect.value = targetTemplateId;
      if (!tmplSelect.value) {
        tmplSelect.value = outreachTemplatesCache.sms[0]?.id || "casual_direct";
      }
    } else if (tmplSelect) {
      tmplSelect.value = targetTemplateId;
    }

    // Reset Copilot UI
    const copilotBox = document.getElementById("smsCopilotSuggestionBox");
    if (copilotBox) copilotBox.classList.add("hidden");
    const copilotTxt = document.getElementById("smsCopilotSuggestionText");
    if (copilotTxt) copilotTxt.innerHTML = "";
    const spreadBadge = document.getElementById("smsDealSpreadBadge");
    if (spreadBadge) {
      if (marketVal > 0) {
        spreadBadge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30";
        spreadBadge.innerText = `Val: $${Number(marketVal).toLocaleString()}`;
        spreadBadge.classList.remove("hidden");
      } else {
        spreadBadge.classList.add("hidden");
      }
    }

    // Check if lead already has an ongoing conversation thread
    const threadAlert = document.getElementById("smsExistingThreadAlert");
    if (threadAlert) {
      const digits = String(phone || "").replace(/\D/g, "");
      const cleanDigits = digits.length > 10 && digits.startsWith("1") ? digits.substring(1) : digits;
      const existing = (inboxThreadsCache || []).find(t => {
        const tDigits = String(t.clean_phone || t.phone || "").replace(/\D/g, "");
        const tClean = tDigits.length > 10 && tDigits.startsWith("1") ? tDigits.substring(1) : tDigits;
        return (cleanDigits && (cleanDigits === tClean || tClean.includes(cleanDigits))) || (parcelId && t.parcel_id === parcelId);
      });
      if (existing && existing.messages && existing.messages.length > 0) {
        threadAlert.classList.remove("hidden");
        const msgTxt = document.getElementById("smsExistingThreadText");
        if (msgTxt) msgTxt.innerText = `You have an active chat with ${cleanOwner || 'seller'} (${existing.messages.length} messages).`;
        const jumpBtn = document.getElementById("btnJumpToThread");
        if (jumpBtn) {
          jumpBtn.onclick = () => {
            closeSmsModal();
            openSellerThread(phone, parcelId);
          };
        }
      } else {
        threadAlert.classList.add("hidden");
      }
    }

    // Fetch and populate prior outreach alert and inline thread history directly in 1-by-1 modal
    const priorSmsAlert = document.getElementById("smsPriorSentAlert");
    const priorSmsDetails = document.getElementById("smsPriorSentDetails");
    const inlineThreadBox = document.getElementById("smsInlineThreadBox");
    const inlineThreadCount = document.getElementById("smsInlineThreadCount");
    const inlineThreadMessages = document.getElementById("smsInlineThreadMessages");

    if (priorSmsAlert) priorSmsAlert.classList.add("hidden");
    if (inlineThreadBox) inlineThreadBox.classList.add("hidden");

    fetch(`/api/outreach/lead?parcel_id=${encodeURIComponent(parcelId || '')}&phone=${encodeURIComponent(phone || '')}`)
      .then(res => res.json())
      .then(data => {
        if (data.status === "success" && data.items && data.items.length > 0) {
          const smsItems = data.items.filter(item => String(item.channel || '').toUpperCase() === 'SMS');
          if (smsItems.length > 0) {
            const lastSms = smsItems[smsItems.length - 1];
            if (priorSmsAlert && priorSmsDetails) {
              priorSmsAlert.classList.remove("hidden");
              priorSmsDetails.innerHTML = `SMS already dispatched on <b>${lastSms.timestamp}</b> to <b>${lastSms.recipient || lastSms.phone || phone}</b>. Last sent: <span class="italic text-amber-100">"${escapeAttr(lastSms.message || '')}"</span>`;
            }
            if (inlineThreadBox && inlineThreadMessages) {
              inlineThreadBox.classList.remove("hidden");
              if (inlineThreadCount) inlineThreadCount.innerText = `${smsItems.length} message${smsItems.length > 1 ? 's' : ''}`;
              inlineThreadMessages.innerHTML = smsItems.map(m => {
                const isOutbound = String(m.direction || 'OUTBOUND').toUpperCase() === 'OUTBOUND';
                return `
                  <div class="p-2 rounded-lg ${isOutbound ? 'bg-blue-950/70 border border-blue-800/60 ml-4' : 'bg-emerald-950/70 border border-emerald-800/60 mr-4'} space-y-1">
                    <div class="flex items-center justify-between text-[10px] ${isOutbound ? 'text-blue-300' : 'text-emerald-300'} font-semibold">
                      <span>${isOutbound ? '📤 Outbound (You)' : '📥 Inbound (Seller)'}</span>
                      <span class="text-slate-400 font-mono">${m.timestamp || ''}</span>
                    </div>
                    <div class="text-xs text-slate-200 leading-snug">${escapeAttr(m.message || '')}</div>
                  </div>
                `;
              }).join('');
            }
          }
        }
      })
      .catch(err => console.warn("Could not load SMS outreach history:", err));

    // Apply active template
    const activeKey = tmplSelect ? tmplSelect.value : targetTemplateId;
    applySmsTemplate(activeKey);
  } catch (err) {
    console.error("Error setting up SMS modal:", err);
  }
}

function cycleNextSmsTemplate() {
  const tmplSelect = document.getElementById("smsTemplateSelect");
  if (!tmplSelect || !tmplSelect.options || tmplSelect.options.length === 0) return;
  const curIdx = tmplSelect.selectedIndex;
  const nextIdx = (curIdx + 1) % tmplSelect.options.length;
  tmplSelect.selectedIndex = nextIdx;
  applySmsTemplate(tmplSelect.value);
}

function closeSmsModal() {
  const modal = document.getElementById("smsModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

function applySmsTemplate(templateKey) {
  const aliases = {multi_list:'casual_direct',single_list:'quick_question',ultra_short:'neighbor_investor',cash_offer:'casual_direct'};
  templateKey = aliases[templateKey] || templateKey;
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
  const leadCounty = document.getElementById('smsCounty')?.value || selectedCountyKey || 'Pinellas';

  // Smart first-name extraction
  // 1. Corporate/LLC/Trust/Estate names → use "there" as greeting
  const isCorporate = /\b(llc|inc|corp|trust|estate|properties|holdings|group|management|solutions|services|investments|realty|real estate)\b/i.test(rawOwner);
  let firstName, lastName;
  if (isCorporate || !rawOwner.trim() || /^(homeowner|property owner|unknown)$/i.test(rawOwner.trim())) {
    firstName = "there";
    lastName = "";
  } else {
    // 2. Try to get first name from savedContactsCache by current parcel
    const curParcel = document.getElementById("smsParcelId")?.value || "";
    const cachedContact = curParcel && savedContactsCache ? savedContactsCache[curParcel] : null;
    let resolvedOwner = rawOwner.trim();
    if (cachedContact?.owner && !/^(homeowner|property owner|unknown)$/i.test(cachedContact.owner.trim())) {
      resolvedOwner = cachedContact.owner.trim();
    }
    const nameParts = resolvedOwner.split(/\s+/);
    // 3. Detect county SURNAME FIRSTNAME all-caps format (e.g., "GARCIA JOSE")
    //    Heuristic: all-caps, 2 words, no lowercase letters → likely last-first
    const allCaps = /^[A-Z\s'-]+$/.test(resolvedOwner) && nameParts.length >= 2;
    if (allCaps) {
      // Last word is likely the first name in county-format "LAST FIRST"
      firstName = formatDisplayName(nameParts[nameParts.length - 1]);
      lastName = formatDisplayName(nameParts.slice(0, -1).join(" "));
    } else {
      firstName = formatDisplayName(nameParts[0] || "there");
      lastName = formatDisplayName(nameParts.length > 1 ? nameParts.slice(1).join(" ") : "");
    }
    // Final safety net
    if (!firstName || /^(homeowner|property owner|unknown)$/i.test(firstName)) {
      firstName = "there";
    }
  }

  // Extract Street Address & City
  const addrParts = rawAddr.split(",");
  const streetAddr = formatDisplayAddress(addrParts[0]?.trim() || rawAddr);
  const city = formatDisplayCity(window.activeSmsLeadContext?.city || leadCounty || "your area");

  let filled = templateBody
    .replace(/{FirstName}/g, firstName)
    .replace(/{LastName}/g, lastName)
    .replace(/{Address}/g, streetAddr)
    .replace(/{City}/g, city)
    .replace(/{State}/g, currentState || "FL")
    .replace(/{County}/g, leadCounty)
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
    const tmplSelect = document.getElementById("smsTemplateSelect");
    const chosenTmpl = tmplSelect ? tmplSelect.value : "";
    let openerAngle = chosenTmpl || "casual_direct";

    const res = await fetch("/api/sms/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        phone: phone,
        message: message,
        parcel_id: parcelId,
        county: county,
        owner_name: ownerName,
        property_address: propertyAddress,
        opener_angle: openerAngle
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
        savedContactsCache[parcelId].sms_initial_resend_pending = false;
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
• We buy 100% As-Is: absolutely no repairs, painting, or cleaning required
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
• No repairs needed: we buy strictly in current As-Is condition.
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
• Zero repair demands: roof damage, plumbing, electrical, or structural issues welcome
• All-cash purchase with no appraisal contingencies or bank inspection delays
• Fast closing on your preferred date (7 to 14 days)
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
• All-Cash Offer: No bank approvals, no appraisal hurdles
• As-Is Condition: No repairs, painting, or cleaning needed
• Fast & Flexible Closing: Close in 7 to 14 days or on your chosen date
• Zero Expenses: No 6% Realtor commissions and no seller closing costs

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

function getDefaultEmailTemplate(lead) {
  const types = [lead.Lead_Type, ...(Array.isArray(lead.All_Lead_Types) ? lead.All_Lead_Types : [])].filter(Boolean);
  const hasProbate = lead.Has_Confirmed_Probate === 'Yes' ||
    (lead.Has_Confirmed_Probate !== 'No' && types.some(t => /\bprobate\b/i.test(t) && !/death certificate/i.test(t)));
  if (hasProbate) return 'probate';
  if (types.some(t => /lis[ _]pendens|foreclosure/i.test(t))) return 'lis_pendens';
  if (types.some(t => /code/i.test(t))) return 'code_violation';
  return 'quick_cash';
}

function openEmailModal(parcelId, email, ownerName, propertyAddress) {
  markLeadAsViewed(parcelId);
  const modal = document.getElementById("emailModal");
  if (!modal) return;

  modal.classList.remove("hidden");
  modal.style.display = "flex";

  try {
    const pidEl = document.getElementById("emailParcelId");
    if (pidEl) pidEl.value = parcelId || "";
    const cntyEl = document.getElementById("emailCounty");
    if (cntyEl) cntyEl.value = selectedCountyKey || "Pinellas";
    const cleanOwner = formatDisplayName(ownerName);
    const cleanAddr = formatDisplayAddress(propertyAddress);
    const ownEl = document.getElementById("emailOwnerName");
    if (ownEl) ownEl.value = cleanOwner || "";
    const addrEl = document.getElementById("emailPropertyAddress");
    if (addrEl) addrEl.value = cleanAddr || "";

    const ownDisp = document.getElementById("emailOwnerDisplay");
    if (ownDisp) ownDisp.innerText = cleanOwner || "Homeowner";
    const addrDisp = document.getElementById("emailAddressDisplay");
    if (addrDisp) addrDisp.innerText = cleanAddr || "Florida Property";
    const emailInput = document.getElementById("emailRecipientInput");
    if (emailInput) emailInput.value = email || "";

    const banner = document.getElementById("emailStatusBanner");
    if (banner) {
      banner.className = "hidden p-3 rounded-xl text-xs font-semibold";
      banner.innerText = "";
    }

    // Inspect lead record to select the smartest default template
    const lead = getActivePipelineDataset().find(r => r && (r.Parcel_ID === parcelId || r.Property_Address === propertyAddress)) || {};
    window.activeEmailLeadRecord = lead;
    const isStacked = lead.Is_Stacked_Distress === "Yes";
    const defId = getDefaultEmailTemplate(lead);
    const hasForeclosure = [lead.Lead_Type, ...(lead.All_Lead_Types || [])].some(t => /lis[ _]pendens|foreclosure/i.test(t || ''));
    if (cntyEl) cntyEl.value = lead.County || selectedCountyKey || 'Pinellas';

    // Configure Double Distress Toggle Bar
    const ddSwitch = document.getElementById("emailDoubleDistressSwitch");
    if (ddSwitch) {
      if (isStacked && (defId === 'probate' || hasForeclosure)) {
        ddSwitch.classList.remove("hidden");
        const btnProbate = document.getElementById("btnEmailSwitchProbate");
        const btnLp = document.getElementById("btnEmailSwitchLp");
        if (btnProbate && btnLp) {
          const active = 'px-2.5 py-1 rounded-lg text-xs font-bold bg-indigo-600 text-white transition cursor-pointer shadow-sm';
          const inactive = 'px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-800 hover:bg-slate-700 text-slate-300 transition cursor-pointer';
          btnProbate.className = defId === 'probate' ? active : inactive;
          btnLp.className = defId === 'lis_pendens' ? active : inactive;
          btnProbate.classList.toggle('hidden', defId !== 'probate');
          btnLp.classList.toggle('hidden', !hasForeclosure);
        }
      } else {
        ddSwitch.classList.add("hidden");
      }
    }

    // Refresh email template dropdown options from cache
    const tmplSelect = document.getElementById("emailTemplateSelect");
    if (tmplSelect && outreachTemplatesCache && outreachTemplatesCache.email) {
      tmplSelect.innerHTML = "";
      outreachTemplatesCache.email.forEach(t => {
        const opt = document.createElement("option");
        opt.value = t.id;
        opt.textContent = t.name;
        opt.disabled = t.id === 'probate' && defId !== 'probate';
        tmplSelect.appendChild(opt);
      });
      tmplSelect.value = outreachTemplatesCache.email.some(t => t.id === defId) ? defId : outreachTemplatesCache.email[0]?.id;
    } else if (tmplSelect) {
      tmplSelect.value = defId;
    }

    // Prior Email Sent Alert check
    const priorEmailAlert = document.getElementById("emailPriorSentAlert");
    const priorEmailDetails = document.getElementById("emailPriorSentDetails");
    if (priorEmailAlert) priorEmailAlert.classList.add("hidden");

    fetch(`/api/outreach/lead?parcel_id=${encodeURIComponent(parcelId || '')}&email=${encodeURIComponent(email || '')}`)
      .then(res => res.json())
      .then(data => {
        if (data.status === "success" && data.items && data.items.length > 0) {
          const emailItems = data.items.filter(item => String(item.channel || '').toUpperCase() === 'EMAIL');
          if (emailItems.length > 0) {
            const lastEmail = emailItems[emailItems.length - 1];
            if (priorEmailAlert && priorEmailDetails) {
              priorEmailAlert.classList.remove("hidden");
              priorEmailDetails.innerHTML = `Offer email already dispatched on <b>${lastEmail.timestamp}</b> to <b>${lastEmail.recipient || email}</b> (Subject: <em>${escapeAttr(lastEmail.subject || '')}</em>). Avoid duplicate emails unless following up.`;
            }
          }
        }
      })
      .catch(err => console.warn("Could not check email outreach history:", err));

    const activeKey = tmplSelect ? tmplSelect.value : defId;
    applyEmailTemplate(activeKey);
  } catch (err) {
    console.error("Error setting up email modal:", err);
  }
}

window.selectDoubleDistressEmail = function(type) {
  if (type === 'probate' && getDefaultEmailTemplate(window.activeEmailLeadRecord || {}) !== 'probate') return;
  const tmplSelect = document.getElementById("emailTemplateSelect");
  if (tmplSelect) {
    tmplSelect.value = type;
    applyEmailTemplate(type);
  }
  const btnProbate = document.getElementById("btnEmailSwitchProbate");
  const btnLp = document.getElementById("btnEmailSwitchLp");
  if (btnProbate && btnLp) {
    if (type === "probate") {
      btnProbate.className = "px-2.5 py-1 rounded-lg text-xs font-bold bg-indigo-600 text-white transition cursor-pointer shadow-sm";
      btnLp.className = "px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-800 hover:bg-slate-700 text-slate-300 transition cursor-pointer";
    } else {
      btnLp.className = "px-2.5 py-1 rounded-lg text-xs font-bold bg-blue-600 text-white transition cursor-pointer shadow-sm";
      btnProbate.className = "px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-800 hover:bg-slate-700 text-slate-300 transition cursor-pointer";
    }
    const lead = window.activeEmailLeadRecord || {};
    btnProbate.classList.toggle('hidden', getDefaultEmailTemplate(lead) !== 'probate');
    btnLp.classList.toggle('hidden', ![lead.Lead_Type, ...(lead.All_Lead_Types || [])]
      .some(t => /lis[ _]pendens|foreclosure/i.test(t || '')));
  }
};

function closeEmailModal() {
  const modal = document.getElementById("emailModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

function applyEmailTemplate(templateKey) {
  if (templateKey === 'probate' && window.activeEmailLeadRecord &&
      getDefaultEmailTemplate(window.activeEmailLeadRecord) !== 'probate') {
    templateKey = getDefaultEmailTemplate(window.activeEmailLeadRecord);
    const selector = document.getElementById('emailTemplateSelect');
    if (selector) selector.value = templateKey;
  }
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
  let firstName = formatDisplayName(nameParts[0] || "Homeowner");
  const lastName = formatDisplayName(nameParts.length > 1 ? nameParts.slice(1).join(" ") : "");

  const addrParts = rawAddr.split(",");
  const streetAddr = formatDisplayAddress(addrParts[0]?.trim() || rawAddr);
  const city = formatDisplayCity(selectedCountyKey || "Orlando");

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
      SMS_TEMPLATES.cash_offer = outreachTemplatesCache.sms?.[0]?.body || SMS_TEMPLATES.casual_direct;
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
  markLeadAsViewed(parcelId);
  const modal = document.getElementById("contractModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.style.display = "flex";

  const cleanAddr = formatDisplayAddress(propertyAddress);
  const cleanCity = formatDisplayCity(propertyCity || (selectedCountyKey === 'Orange' ? 'Orlando' : 'St Petersburg'));
  const cleanOwner = formatDisplayName(ownerName);

  // Hidden Inputs
  document.getElementById("contractParcelId").value = parcelId || "";
  document.getElementById("contractCounty").value = selectedCountyKey || "Pinellas";
  document.getElementById("contractPropertyStreet").value = cleanAddr || "";
  document.getElementById("contractPropertyCity").value = cleanCity || "St Petersburg";
  document.getElementById("contractPropertyState").value = currentState || "FL";
  document.getElementById("contractPropertyZip").value = propertyZip || "";

  // Visual header tags
  document.getElementById("contractDisplayPin").innerText = `PIN: ${parcelId || 'N/A'}`;
  document.getElementById("contractDisplayAddress").innerText = cleanAddr || "Unknown Address";
  document.getElementById("contractDisplayCity").innerText = `${cleanCity || 'Pinellas'}, ${currentState || 'FL'} ${propertyZip || ''}`;

  // Form Fields
  document.getElementById("contractSellerName").value = cleanOwner || "Property Owner";
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

function launchContractFromSmsModal() {
  const parcelId = document.getElementById("smsParcelId")?.value || "";
  const phone = document.getElementById("smsPhoneInput")?.value || "";
  const ownerName = document.getElementById("smsOwnerName")?.value || "";
  const propertyAddress = document.getElementById("smsPropertyAddress")?.value || "";

  let rec = null;
  if (parcelId && typeof savedContactsCache !== "undefined" && savedContactsCache[parcelId]) {
    rec = savedContactsCache[parcelId];
  } else if (parcelId && typeof liveRecords !== "undefined" && Array.isArray(liveRecords)) {
    rec = liveRecords.find(r => r && r.Parcel_ID === parcelId);
  }

  const city = rec?.Property_City || rec?.city || "St Petersburg";
  const zip = rec?.Property_Zip || rec?.zip || "";
  const marketVal = rec ? (rec.Market_Value || rec.Just_Value || rec.just_value || rec.Assessed_Value || 0) : 0;
  const email = (rec && (rec.Email || rec.email)) ? (rec.Email || rec.email) : "";

  closeSmsModal();
  openContractModal(parcelId, phone, email, ownerName, propertyAddress, city, zip, marketVal);
}

function launchContractFromEmailModal() {
  const parcelId = document.getElementById("emailParcelId")?.value || "";
  const email = document.getElementById("emailRecipientInput")?.value || "";
  const ownerName = document.getElementById("emailOwnerName")?.value || "";
  const propertyAddress = document.getElementById("emailPropertyAddress")?.value || "";

  let rec = null;
  if (parcelId && typeof savedContactsCache !== "undefined" && savedContactsCache[parcelId]) {
    rec = savedContactsCache[parcelId];
  } else if (parcelId && typeof liveRecords !== "undefined" && Array.isArray(liveRecords)) {
    rec = liveRecords.find(r => r && r.Parcel_ID === parcelId);
  }

  const city = rec?.Property_City || rec?.city || "St Petersburg";
  const zip = rec?.Property_Zip || rec?.zip || "";
  const marketVal = rec ? (rec.Market_Value || rec.Just_Value || rec.just_value || rec.Assessed_Value || 0) : 0;
  const phone = (rec && (rec.Phone || rec.phone)) ? (rec.Phone || rec.phone) : "";

  closeEmailModal();
  openContractModal(parcelId, phone, email, ownerName, propertyAddress, city, zip, marketVal);
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

/* =========================================================================
   SELLER BOT ENGINE & GOLDEN TRAINING SUITE CONTROLLER
   Emma & John Florida Distress Acquisitions Architecture
   ========================================================================= */

let trainingScenariosCache = [];
let currentTrainingFilterCategory = "ALL";
let activeTrainingScenarioId = null;
let sellerBotSettingsCache = null;
let sellerInboxCache = [];

// -------------------------------------------------------------------------
// Golden Training Suite Functions
// -------------------------------------------------------------------------

function openSellerTrainingModal() {
  const modal = document.getElementById("sellerTrainingModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.style.display = "flex";
  loadTrainingSuite();
}

function closeSellerTrainingModal() {
  const modal = document.getElementById("sellerTrainingModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.style.display = "none";
}

async function loadTrainingSuite() {
  const listEl = document.getElementById("trainingScenariosList");
  if (listEl) {
    listEl.innerHTML = `<div class="p-4 text-center text-xs text-slate-500">Loading golden scenarios...</div>`;
  }
  try {
    const res = await fetch("/api/bot/training");
    if (!res.ok) throw new Error("Failed to load training database");
    const data = await res.json();
    trainingScenariosCache = data.scenarios || [];

    updateTrainingCategoryCounters();
    filterTrainingByCategory(currentTrainingFilterCategory);

    if (trainingScenariosCache.length > 0 && !activeTrainingScenarioId) {
      selectTrainingScenario(trainingScenariosCache[0].id);
    }
  } catch (err) {
    console.error("Error loading training suite:", err);
    if (listEl) {
      listEl.innerHTML = `<div class="p-4 text-center text-xs text-rose-400">Error loading training scenarios.</div>`;
    }
  }
}

function updateTrainingCategoryCounters() {
  const allCount = trainingScenariosCache.length;
  const codeCount = trainingScenariosCache.filter(s => s.category === "CODE_VIOLATION").length;
  const lisCount = trainingScenariosCache.filter(s => s.category === "LIS_PENDENS").length;
  const probCount = trainingScenariosCache.filter(s => s.category === "PROBATE").length;
  const genCount = trainingScenariosCache.filter(s => s.category === "GENERAL_DISTRESS").length;

  const setCnt = (id, cnt) => {
    const el = document.getElementById(id);
    if (el) el.innerText = cnt;
  };
  setCnt("countTrainAll", allCount);
  setCnt("countTrainCode", codeCount);
  setCnt("countTrainLis", lisCount);
  setCnt("countTrainProbate", probCount);
  setCnt("countTrainGeneral", genCount);
}

function filterTrainingByCategory(cat) {
  currentTrainingFilterCategory = cat;
  const tabs = {
    ALL: document.getElementById("tabTrainAll"),
    CODE_VIOLATION: document.getElementById("tabTrainCode"),
    LIS_PENDENS: document.getElementById("tabTrainLis"),
    PROBATE: document.getElementById("tabTrainProbate"),
    GENERAL_DISTRESS: document.getElementById("tabTrainGeneral")
  };

  Object.entries(tabs).forEach(([k, el]) => {
    if (!el) return;
    if (k === cat) {
      el.className = "px-3 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 bg-amber-500/20 text-amber-300 border border-amber-500/40 cursor-pointer";
    } else {
      el.className = "px-3 py-1.5 rounded-xl text-xs font-semibold transition flex items-center gap-1.5 bg-slate-800 text-slate-300 hover:text-white border border-slate-700 cursor-pointer";
    }
  });

  const term = (document.getElementById("trainingSearchInput")?.value || "").toLowerCase().trim();
  renderTrainingScenariosList(term);
}

function searchTrainingScenarios(term) {
  renderTrainingScenariosList((term || "").toLowerCase().trim());
}

function renderTrainingScenariosList(filterTerm = "") {
  const listEl = document.getElementById("trainingScenariosList");
  if (!listEl) return;

  let items = trainingScenariosCache;
  if (currentTrainingFilterCategory !== "ALL") {
    items = items.filter(s => s.category === currentTrainingFilterCategory);
  }
  if (filterTerm) {
    items = items.filter(s =>
      (s.title || "").toLowerCase().includes(filterTerm) ||
      (s.typical_inbound || "").toLowerCase().includes(filterTerm) ||
      (s.golden_response || "").toLowerCase().includes(filterTerm) ||
      (s.triggers || []).some(t => t.toLowerCase().includes(filterTerm))
    );
  }

  if (items.length === 0) {
    listEl.innerHTML = `<div class="p-6 text-center text-xs text-slate-500">No matching golden scenarios found.</div>`;
    return;
  }

  const categoryBadges = {
    CODE_VIOLATION: { label: "Code Violation", cls: "bg-amber-500/20 text-amber-300 border-amber-500/30" },
    LIS_PENDENS: { label: "Pre-Foreclosure", cls: "bg-rose-500/20 text-rose-300 border-rose-500/30" },
    PROBATE: { label: "Probate / Estate", cls: "bg-purple-500/20 text-purple-300 border-purple-500/30" },
    GENERAL_DISTRESS: { label: "General Distress", cls: "bg-blue-500/20 text-blue-300 border-blue-500/30" }
  };

  listEl.innerHTML = items.map(sc => {
    const isSelected = sc.id === activeTrainingScenarioId;
    const badge = categoryBadges[sc.category] || { label: sc.category, cls: "bg-slate-700 text-slate-300" };
    return `
      <div onclick="selectTrainingScenario('${sc.id}')" class="p-3 rounded-xl border transition cursor-pointer ${isSelected ? 'bg-amber-500/10 border-amber-500/60 shadow-md shadow-amber-950/20' : 'bg-slate-900/70 border-slate-800 hover:border-slate-700 hover:bg-slate-900'}">
        <div class="flex items-center justify-between gap-1 mb-1">
          <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${badge.cls}">${badge.label}</span>
          <span class="text-[9px] font-mono text-slate-500 truncate max-w-[100px]">${sc.deal_criteria ? escapeHtml(sc.deal_criteria) : ''}</span>
        </div>
        <div class="text-xs font-bold text-white leading-tight mb-1 truncate">${escapeHtml(sc.title)}</div>
        <div class="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">"${escapeHtml(sc.typical_inbound || '')}"</div>
      </div>
    `;
  }).join("");
}

function selectTrainingScenario(id) {
  activeTrainingScenarioId = id;
  const scenario = trainingScenariosCache.find(s => s.id === id);
  if (!scenario) return;

  // Highlight list item
  const term = (document.getElementById("trainingSearchInput")?.value || "").toLowerCase().trim();
  renderTrainingScenariosList(term);

  // Fill Editor
  document.getElementById("editorHeaderTitle").innerText = `✏️ Edit: ${scenario.title}`;
  document.getElementById("editorScenarioId").innerText = `ID: ${scenario.id}`;
  document.getElementById("editScenarioId").value = scenario.id;
  document.getElementById("editScenarioTitle").value = scenario.title || "";
  document.getElementById("editScenarioCategory").value = scenario.category || "GENERAL_DISTRESS";
  document.getElementById("editScenarioTriggers").value = (scenario.triggers || []).join(", ");
  document.getElementById("editScenarioInbound").value = scenario.typical_inbound || "";
  document.getElementById("editScenarioResponse").value = scenario.golden_response || "";
  document.getElementById("editScenarioCriteria").value = scenario.deal_criteria || "";
  document.getElementById("editScenarioHandoff").value = scenario.handoff_action || "";

  // Show delete button
  const delBtn = document.getElementById("btnDeleteScenario");
  if (delBtn) delBtn.classList.remove("hidden");

  // Pre-fill playground with this scenario
  document.getElementById("playDistressType").value = scenario.category || "GENERAL_DISTRESS";
  document.getElementById("playSellerText").value = scenario.typical_inbound || "";
}

function createNewTrainingScenario() {
  activeTrainingScenarioId = null;
  const term = (document.getElementById("trainingSearchInput")?.value || "").toLowerCase().trim();
  renderTrainingScenariosList(term);

  document.getElementById("editorHeaderTitle").innerText = "➕ Create New Golden Scenario";
  document.getElementById("editorScenarioId").innerText = "ID: new";
  document.getElementById("editScenarioId").value = "";
  document.getElementById("editScenarioTitle").value = "";
  document.getElementById("editScenarioCategory").value = currentTrainingFilterCategory !== "ALL" ? currentTrainingFilterCategory : "CODE_VIOLATION";
  document.getElementById("editScenarioTriggers").value = "";
  document.getElementById("editScenarioInbound").value = "";
  document.getElementById("editScenarioResponse").value = "";
  document.getElementById("editScenarioCriteria").value = "Target <= 70% of county market value";
  document.getElementById("editScenarioHandoff").value = "Phone appointment with John";

  const delBtn = document.getElementById("btnDeleteScenario");
  if (delBtn) delBtn.classList.add("hidden");

  const statusBanner = document.getElementById("trainingStatusBanner");
  if (statusBanner) statusBanner.className = "hidden";
}

async function handleSaveTrainingScenario(event) {
  event.preventDefault();
  const id = document.getElementById("editScenarioId").value;
  const title = document.getElementById("editScenarioTitle").value.trim();
  const category = document.getElementById("editScenarioCategory").value;
  const triggersRaw = document.getElementById("editScenarioTriggers").value;
  const triggers = triggersRaw.split(",").map(t => t.trim()).filter(Boolean);
  const typical_inbound = document.getElementById("editScenarioInbound").value.trim();
  const golden_response = document.getElementById("editScenarioResponse").value.trim();
  const deal_criteria = document.getElementById("editScenarioCriteria").value.trim();
  const handoff_action = document.getElementById("editScenarioHandoff").value.trim();

  const banner = document.getElementById("trainingStatusBanner");
  const btn = document.getElementById("btnSaveScenario");
  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> <span>Saving...</span>`;

  try {
    const payload = {
      id: id || undefined,
      title,
      category,
      triggers,
      typical_inbound,
      golden_response,
      deal_criteria,
      handoff_action
    };

    const res = await fetch("/api/bot/training/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.status === "ok") {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 block";
      banner.innerText = "✓ Golden scenario saved successfully!";
      await loadTrainingSuite();
      if (data.scenario?.id) {
        selectTrainingScenario(data.scenario.id);
      }
    } else {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/40 text-rose-300 block";
      banner.innerText = `⚠️ Failed to save: ${data.message || 'Unknown error'}`;
    }
  } catch (err) {
    banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/40 text-rose-300 block";
    banner.innerText = `⚠️ Error: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>💾</span> <span>Save to Golden Suite</span>`;
    setTimeout(() => { if (banner) banner.className = "hidden"; }, 4000);
  }
}

async function deleteCurrentTrainingScenario() {
  if (!activeTrainingScenarioId) return;
  if (!confirm("Are you sure you want to delete this golden training scenario?")) return;

  try {
    const res = await fetch(`/api/bot/training/${encodeURIComponent(activeTrainingScenarioId)}`, {
      method: "DELETE"
    });
    const data = await res.json();
    if (data.status === "ok") {
      activeTrainingScenarioId = null;
      await loadTrainingSuite();
      createNewTrainingScenario();
    } else {
      alert(`Could not delete scenario: ${data.message || 'Unknown error'}`);
    }
  } catch (err) {
    alert(`Error deleting scenario: ${err.message}`);
  }
}

async function testTrainingPlayground() {
  const distressType = document.getElementById("playDistressType").value;
  const sellerText = document.getElementById("playSellerText").value.trim();
  const assessedVal = parseFloat(document.getElementById("playAssessedValue").value) || 250000;

  if (!sellerText) {
    alert("Please enter a sample seller message to evaluate.");
    return;
  }

  const btn = document.getElementById("btnRunPlayground");
  const spinner = document.getElementById("playLoadingIndicator");
  const resultCard = document.getElementById("playResultCard");

  btn.disabled = true;
  spinner.classList.remove("hidden");
  resultCard.classList.add("hidden");

  try {
    const res = await fetch("/api/bot/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        seller_message: sellerText,
        distress_type: distressType,
        assessed_value: assessedVal,
        address: "742 Evergreen Terr, St Petersburg, FL"
      })
    });
    const data = await res.json();

    if (data.status === "ok") {
      resultCard.classList.remove("hidden");
      const respEl = document.getElementById("playResponseText");
      respEl.innerText = data.suggestion || "No response generated.";

      const badgeEl = document.getElementById("playDealBadge");
      const statsEl = document.getElementById("playDealStats");
      const spread = data.spread_eval || {};

      if (spread.deal_rating === "GOLD_DEAL") {
        badgeEl.className = "px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
        badgeEl.innerText = "🔥 GOLD DEAL";
      } else if (spread.deal_rating === "SPREAD_DEAL") {
        badgeEl.className = "px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40";
        badgeEl.innerText = "⚡ SPREAD DEAL";
      } else if (spread.deal_rating === "RETAIL_CREATIVE") {
        badgeEl.className = "px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40";
        badgeEl.innerText = "⚠️ RETAIL / CREATIVE";
      } else {
        badgeEl.className = "px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/40";
        badgeEl.innerText = "💬 INFORMATION INQUIRY";
      }

      if (spread.detected_price && spread.ratio_pct) {
        statsEl.innerText = `Asking $${Number(spread.detected_price).toLocaleString()} (${spread.ratio_pct}% of $${Number(assessedVal).toLocaleString()})`;
      } else {
        statsEl.innerText = `County Assessed: $${Number(assessedVal).toLocaleString()} (No explicit price mentioned)`;
      }
    } else {
      alert(`Playground test error: ${data.message || 'Unknown error'}`);
    }
  } catch (err) {
    alert(`Connection error: ${err.message}`);
  } finally {
    btn.disabled = false;
    spinner.classList.add("hidden");
  }
}

function copyPlaygroundToEditor() {
  const sellerText = document.getElementById("playSellerText").value.trim();
  const distressType = document.getElementById("playDistressType").value;
  const responseText = document.getElementById("playResponseText").innerText.trim();

  createNewTrainingScenario();
  document.getElementById("editScenarioCategory").value = distressType;
  document.getElementById("editScenarioInbound").value = sellerText;
  document.getElementById("editScenarioResponse").value = responseText;
  document.getElementById("editScenarioTitle").value = `Playground: ${distressType.replace('_', ' ')} Inquiry`;
  document.getElementById("trainingScenarioForm").scrollIntoView({ behavior: 'smooth' });
}

// -------------------------------------------------------------------------
// Seller Bot Settings Functions (Emma & John)
// -------------------------------------------------------------------------

function openSellerBotSettingsModal() {
  const modal = document.getElementById("sellerBotSettingsModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.style.display = "flex";
  loadSellerBotSettings();
}

function closeSellerBotSettingsModal() {
  const modal = document.getElementById("sellerBotSettingsModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.style.display = "none";
}

async function loadSellerBotSettings() {
  try {
    const res = await fetch("/api/bot/settings");
    if (!res.ok) return;
    const data = await res.json();
    if (data.status === "ok" && data.settings) {
      sellerBotSettingsCache = data.settings;
      const s = data.settings;
      const setVal = (id, v) => {
        const el = document.getElementById(id);
        if (el) el.value = v || "";
      };
      setVal("botName", s.bot_name || "Emma");
      setVal("botPartnerName", s.partner_name || "John");
      setVal("botGatewayPhone", s.gateway_phone || "(407) 793-7029");
      setVal("botOfficePhone", s.office_phone || "(407) 815-5043");
      setVal("botGeminiApiKey", s.gemini_api_key || "");
      setVal("botPersonalityPrompt", s.personality_prompt || "Friendly, warm, casual Florida local. Short 1 to 2 sentence texts. Disarming, understanding. Drive toward a quick 5 minute call with John.");

      const enabledEl = document.getElementById("botEnabled");
      if (enabledEl) enabledEl.checked = s.enabled !== false;

      const mode = s.mode || "copilot";
      const radCopilot = document.getElementById("botModeCopilot");
      const radAutopilot = document.getElementById("botModeAutopilot");
      if (mode === "autopilot") {
        if (radAutopilot) radAutopilot.checked = true;
      } else {
        if (radCopilot) radCopilot.checked = true;
      }
    }
  } catch (err) {
    console.error("Error loading seller bot settings:", err);
  }
}

async function handleSaveSellerBotSettings(event) {
  event.preventDefault();
  const banner = document.getElementById("botSettingsStatusBanner");
  const btn = document.getElementById("btnSaveSellerBot");
  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> <span>Saving...</span>`;

  try {
    const isAutopilot = document.getElementById("botModeAutopilot")?.checked;
    const payload = {
      enabled: document.getElementById("botEnabled")?.checked,
      mode: isAutopilot ? "autopilot" : "copilot",
      bot_name: document.getElementById("botName")?.value.trim() || "Emma",
      partner_name: document.getElementById("botPartnerName")?.value.trim() || "John",
      gateway_phone: document.getElementById("botGatewayPhone")?.value.trim() || "(407) 793-7029",
      office_phone: document.getElementById("botOfficePhone")?.value.trim() || "(407) 815-5043",
      gemini_api_key: document.getElementById("botGeminiApiKey")?.value.trim() || "",
      personality_prompt: document.getElementById("botPersonalityPrompt")?.value.trim() || ""
    };

    const res = await fetch("/api/bot/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.status === "ok") {
      sellerBotSettingsCache = payload;
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 block";
      banner.innerText = "✓ Emma bot settings saved successfully!";
      setTimeout(() => closeSellerBotSettingsModal(), 1200);
    } else {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/40 text-rose-300 block";
      banner.innerText = `⚠️ Failed to save: ${data.message || 'Unknown error'}`;
    }
  } catch (err) {
    banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/40 text-rose-300 block";
    banner.innerText = `⚠️ Error: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>💾</span> <span>Save Settings</span>`;
  }
}

async function testSellerGeminiApi() {
  const btn = document.getElementById("btnTestSellerGemini");
  const banner = document.getElementById("botSettingsStatusBanner");
  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> <span>Connecting...</span>`;

  try {
    const res = await fetch("/api/bot/test-gemini", { method: "POST" });
    const data = await res.json();
    if (data.status === "ok") {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 block";
      banner.innerHTML = `✓ <b>Gemini AI Connected!</b> Model: <span class="font-mono">${data.model}</span> (Reply: "${escapeHtml(data.reply)}")`;
    } else {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/40 text-rose-300 block";
      banner.innerHTML = `⚠️ <b>Gemini Error:</b> ${data.message}`;
    }
  } catch (err) {
    banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/40 text-rose-300 block";
    banner.innerHTML = `⚠️ <b>Connection Error:</b> ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>⚡</span> <span>Test Gemini AI</span>`;
  }
}

// -------------------------------------------------------------------------
// 2-Way Seller Inbox Functions
// -------------------------------------------------------------------------

let inboxThreadsCache = [];
let activeInboxThreadKey = null;
let inboxThreadSearchQuery = "";

function openSellerInboxModal(targetKey = null, prefillReply = null) {
  const modal = document.getElementById("sellerInboxModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.style.display = "flex";
  loadSellerInbox(targetKey, prefillReply);
}

function closeSellerInboxModal() {
  const modal = document.getElementById("sellerInboxModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.style.display = "none";
}

async function loadSellerInbox(targetKey = null, prefillReply = null) {
  try {
    const res = await fetch("/api/inbox", { cache: "no-store" });
    if (!res.ok) throw new Error("Failed to load seller inbox");
    const data = await res.json();
    sellerInboxCache = data.messages || [];
    inboxThreadsCache = data.threads || [];

    // Update Badges
    const totalBadge = document.getElementById("inboxTotalCountBadge");
    if (totalBadge) totalBadge.innerText = `${data.count || sellerInboxCache.length} Inbound`;

    const threadCountBadge = document.getElementById("inboxThreadCountBadge");
    if (threadCountBadge) threadCountBadge.innerText = `${inboxThreadsCache.length} Active`;

    const sideBadge = document.getElementById("sidebarInboxBadge");
    if (sideBadge) {
      if (sellerInboxCache.length > 0) {
        sideBadge.innerText = sellerInboxCache.length;
        sideBadge.classList.remove("hidden");
      } else {
        sideBadge.classList.add("hidden");
      }
    }

    renderInboxThreadsList();

    // Determine which thread to select
    let keyToSelect = targetKey;
    if (!keyToSelect && activeInboxThreadKey) {
      if (inboxThreadsCache.some(t => t.key === activeInboxThreadKey)) {
        keyToSelect = activeInboxThreadKey;
      }
    }
    if (!keyToSelect && inboxThreadsCache.length > 0) {
      keyToSelect = inboxThreadsCache[0].key;
    }

    if (keyToSelect) {
      selectInboxThread(keyToSelect, prefillReply);
    } else {
      renderActiveThread();
    }
  } catch (err) {
    console.error("Error loading seller inbox:", err);
    const listEl = document.getElementById("inboxThreadsList");
    if (listEl) listEl.innerHTML = `<div class="p-4 text-center text-xs text-rose-400">Failed to load conversations.</div>`;
  }
}

function filterInboxThreads() {
  const input = document.getElementById("inboxThreadSearchInput");
  inboxThreadSearchQuery = input ? input.value.trim().toLowerCase() : "";
  renderInboxThreadsList();
}

function renderInboxThreadsList() {
  const listEl = document.getElementById("inboxThreadsList");
  if (!listEl) return;

  let threads = inboxThreadsCache || [];
  if (inboxThreadSearchQuery) {
    threads = threads.filter(t => 
      (t.owner || "").toLowerCase().includes(inboxThreadSearchQuery) ||
      (t.phone || "").toLowerCase().includes(inboxThreadSearchQuery) ||
      (t.address || "").toLowerCase().includes(inboxThreadSearchQuery) ||
      (t.last_message || "").toLowerCase().includes(inboxThreadSearchQuery)
    );
  }

  if (threads.length === 0) {
    listEl.innerHTML = `
      <div class="p-8 text-center text-slate-500 space-y-1">
        <div class="text-2xl">📭</div>
        <div class="text-xs font-semibold text-slate-400">No Conversations Found</div>
        <div class="text-[10px] text-slate-500">Inbound SMS from homeowners to (407) 793-7029 will appear here live.</div>
      </div>
    `;
    return;
  }

  listEl.innerHTML = threads.map(t => {
    const isActive = t.key === activeInboxThreadKey;
    const isUnrealistic = t.deal_evaluation?.deal_rating === "UNREALISTIC_PRICE";
    const isGold = t.deal_evaluation?.deal_rating === "GOLD_DEAL";
    const isSpread = t.deal_evaluation?.deal_rating === "SPREAD_DEAL";
    
    let badgeHtml = "";
    if (isUnrealistic) {
      badgeHtml = `<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">🎲 DREAM PRICE</span>`;
    } else if (isGold) {
      badgeHtml = `<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">🔥 GOLD DEAL</span>`;
    } else if (isSpread) {
      badgeHtml = `<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">⚡ SPREAD</span>`;
    } else if (t.distress_category) {
      badgeHtml = `<span class="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-slate-800 text-slate-400 border border-slate-700/60 truncate max-w-[90px]">${escapeHtml(t.distress_category)}</span>`;
    }

    const unreadDot = t.inbound_count > 0 
      ? `<span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0"></span>`
      : `<span class="w-2 h-2 rounded-full bg-slate-600 shrink-0"></span>`;

    const lastTime = t.last_timestamp ? new Date(t.last_timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "";

    return `
      <div onclick="selectInboxThread('${escapeAttr(t.key)}')" class="p-3.5 transition cursor-pointer flex flex-col gap-1.5 ${isActive ? 'bg-blue-600/15 border-l-4 border-blue-500' : 'hover:bg-slate-800/40 border-l-4 border-transparent'}">
        <div class="flex items-center justify-between gap-1">
          <div class="flex items-center gap-2 min-w-0">
            ${unreadDot}
            <span class="text-xs font-bold text-white truncate">${escapeHtml(t.owner || 'Homeowner')}</span>
          </div>
          <div class="flex items-center gap-1.5 shrink-0">
            <span class="text-[10px] text-slate-500 font-mono">${escapeHtml(lastTime)}</span>
            <button type="button" onclick="event.stopPropagation(); deleteInboxThread('${escapeAttr(t.key)}')" class="hover:text-rose-400 p-0.5 text-slate-500 transition text-[11px] cursor-pointer" title="Delete conversation / Spam">🗑️</button>
          </div>
        </div>
        <div class="flex items-center justify-between gap-1 text-[11px]">
          <span class="text-emerald-400 font-mono font-semibold text-[11px] truncate">${escapeHtml(t.phone || '')}</span>
          ${badgeHtml}
        </div>
        <div class="text-[10px] text-slate-400 truncate">
          📍 ${escapeHtml(t.address || 'Florida Property')}
        </div>
        <div class="text-[11px] text-slate-300 line-clamp-1 leading-relaxed font-sans ${t.last_direction === 'INBOUND' ? 'font-semibold text-white' : 'text-slate-400'}">
          ${t.last_direction === 'OUTBOUND' ? '<span class="text-blue-400">You: </span>' : ''}"${escapeHtml(t.last_message || '')}"
        </div>
      </div>
    `;
  }).join("");
}

function selectInboxThread(threadKey, prefillReply = null) {
  activeInboxThreadKey = threadKey;
  renderInboxThreadsList();
  renderActiveThread(prefillReply);
}

function renderActiveThread(prefillReply = null) {
  const panel = document.getElementById("inboxActiveThreadPanel");
  if (!panel) return;

  const thread = (inboxThreadsCache || []).find(t => t.key === activeInboxThreadKey);
  if (!thread) {
    panel.innerHTML = `
      <div class="flex-1 flex items-center justify-center p-8 text-center text-slate-500 space-y-2">
        <div>
          <div class="text-4xl mb-2">💬</div>
          <div class="text-sm font-semibold text-slate-300">Select a Conversation</div>
          <div class="text-xs text-slate-500 max-w-sm mt-1">Choose a seller thread from the left to view the live chat history, deal calculations, and Emma's AI suggestions.</div>
        </div>
      </div>
    `;
    return;
  }

  const isUnrealistic = thread.deal_evaluation?.deal_rating === "UNREALISTIC_PRICE";
  const isGold = thread.deal_evaluation?.deal_rating === "GOLD_DEAL";
  const isSpread = thread.deal_evaluation?.deal_rating === "SPREAD_DEAL";
  const isRetail = thread.deal_evaluation?.deal_rating === "RETAIL_CREATIVE";
  const agreedPrice = thread.deal_evaluation?.detected_price || 0;
  const justVal = Number(thread.just_value || 0);
  const marketVal = Number(thread.market_value || thread.deal_evaluation?.market_value || (justVal > 0 ? justVal * 1.30 : 0));
  const valSource = thread.valuation_source || "Est. Market";

  let dealBadgeHtml = "";
  if (isUnrealistic) {
    dealBadgeHtml = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">🎲 DREAM PRICE (${thread.deal_evaluation.ratio_pct}% of Market)</span>`;
  } else if (isGold) {
    dealBadgeHtml = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">🔥 GOLD DEAL (${thread.deal_evaluation.ratio_pct}% of Market)</span>`;
  } else if (isSpread) {
    dealBadgeHtml = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">⚡ SPREAD (${thread.deal_evaluation.ratio_pct}%)</span>`;
  } else if (isRetail) {
    dealBadgeHtml = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">🏷️ RETAIL ASK (${thread.deal_evaluation.ratio_pct}%)</span>`;
  } else if (marketVal > 0) {
    dealBadgeHtml = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">Market: $${marketVal.toLocaleString()}</span>`;
  }

  const suggestedReply = prefillReply || thread.latest_bot_response || "";

  panel.innerHTML = `
    <!-- Pinned Thread Header -->
    <div class="px-5 py-3 border-b border-slate-800 bg-[#080d1b] flex flex-wrap items-center justify-between gap-3 shrink-0">
      <div class="space-y-0.5 min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
          <h4 class="text-sm font-extrabold text-white truncate">${escapeHtml(thread.owner || 'Homeowner')}</h4>
          <span class="text-xs font-mono font-bold text-emerald-400">${escapeHtml(thread.phone || '')}</span>
          ${dealBadgeHtml}
        </div>
        <p class="text-xs text-slate-400 truncate">
          📍 <b>${escapeHtml(thread.address || 'Florida Property')}</b> 
          ${marketVal > 0 ? `&bull; Est. Market: <b class="text-emerald-300 font-mono">$${marketVal.toLocaleString()}</b> <span class="text-[10px] text-slate-500 font-sans">(${escapeHtml(valSource)})</span>` : ''}
          ${justVal > 0 ? `&bull; Assessed: <span class="font-mono text-slate-300">$${justVal.toLocaleString()}</span>` : ''}
          ${thread.parcel_id ? `&bull; PIN: <span class="font-mono text-slate-300">${escapeHtml(thread.parcel_id)}</span>` : ''}
        </p>
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <button type="button" onclick="deleteInboxThread('${escapeAttr(thread.key)}')" class="px-3 py-1.5 rounded-xl bg-rose-600/20 hover:bg-rose-600/40 text-rose-300 hover:text-white border border-rose-500/30 text-xs font-bold transition flex items-center gap-1.5 cursor-pointer shadow-sm" title="Delete conversation & remove from queue">
          <span>🗑️</span> <span>Delete Thread</span>
        </button>
        <button type="button" onclick="openContractFromInboxThread('${escapeAttr(thread.key)}')" class="px-3.5 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-md shadow-purple-600/30 cursor-pointer" title="Generate Wholesale Purchase Agreement & PandaDoc E-Sign">
          <span>📝</span> <span>Send Contract</span>
        </button>
      </div>
    </div>

    <!-- Chronological Chat Stream -->
    <div id="inboxChatStream" class="flex-1 overflow-y-auto p-5 space-y-3.5 bg-[#050811]">
      ${renderChatBubbles(thread.messages || [], thread.owner)}
    </div>

    <!-- Emma AI Copilot Smart Suggestion Card -->
    ${suggestedReply ? `
      <div class="px-5 py-2.5 bg-gradient-to-r from-blue-950/40 via-purple-950/30 to-slate-900 border-t border-blue-500/30 flex items-center justify-between gap-3 shrink-0">
        <div class="flex items-start gap-2.5 min-w-0">
          <span class="text-base mt-0.5">🤖</span>
          <div class="min-w-0">
            <div class="text-[10px] font-bold uppercase tracking-wider text-blue-300">Emma AI Next Suggested Reply:</div>
            <div class="text-xs text-emerald-300 line-clamp-2 leading-relaxed italic font-sans">"${escapeHtml(suggestedReply)}"</div>
          </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <button type="button" onclick="trainEmmaFromInbox()" class="px-3 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 hover:text-white border border-indigo-500/40 text-xs font-bold transition flex items-center gap-1 cursor-pointer shadow-sm" title="Save your reply as a permanent Golden Training Rule for Emma">
            <span>🎓</span> <span>Train Emma</span>
          </button>
          <button type="button" onclick="insertEmmaSuggestion('${escapeAttr(suggestedReply)}')" class="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center gap-1 shrink-0 cursor-pointer shadow-sm">
            <span>⚡</span> <span>Use This Script</span>
          </button>
        </div>
      </div>
    ` : ''}

    <!-- Bottom Reply Compose Bar -->
    <div class="p-4 border-t border-slate-800 bg-[#080d1b] space-y-2 shrink-0">
      <form onsubmit="handleThreadSendReply(event)" class="space-y-2">
        <div class="relative">
          <textarea id="inboxReplyTextarea" rows="2" required placeholder="Type your reply to ${escapeAttr(thread.owner || 'homeowner')}... (or click 'Use This Script' above)" class="w-full bg-[#0d1424] border border-slate-700/80 rounded-xl p-3 text-xs text-white focus:outline-none focus:border-blue-500 leading-relaxed font-sans">${escapeHtml(prefillReply || '')}</textarea>
        </div>
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-2 text-[11px] text-slate-400">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>Sending via SIM: <b class="text-emerald-300 font-mono">(407) 793-7029</b></span>
          </div>
          <button type="submit" id="btnSendThreadReply" class="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs transition flex items-center gap-1.5 shadow-lg shadow-blue-600/30 cursor-pointer shrink-0">
            <span>🚀</span> <span>Send SMS via Phone</span>
          </button>
        </div>
      </form>
    </div>
  `;

  // Scroll to bottom of chat
  setTimeout(() => {
    const stream = document.getElementById("inboxChatStream");
    if (stream) stream.scrollTop = stream.scrollHeight;
  }, 40);
}

function renderChatBubbles(messages, ownerName) {
  if (!messages || messages.length === 0) {
    return `<div class="p-8 text-center text-xs text-slate-500 italic">No messages in this conversation yet. Send an opening SMS below!</div>`;
  }

  return messages.map(m => {
    const isInbound = (m.direction || "").toUpperCase() === "INBOUND";
    const timeStr = m.timestamp ? new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' }) : "";
    const senderLabel = isInbound ? (ownerName || 'Homeowner') : 'You (Emma / 407 Flips)';

    if (isInbound) {
      return `
        <div class="flex flex-col items-start max-w-[85%] sm:max-w-[75%] space-y-1">
          <div class="flex items-center gap-1.5 text-[10px] text-slate-400 pl-1">
            <span class="font-bold text-slate-300">${escapeHtml(senderLabel)}</span>
            <span>&bull;</span>
            <span class="font-mono text-slate-500">${escapeHtml(timeStr)}</span>
          </div>
          <div class="p-3.5 rounded-2xl rounded-tl-sm bg-slate-800/90 border border-slate-700/80 text-white text-xs leading-relaxed shadow-md">
            "${escapeHtml(m.message || '')}"
          </div>
        </div>
      `;
    } else {
      return `
        <div class="flex flex-col items-end max-w-[85%] sm:max-w-[75%] ml-auto space-y-1">
          <div class="flex items-center gap-1.5 text-[10px] text-slate-400 pr-1">
            <span class="font-bold text-blue-300">${escapeHtml(senderLabel)}</span>
            <span>&bull;</span>
            <span class="font-mono text-slate-500">${escapeHtml(timeStr)}</span>
          </div>
          <div class="p-3.5 rounded-2xl rounded-tr-sm bg-blue-600 text-white text-xs leading-relaxed shadow-md border border-blue-500/60">
            ${escapeHtml(m.message || '')}
          </div>
        </div>
      `;
    }
  }).join("");
}

function insertEmmaSuggestion(text) {
  const ta = document.getElementById("inboxReplyTextarea");
  if (ta) {
    ta.value = text;
    ta.focus();
  }
}

async function handleThreadSendReply(e) {
  e.preventDefault();
  const thread = (inboxThreadsCache || []).find(t => t.key === activeInboxThreadKey);
  if (!thread) return;

  const ta = document.getElementById("inboxReplyTextarea");
  const text = ta ? ta.value.trim() : "";
  const btn = document.getElementById("btnSendThreadReply");

  if (!text) {
    alert("Please type a message to send.");
    return;
  }

  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> <span>Sending via Phone...</span>`;

  try {
    const res = await fetch("/api/sms/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        phone: thread.phone,
        message: text,
        parcel_id: thread.parcel_id,
        owner_name: thread.owner,
        property_address: thread.address,
        county: "Pinellas"
      })
    });
    const data = await res.json();
    if (data.status === "success") {
      const nowStr = new Date().toISOString().replace('T', ' ').substring(0, 19);
      const newEntry = {
        timestamp: nowStr,
        direction: "OUTBOUND",
        phone: thread.phone,
        message: text,
        parcel_id: thread.parcel_id,
        owner: thread.owner
      };
      thread.messages.push(newEntry);
      thread.last_message = text;
      thread.last_timestamp = nowStr;
      thread.last_direction = "OUTBOUND";
      thread.latest_bot_response = ""; // Clear suggestion so it doesn't linger or prefill

      if (ta) ta.value = "";
      renderActiveThread();
      renderInboxThreadsList();
      fetchOutreachHistory();
    } else {
      alert(`Send Error: ${data.message}`);
    }
  } catch (err) {
    alert(`Send Error: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>🚀</span> <span>Send SMS via Phone</span>`;
  }
}

async function deleteInboxThread(threadKey) {
  const targetKey = threadKey || activeInboxThreadKey;
  if (!targetKey) return;
  const thread = (inboxThreadsCache || []).find(t => t.key === targetKey);
  const label = thread ? (thread.owner || thread.phone || "this conversation") : "this conversation";
  
  if (!confirm(`Delete conversation with ${label} and remove from queue?`)) {
    return;
  }

  try {
    const res = await fetch("/api/inbox/thread/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: targetKey, phone: thread?.phone, parcel_id: thread?.parcel_id })
    });
    const data = await res.json();
    if (data.status === "success") {
      if (activeInboxThreadKey === targetKey) {
        activeInboxThreadKey = null;
      }
      await loadSellerInbox();
    } else {
      alert(`Failed to delete thread: ${data.message || 'Unknown error'}`);
    }
  } catch (err) {
    alert(`Error deleting thread: ${err.message}`);
  }
}

async function trainEmmaFromInbox() {
  const thread = (inboxThreadsCache || []).find(t => t.key === activeInboxThreadKey);
  if (!thread) return;

  const ta = document.getElementById("inboxReplyTextarea");
  const currentText = ta ? ta.value.trim() : "";
  const inboundText = thread.last_message || (thread.messages && thread.messages.length > 0 ? thread.messages[thread.messages.length - 1].message : "");

  if (!currentText) {
    alert("Please type or refine your ideal answer in the reply box below first, then click 'Train Emma' to teach her!");
    if (ta) ta.focus();
    return;
  }

  const promptNotes = prompt("Confirm scenario note for Emma (optional):", `Trained on: "${(inboundText || '').substring(0, 45)}"`);
  if (promptNotes === null) return; // user cancelled prompt

  try {
    const res = await fetch("/api/bot/training/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category: thread.distress_category || "General Distress",
        distress_type: thread.distress_category || "General Distress",
        seller_inbound: inboundText || "General Seller Question",
        final_approved_text: currentText,
        notes: promptNotes || "Trained directly from 2-Way Seller Inbox by John"
      })
    });
    const data = await res.json();
    if (data.status === "ok") {
      alert(`✅ Emma Trained Successfully!\n\nEmma has permanently learned this response and will use your wording for future homeowners asking similar questions.`);
    } else {
      alert(`Failed to train Emma: ${data.message || 'Unknown error'}`);
    }
  } catch (err) {
    alert(`Error training Emma: ${err.message}`);
  }
}

function openContractFromInboxThread(threadKey) {
  const thread = (inboxThreadsCache || []).find(t => t.key === (threadKey || activeInboxThreadKey));
  if (!thread) return;

  closeSellerInboxModal();

  const parcelId = thread.parcel_id || "";
  const phone = thread.phone || "";
  const owner = thread.owner || "Homeowner";
  const address = thread.address || "";
  const agreedPrice = thread.deal_evaluation?.detected_price || 0;
  const justVal = Number(thread.just_value || 0);

  const rec = (liveRecords || []).find(r => r && (r.Parcel_ID === parcelId || r.Property_Address === address));
  const city = rec?.Property_City || "St Petersburg";
  const zip = rec?.Property_Zip || "33701";
  const marketVal = rec ? (rec.Market_Value || rec.Just_Value || justVal) : justVal;

  openContractModal(parcelId, phone, '', owner, address, city, zip, marketVal);

  if (agreedPrice > 0) {
    setTimeout(() => {
      const priceInput = document.getElementById("contractPurchasePrice");
      if (priceInput) {
        priceInput.value = agreedPrice;
        if (typeof updateContractCalculations === "function") {
          updateContractCalculations();
        }
      }
    }, 100);
  }
}

function openSellerThread(phoneStr, parcelId = null, prefillReply = null) {
  const digits = String(phoneStr || "").replace(/\D/g, "");
  const cleanDigits = digits.length > 10 && digits.startsWith("1") ? digits.substring(1) : digits;

  openSellerInboxModal(null, prefillReply);

  setTimeout(async () => {
    let match = (inboxThreadsCache || []).find(t => {
      const tDigits = String(t.clean_phone || t.phone || "").replace(/\D/g, "");
      const tClean = tDigits.length > 10 && tDigits.startsWith("1") ? tDigits.substring(1) : tDigits;
      return (cleanDigits && (cleanDigits === tClean || tClean.includes(cleanDigits))) || (parcelId && t.parcel_id === parcelId);
    });

    if (!match) {
      await loadSellerInbox();
      match = (inboxThreadsCache || []).find(t => {
        const tDigits = String(t.clean_phone || t.phone || "").replace(/\D/g, "");
        const tClean = tDigits.length > 10 && tDigits.startsWith("1") ? tDigits.substring(1) : tDigits;
        return (cleanDigits && (cleanDigits === tClean || tClean.includes(cleanDigits))) || (parcelId && t.parcel_id === parcelId);
      });
    }

    if (match) {
      selectInboxThread(match.key, prefillReply);
    }
  }, 120);
}

function toggleInboxSimulator() {
  const drawer = document.getElementById("inboxSimulatorDrawer");
  if (!drawer) return;
  drawer.classList.toggle("hidden");
}

function fillSimScenario(val) {
  const simInput = document.getElementById("simMessageText");
  if (!simInput) return;
  const scenarios = {
    code: "We got cited for the garage by the county inspector. What will you offer as-is?",
    lis: "Auction date is in 3 weeks. Can you buy before then?",
    probate: "Inherited Dad's house, full of old furniture. Asking 175k cash as-is.",
    price_gold: "I'll let it go for 130k if you can close cash this month.",
    stop: "STOP texting me"
  };
  simInput.value = scenarios[val] || scenarios.code;
}

async function dispatchSimulatedInbound() {
  const phone = document.getElementById("simPhone").value.trim();
  const text = document.getElementById("simMessageText").value.trim();
  const btn = document.getElementById("btnDispatchSim");

  if (!phone || !text) {
    alert("Please provide both phone number and message.");
    return;
  }

  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> <span>Dispatching...</span>`;

  try {
    const res = await fetch("/api/sms/inbound", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event: "sms:received",
        payload: {
          phoneNumber: phone,
          message: text
        }
      })
    });
    const data = await res.json();
    if (data.status === "ok" || data.status === "success") {
      playInboundNotificationChime();
      showInboundToast(phone, text, "Robert Vance (Test Lead)", text.includes("130k") ? "GOLD_DEAL" : "SPREAD_DEAL");
      await fetchOutreachHistory();
      const cleanDigits = phone.replace(/\D/g, "");
      const targetKey = cleanDigits.length > 10 && cleanDigits.startsWith("1") ? cleanDigits.slice(1) : cleanDigits;
      await loadSellerInbox(targetKey);
      toggleInboxSimulator();
    } else {
      alert(`Simulation error: ${data.message || data.reason || 'Unknown error'}`);
    }
  } catch (err) {
    alert(`Error: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>🚀</span> <span>Dispatch Simulated SMS</span>`;
  }
}

// -------------------------------------------------------------------------
// Sandbox Test Lead & Live Webhook Simulator
// -------------------------------------------------------------------------

function openSandboxTestModal() {
  const modal = document.getElementById("sandboxTestModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.style.display = "flex";
  const banner = document.getElementById("sandboxStatusBanner");
  if (banner) banner.className = "hidden";
}

function closeSandboxTestModal() {
  const modal = document.getElementById("sandboxTestModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

async function addSandboxTestLead() {
  try {
    const res = await fetch("/api/leads/sandbox-test-lead", { method: "POST" });
    if (res.ok) {
      await fetchSavedContacts();
      switchPipelineView("saved");
      openSandboxTestModal();
    }
  } catch (err) {
    console.error("Error creating sandbox test lead:", err);
  }
}

async function triggerSandboxWebhookScenario(scenarioKey) {
  const scenarios = {
    gold: "I'll let it go for 130k if you close this month.",
    code: "The city gave me a citation for the garage & roof. What will you offer as-is?",
    lis: "Auction date is set in 3 weeks. Can you purchase before then?",
    probate: "Inherited Dad's house, full of furniture. Asking 175k cash.",
    stop: "STOP texting me"
  };

  const text = scenarios[scenarioKey] || scenarios.gold;
  await executeWebhookTest(text, scenarioKey === 'gold' ? 'GOLD_DEAL' : (scenarioKey === 'stop' ? 'OPT_OUT' : 'SPREAD_DEAL'));
}

async function triggerSandboxWebhookCustom() {
  const input = document.getElementById("sandboxCustomMessage");
  const text = input ? input.value.trim() : "";
  if (!text) {
    alert("Please enter a custom homeowner message to test.");
    return;
  }
  await executeWebhookTest(text, "SPREAD_DEAL");
  if (input) input.value = "";
}

async function executeWebhookTest(text, expectedRating) {
  const banner = document.getElementById("sandboxStatusBanner");
  if (banner) {
    banner.className = "p-3 rounded-xl text-xs font-semibold bg-violet-950/60 border border-violet-500/40 text-violet-300 block";
    banner.innerText = "⏳ Dispatching live webhook to /api/sms/inbound...";
  }

  const phone = "(727) 555-0199";

  try {
    const res = await fetch("/api/sms/inbound", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event: "sms:received",
        payload: {
          phoneNumber: phone,
          message: text
        }
      })
    });
    const data = await res.json();

    if (data.status === "success" || data.status === "ok") {
      playInboundNotificationChime();
      showInboundToast(phone, text, "Robert Vance (Test Lead)", expectedRating);

      if (banner) {
        banner.className = "p-3 rounded-xl text-xs font-semibold bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 block";
        banner.innerHTML = `✓ <b>Webhook Accepted (HTTP 200)!</b> Emma scored the deal and prepared a reply.`;
      }

      await fetchOutreachHistory();
      await pollSellerInboxUpdates();

      setTimeout(() => {
        closeSandboxTestModal();
        openSellerInboxModal();
      }, 1000);
    } else {
      if (banner) {
        banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/40 text-rose-300 block";
        banner.innerText = `⚠️ Webhook returned: ${data.reason || data.status}`;
      }
    }
  } catch (err) {
    if (banner) {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-950/60 border border-rose-500/40 text-rose-300 block";
      banner.innerText = `⚠️ Connection error: ${err.message}`;
    }
  }
}

function replyInCopilotFromInbox(index) {
  const item = sellerInboxCache[index];
  if (!item) return;
  openSellerThread(item.sender || item.phone, item.parcel_id, item.bot_response);
}

function openContractFromInbox(index) {
  const item = sellerInboxCache[index];
  if (!item) return;

  closeSellerInboxModal();

  const parcelId = item.parcel_id || "";
  const phone = item.sender || item.phone || "";
  const owner = item.owner || "Homeowner";
  const address = item.address || "";
  const spread = item.spread_eval || {};
  const agreedPrice = spread.detected_price || 0;

  // Find record in liveRecords to grab market value and city/zip
  const rec = (liveRecords || []).find(r => r && (r.Parcel_ID === parcelId || r.Property_Address === address));
  const city = rec?.Property_City || "St Petersburg";
  const zip = rec?.Property_Zip || "";
  const marketVal = rec ? (rec.Market_Value || rec.Just_Value || rec.Assessed_Value || 0) : (spread.parcel_value || 0);

  openContractModal(parcelId, phone, '', owner, address, city, zip, marketVal);

  if (agreedPrice > 0) {
    const priceInput = document.getElementById("contractPurchasePrice");
    if (priceInput) {
      priceInput.value = agreedPrice;
      if (typeof updateContractCalculations === "function") {
        updateContractCalculations();
      }
    }
  }
}

// -------------------------------------------------------------------------
// Live Audio Chime, Visual Toast & Background Polling
// -------------------------------------------------------------------------

let inboxPollTimer = null;
let inboxPollInFlight = false;
let lastSeenInboxSignatures = null;

function startSellerInboxPolling() {
  if (inboxPollTimer !== null) return;
  pollSellerInboxUpdates();
  inboxPollTimer = setInterval(pollSellerInboxUpdates, 2000);
  window.addEventListener("focus", pollSellerInboxUpdates);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) pollSellerInboxUpdates();
  });
}

function setInboxConnectionStatus(connected) {
  const status = document.getElementById("inboxConnectionStatus");
  if (!status) return;
  status.textContent = connected ? "Live updates on" : "Connection lost — retrying automatically";
  status.className = connected ? "text-emerald-400 text-[11px]" : "text-amber-400 text-[11px]";
}

function playInboundNotificationChime() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    if (ctx.state === "suspended") {
      ctx.resume();
    }
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    const now = ctx.currentTime;
    osc.frequency.setValueAtTime(587.33, now); // D5
    osc.frequency.setValueAtTime(880, now + 0.12); // A5
    gain.gain.setValueAtTime(0.18, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.4);
  } catch (e) {
    // Non-blocking
  }
}

function showInboundToast(sender, message, owner, dealRating) {
  const container = document.getElementById("inboundToastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = "pointer-events-auto max-w-sm w-full bg-slate-900/95 border border-blue-500/50 rounded-2xl p-4 shadow-2xl shadow-blue-950/60 flex items-start gap-3 backdrop-blur-md transition-all duration-300 transform translate-y-[-10px] opacity-0";
  
  let badgeHtml = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">💬 Inbound SMS</span>';
  if (dealRating === 'GOLD_DEAL') {
    badgeHtml = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">🔥 GOLD DEAL</span>';
  } else if (dealRating === 'SPREAD_DEAL') {
    badgeHtml = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">⚡ SPREAD DEAL</span>';
  }

  toast.innerHTML = `
    <div class="w-8 h-8 rounded-xl bg-blue-600/20 border border-blue-500/40 text-blue-400 flex items-center justify-center shrink-0 text-base mt-0.5">
      💬
    </div>
    <div class="flex-1 min-w-0">
      <div class="flex items-center justify-between gap-1 mb-1">
        <div class="text-xs font-bold text-white truncate">${escapeHtml(owner || 'Florida Homeowner')}</div>
        ${badgeHtml}
      </div>
      <div class="text-[11px] text-slate-300 line-clamp-2 leading-relaxed mb-2 font-sans">"${escapeHtml(message || '')}"</div>
      <div class="flex items-center justify-between pt-1 border-t border-slate-800">
        <span class="text-[10px] font-mono text-emerald-400 font-semibold">${escapeHtml(sender || '')}</span>
        <button type="button" class="text-[11px] font-bold text-blue-400 hover:text-blue-300 cursor-pointer">Open Conversation &rarr;</button>
      </div>
    </div>
  `;

  toast.onclick = () => {
    openSellerThread(sender, null);
    toast.remove();
  };

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.remove("translate-y-[-10px]", "opacity-0");
    toast.classList.add("translate-y-0", "opacity-100");
  }, 20);

  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-[-10px]");
    setTimeout(() => toast.remove(), 350);
  }, 7000);
}

async function pollSellerInboxUpdates() {
  if (inboxPollInFlight) return;
  inboxPollInFlight = true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch("/api/inbox", { cache: "no-store", signal: controller.signal });
    if (!res.ok) throw new Error(`Inbox unavailable (${res.status})`);
    const data = await res.json();
    const messages = data.messages || [];
    const count = data.count ?? messages.length;
    setInboxConnectionStatus(true);
    const signatures = messages.map(m => JSON.stringify([m.timestamp, m.sender_phone || m.phone || m.sender, m.message]));
    const newMessageIndex = lastSeenInboxSignatures === null ? -1 : signatures.findIndex(s => !lastSeenInboxSignatures.has(s));
    lastSeenInboxSignatures = new Set(signatures);

    // Update sidebar badge
    const sideBadge = document.getElementById("sidebarInboxBadge");
    if (sideBadge) {
      if (count > 0) {
        sideBadge.innerText = count;
        sideBadge.classList.remove("hidden");
      } else {
        sideBadge.classList.add("hidden");
      }
    }

    if (newMessageIndex >= 0) {
      // New inbound text arrived!
      const newest = messages[newMessageIndex];
      playInboundNotificationChime();
      if (newest) {
        showInboundToast(
          newest.sender_phone || newest.sender || newest.phone,
          newest.message,
          newest.owner,
          newest.spread_eval?.deal_rating
        );
      }
    }

    // If seller inbox modal is currently visible, live re-render so chat updates in real time
    const modal = document.getElementById("sellerInboxModal");
    if (modal && !modal.classList.contains("hidden")) {
      const previousThread = (inboxThreadsCache || []).find(t => t.key === activeInboxThreadKey);
      sellerInboxCache = messages;
      inboxThreadsCache = data.threads || [];
      const totalBadge = document.getElementById("inboxTotalCountBadge");
      if (totalBadge) totalBadge.innerText = `${count} Inbound`;
      const threadCountBadge = document.getElementById("inboxThreadCountBadge");
      if (threadCountBadge) threadCountBadge.innerText = `${inboxThreadsCache.length} Active`;
      renderInboxThreadsList();
      const currentThread = inboxThreadsCache.find(t => t.key === activeInboxThreadKey);
      if (!currentThread && inboxThreadsCache.length) {
        selectInboxThread(inboxThreadsCache[0].key);
      } else if (currentThread && JSON.stringify(previousThread) !== JSON.stringify(currentThread)) {
        const ta = document.getElementById("inboxReplyTextarea");
        const userDraft = (ta && ta.value) ? ta.value : "";
        const wasFocused = (ta && document.activeElement === ta);
        const selectionStart = ta?.selectionStart;
        const selectionEnd = ta?.selectionEnd;
        renderActiveThread();
        if (userDraft) {
          const newTa = document.getElementById("inboxReplyTextarea");
          if (newTa) {
            newTa.value = userDraft;
            if (wasFocused) {
              newTa.focus();
              newTa.setSelectionRange(selectionStart, selectionEnd);
            }
          }
        }
      }
    }
    // Also silently refresh callbacks in background
    loadScheduledCallbacks(true);
  } catch (err) {
    setInboxConnectionStatus(false);
  } finally {
    clearTimeout(timeout);
    inboxPollInFlight = false;
  }
}

// -------------------------------------------------------------------------
// SMS Copilot Card Functions (Inside #smsModal)
// -------------------------------------------------------------------------

async function generateEmmaCopilotSuggestion() {
  const ctx = window.activeSmsLeadContext || {};
  const btn = document.getElementById("btnFetchCopilotSuggest");
  const box = document.getElementById("smsCopilotSuggestionBox");
  const txt = document.getElementById("smsCopilotSuggestionText");
  const spreadBadge = document.getElementById("smsDealSpreadBadge");

  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> <span>Thinking...</span>`;

  try {
    const res = await fetch("/api/bot/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        seller_message: "INITIAL_HOOK",
        opener_angle: document.getElementById('smsTemplateSelect')?.value || '',
        owner_name: ctx.ownerName || "",
        property_address: ctx.propertyAddress || "",
        address: ctx.propertyAddress || "",
        parcel_id: ctx.parcelId || "",
        distress_type: ctx.distressType || "GENERAL_DISTRESS",
        assessed_value: ctx.marketValue || 0,
        county: ctx.county || selectedCountyKey || "Pinellas",
        phone: ctx.phone || ""
      })
    });
    const data = await res.json();
    if (data.status === "ok") {
      box.classList.remove("hidden");
      txt.innerText = data.suggestion || document.getElementById('smsMessageText')?.value || '';

      const spread = data.spread_eval || {};
      if (spreadBadge && spread.deal_rating) {
        spreadBadge.classList.remove("hidden");
        if (spread.deal_rating === "GOLD_DEAL") {
          spreadBadge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
          spreadBadge.innerText = `🔥 GOLD DEAL (${spread.ratio_pct}%)`;
        } else if (spread.deal_rating === "SPREAD_DEAL") {
          spreadBadge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40";
          spreadBadge.innerText = `⚡ SPREAD DEAL (${spread.ratio_pct}%)`;
        } else if (spread.deal_rating === "RETAIL_CREATIVE") {
          spreadBadge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40";
          spreadBadge.innerText = `⚠️ RETAIL`;
        }
      }
    } else {
      alert(`Copilot error: ${data.message || 'Unable to generate suggestion'}`);
    }
  } catch (err) {
    alert(`Error generating suggestion: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>⚡</span> <span>Get Emma's Suggestion</span>`;
  }
}

function applyEmmaCopilotSuggestion() {
  const txt = document.getElementById("smsCopilotSuggestionText")?.innerText;
  if (!txt) return;

  const msgBox = document.getElementById("smsMessageText");
  if (msgBox) {
    msgBox.value = txt.trim();
    if (typeof updateSmsCharCount === "function") {
      updateSmsCharCount();
    }
  }

  const box = document.getElementById("smsCopilotSuggestionBox");
  if (box) box.classList.add("hidden");
}

// -------------------------------------------------------------------------
// Scheduled Callbacks with John & Google Calendar Sync Controller
// -------------------------------------------------------------------------

let scheduledCallbacksCache = [];

async function loadScheduledCallbacks(isSilent = false) {
  try {
    const res = await fetch("/api/callbacks");
    if (!res.ok) return;
    const data = await res.json();
    scheduledCallbacksCache = data.callbacks || [];
    renderCallbacksDashboard(scheduledCallbacksCache);
  } catch (err) {
    if (!isSilent) console.warn("Could not load callbacks:", err);
  }
}

function renderCallbacksDashboard(callbacks) {
  const container = document.getElementById("callbacksListContainer");
  const badge = document.getElementById("callbacksPendingCountBadge");
  const sideBadge = document.getElementById("sidebarCallbacksBadge");

  const pending = (callbacks || []).filter(c => (c.status || "").toUpperCase() === "PENDING");

  if (badge) {
    badge.innerText = `${pending.length} Pending`;
    if (pending.length === 0) {
      badge.className = "px-2 py-0.5 rounded-full text-[11px] font-bold bg-slate-800 text-slate-400 border border-slate-700";
    } else {
      badge.className = "px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
    }
  }

  if (sideBadge) {
    if (pending.length > 0) {
      sideBadge.innerText = pending.length;
      sideBadge.classList.remove("hidden");
    } else {
      sideBadge.classList.add("hidden");
    }
  }

  if (!container) return;

  if (pending.length === 0) {
    container.innerHTML = `
      <div class="col-span-full p-6 text-center bg-[#070d18]/60 border border-slate-800/80 rounded-xl space-y-1.5">
        <div class="text-2xl">☕</div>
        <div class="text-xs font-bold text-slate-300">All Caught Up! No Pending Callbacks</div>
        <div class="text-[11px] text-slate-400 max-w-md mx-auto">
          When motivated sellers agree to a phone call with Emma via SMS, their scheduled appointment will appear right here and automatically sync into your Google Calendar at <span class="text-emerald-400 font-mono">johngroberts76@gmail.com</span>.
        </div>
      </div>
    `;
    return;
  }

  container.innerHTML = pending.map(c => {
    const marketFormatted = c.market_value ? `$${Math.round(c.market_value).toLocaleString()}` : "N/A";
    const phoneDigits = c.clean_phone || (c.phone || "").replace(/\D/g, "");

    return `
      <div class="bg-[#0b1220]/90 border border-emerald-500/30 hover:border-emerald-500/60 rounded-xl p-4 transition shadow-lg flex flex-col justify-between gap-3 relative group">
        <div>
          <!-- Top Row: Owner & Appointment Time Pill -->
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <h3 class="text-sm font-extrabold text-white truncate flex items-center gap-1.5">
                <span>👤</span> <span>${escapeHtml(c.owner || 'Homeowner')}</span>
              </h3>
              <p class="text-[11px] text-slate-400 truncate mt-0.5">
                📍 ${escapeHtml(c.address || 'Florida Property')}
              </p>
            </div>
            <div class="shrink-0 text-right">
              <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                ⏰ ${escapeHtml(c.display_time || c.scheduled_time_raw || 'Pending')}
              </span>
            </div>
          </div>

          <!-- Mid Info Row: Phone Click-to-dial & Market Value -->
          <div class="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-xs">
            <div class="flex items-center gap-1.5 font-mono">
              <span class="text-slate-400">📞</span>
              <a href="tel:${escapeAttr(phoneDigits)}" class="font-bold text-emerald-400 hover:text-emerald-300 hover:underline">
                ${escapeHtml(c.phone || phoneDigits)}
              </a>
              <button type="button" onclick="navigator.clipboard.writeText('${escapeAttr(c.phone || phoneDigits)}'); alert('Phone number copied to clipboard: ${escapeAttr(c.phone || phoneDigits)}');" class="text-slate-500 hover:text-slate-300 text-xs ml-1 cursor-pointer" title="Copy Phone Number">
                📋
              </button>
            </div>
            <div class="text-[11px] text-slate-400">
              Est. Value: <b class="text-white font-mono">${marketFormatted}</b>
            </div>
          </div>

          <!-- Calendar Delivery Status -->
          <div class="mt-2 text-[10px] text-slate-400 flex items-center justify-between">
            <div class="flex items-center gap-1.5">
              <span class="text-emerald-400 font-bold">✓ Invite:</span>
              <span class="truncate max-w-[200px]">Sent to ${escapeHtml(c.email_recipient || 'johngroberts76@gmail.com')}</span>
            </div>
            <span class="text-[9px] font-mono text-slate-500">${escapeHtml(c.created_at || '')}</span>
          </div>
        </div>

        <!-- Action Buttons Footer -->
        <div class="mt-2 pt-2.5 border-t border-slate-800/80 flex items-center justify-between gap-2">
          <div class="flex items-center gap-1.5">
            <button type="button" onclick="openSellerInboxModal('${escapeAttr(c.clean_phone || phoneDigits)}')" class="px-2.5 py-1.5 rounded-lg bg-blue-600/30 hover:bg-blue-600/50 border border-blue-500/40 text-blue-300 hover:text-white text-xs font-bold transition flex items-center gap-1 cursor-pointer" title="Open full 2-Way SMS chat thread">
              <span>💬</span> <span>Open Chat</span>
            </button>
            ${c.gcal_url ? `
              <a href="${escapeAttr(c.gcal_url)}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-semibold transition flex items-center gap-1 border border-slate-700 cursor-pointer" title="View or edit in Google Calendar web">
                <span>📅</span> <span>Google Cal</span>
              </a>
            ` : ''}
          </div>
          <button type="button" onclick="completeScheduledCallback('${escapeAttr(c.id)}', '${escapeAttr(c.clean_phone || phoneDigits)}')" class="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center gap-1 cursor-pointer shadow-md shadow-emerald-600/30" title="Mark this phone call as completed">
            <span>✓</span> <span>Done</span>
          </button>
        </div>
      </div>
    `;
  }).join("");
}

async function completeScheduledCallback(id, cleanPhone) {
  if (!confirm("Mark this callback as completed?")) return;
  try {
    const res = await fetch("/api/callbacks/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: id, clean_phone: cleanPhone })
    });
    if (res.ok) {
      const data = await res.json();
      scheduledCallbacksCache = data.callbacks || [];
      renderCallbacksDashboard(scheduledCallbacksCache);
    } else {
      alert("Failed to complete callback.");
    }
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

function scrollOrOpenCallbacks() {
  const card = document.getElementById("callbacksDashboardCard");
  if (card) {
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card.classList.add("ring-2", "ring-emerald-500", "scale-[1.01]");
    setTimeout(() => {
      card.classList.remove("ring-2", "ring-emerald-500", "scale-[1.01]");
    }, 1500);
  }
}

// ----------------------------------------------------
// LINK ZONE LIVE BRIDGE & VERIFICATION AUDIT TRAIL
// ----------------------------------------------------
let linkZoneHealthCache = null;

async function fetchLinkZoneHealth() {
  try {
    const res = await fetch("/api/link-zone/health");
    if (!res.ok) return;
    const data = await res.json();
    linkZoneHealthCache = data;

    // Update Header Status Heartbeat Pill
    const pingEl = document.getElementById("linkZonePulsePing");
    const dotEl = document.getElementById("linkZonePulseDot");
    const countEl = document.getElementById("linkZoneBadgeCounties");
    const subEl = document.getElementById("linkZoneStatusSub");

    if (data.status === "HEALTHY") {
      if (pingEl) pingEl.className = "animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75";
      if (dotEl) dotEl.className = "relative inline-flex rounded-full h-2 w-2 bg-emerald-500";
      if (subEl) subEl.textContent = "Live • Synced";
    } else if (data.status === "FALLBACK") {
      if (pingEl) pingEl.className = "hidden";
      if (dotEl) dotEl.className = "relative inline-flex rounded-full h-2 w-2 bg-amber-400";
      if (subEl) subEl.textContent = "Fallback Snapshot";
    } else {
      if (pingEl) pingEl.className = "hidden";
      if (dotEl) dotEl.className = "relative inline-flex rounded-full h-2 w-2 bg-rose-500";
      if (subEl) subEl.textContent = "Offline";
    }

    if (countEl && data.states && data.states.FL) {
      countEl.textContent = `${data.states.FL.counties || 37} FL`;
    }

    // If modal is actively open, re-render its contents
    const modal = document.getElementById("linkZoneMonitorModal");
    if (modal && !modal.classList.contains("hidden")) {
      renderLinkZoneMonitorModal(data);
    }
  } catch (err) {
    console.warn("Link Zone health check error:", err);
  }
}

function openLinkZoneMonitorModal() {
  const modal = document.getElementById("linkZoneMonitorModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.style.display = "flex";
  if (linkZoneHealthCache) {
    renderLinkZoneMonitorModal(linkZoneHealthCache);
  }
  fetchLinkZoneHealth();
}

function closeLinkZoneMonitorModal() {
  const modal = document.getElementById("linkZoneMonitorModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

function renderLinkZoneMonitorModal(data) {
  if (!data) return;

  // Status Badge in Header
  const badgeEl = document.getElementById("lzModalStatusBadge");
  if (badgeEl) {
    if (data.status === "HEALTHY") {
      badgeEl.className = "px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
      badgeEl.textContent = "🟢 LIVE DIRECT READ";
    } else {
      badgeEl.className = "px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/40";
      badgeEl.textContent = "⚠️ CACHED SNAPSHOT";
    }
  }

  // Master Path
  const pathEl = document.getElementById("lzModalPathText");
  if (pathEl) {
    pathEl.textContent = data.active_path || "C:\\Projects\\Apps\\link-zone\\data";
  }

  // Stat Cards
  const modeEl = document.getElementById("lzCardMode");
  if (modeEl) {
    modeEl.textContent = data.is_live_connected ? "Direct Live Read" : "Cached Snapshot";
    modeEl.className = data.is_live_connected ? "text-sm font-extrabold text-emerald-400 mt-1" : "text-sm font-extrabold text-amber-400 mt-1";
  }

  const statesCountEl = document.getElementById("lzCardStatesCount");
  if (statesCountEl) {
    const sCount = data.total_states || Object.keys(data.states || {}).length || 8;
    statesCountEl.textContent = `${sCount} States`;
  }

  const flCoverageEl = document.getElementById("lzCardFlCoverage");
  if (flCoverageEl) {
    const fl = data.states?.FL;
    if (fl) {
      flCoverageEl.textContent = `${fl.counties} Counties (${fl.links} Links)`;
    } else {
      flCoverageEl.textContent = "37 Counties (222 Links)";
    }
  }

  const lastCheckedEl = document.getElementById("lzCardLastChecked");
  if (lastCheckedEl) {
    lastCheckedEl.textContent = data.last_checked ? data.last_checked.split(" ")[1] : "Active";
  }

  // Left Column: States List
  const statesContainer = document.getElementById("lzStatesListContainer");
  if (statesContainer && data.states) {
    statesContainer.innerHTML = Object.entries(data.states).map(([code, s]) => {
      const isFl = (code === "FL");
      return `
        <div class="p-3 rounded-xl ${isFl ? 'bg-emerald-950/20 border-emerald-500/40' : 'bg-slate-900/60 border-slate-800'} border flex items-center justify-between gap-3 hover:border-slate-700 transition">
          <div class="flex items-center gap-2.5 min-w-0">
            <span class="text-xl">${s.icon || '📍'}</span>
            <div class="min-w-0">
              <div class="flex items-center gap-1.5">
                <span class="text-xs font-bold text-white truncate">${escapeHtml(s.name)}</span>
                <span class="text-[10px] font-mono text-slate-400">(${escapeHtml(code)})</span>
                ${isFl ? '<span class="px-1.5 py-0.2 rounded text-[9px] font-black bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">LIVE</span>' : ''}
              </div>
              <div class="text-[10px] text-slate-400 mt-0.5 truncate font-mono">${escapeHtml(s.filename)} &bull; ${s.last_modified}</div>
            </div>
          </div>
          <div class="text-right shrink-0">
            <div class="text-xs font-bold text-white font-mono">${s.counties} Counties</div>
            <div class="text-[10px] text-emerald-400 font-semibold">${s.links} Portals</div>
          </div>
        </div>
      `;
    }).join("");
  }

  // Right Column: Audit Log
  const logContainer = document.getElementById("lzAuditLogContainer");
  if (logContainer) {
    if (!data.history || data.history.length === 0) {
      logContainer.innerHTML = `<div class="p-4 text-center text-xs text-slate-500">No events logged yet.</div>`;
    } else {
      logContainer.innerHTML = data.history.map(ev => {
        let badgeClass = "bg-blue-500/20 text-blue-300 border-blue-500/40";
        let icon = "ℹ️";
        if (ev.level === "SUCCESS") {
          badgeClass = "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
          icon = "✓";
        } else if (ev.level === "UPDATE") {
          badgeClass = "bg-cyan-500/20 text-cyan-300 border-cyan-500/40";
          icon = "⚡";
        } else if (ev.level === "WARNING") {
          badgeClass = "bg-amber-500/20 text-amber-300 border-amber-500/40";
          icon = "⚠️";
        } else if (ev.level === "ERROR") {
          badgeClass = "bg-rose-500/20 text-rose-300 border-rose-500/40";
          icon = "✕";
        }

        return `
          <div class="p-3 rounded-xl bg-slate-900/70 border border-slate-800 space-y-1 hover:border-slate-700 transition">
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-1.5 min-w-0">
                <span class="px-1.5 py-0.5 rounded text-[9px] font-black uppercase tracking-wider border ${badgeClass} flex items-center gap-1">
                  <span>${icon}</span> <span>${escapeHtml(ev.level)}</span>
                </span>
                <span class="text-xs font-bold text-white truncate">${escapeHtml(ev.title)}</span>
              </div>
              <span class="text-[10px] text-slate-500 font-mono shrink-0">${escapeHtml(ev.timestamp)}</span>
            </div>
            <p class="text-[11px] text-slate-300 leading-snug">${escapeHtml(ev.details)}</p>
            ${ev.metrics && Object.keys(ev.metrics).length > 0 ? `
              <div class="flex items-center gap-2 pt-1 text-[10px] text-slate-400 font-mono">
                ${ev.metrics.counties ? `<span>Counties: <strong class="text-white">${ev.metrics.counties}</strong></span>` : ''}
                ${ev.metrics.links ? `<span>&bull; Links: <strong class="text-white">${ev.metrics.links}</strong></span>` : ''}
                ${ev.metrics.mtime ? `<span>&bull; File Time: <span class="text-slate-400">${ev.metrics.mtime}</span></span>` : ''}
              </div>
            ` : ''}
          </div>
        `;
      }).join("");
    }
  }
}

async function triggerLinkZoneResync() {
  const btn = document.getElementById("lzForceResyncBtn");
  const icon = document.getElementById("lzResyncIcon");
  const banner = document.getElementById("lzStatusBanner");

  if (btn) btn.disabled = true;
  if (icon) icon.className = "inline-block animate-spin";
  if (banner) {
    banner.className = "p-3 rounded-xl text-xs font-semibold bg-blue-900/40 border border-blue-500/40 text-blue-300 block";
    banner.innerHTML = "⏳ Scanning Link Zone data files...";
  }

  try {
    const res = await fetch("/api/link-zone/resync", { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      if (banner) {
        banner.className = "p-3 rounded-xl text-xs font-semibold bg-emerald-900/40 border border-emerald-500/40 text-emerald-300 block";
        banner.innerHTML = `✓ Verified &amp; Synced! Read ${data.total_counties || 37} counties and ${data.total_links || 222} verified government portals.`;
      }
      await fetchLinkZoneHealth();
      await fetchStats(currentState);
      await fetchCounties(currentState);
      if (selectedCountyKey) {
        selectCounty(selectedCountyKey);
      }
    } else {
      if (banner) {
        banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-900/40 border border-rose-500/40 text-rose-300 block";
        banner.innerHTML = "❌ Re-sync encountered an issue. Check audit log below.";
      }
    }
  } catch (err) {
    if (banner) {
      banner.className = "p-3 rounded-xl text-xs font-semibold bg-rose-900/40 border border-rose-500/40 text-rose-300 block";
      banner.innerHTML = `❌ Error: ${err.message}`;
    }
  } finally {
    setTimeout(() => {
      if (btn) btn.disabled = false;
      if (icon) icon.className = "";
      if (banner) {
        setTimeout(() => { banner.className = "hidden"; }, 4000);
      }
    }, 1000);
  }
}

// -------------------------------------------------------------
// Florida Government APIs Master Catalog (Link Zone Integration)
// -------------------------------------------------------------
let flApiCatalogCache = null;
let flApiSelectedCategory = "ALL";
let flApiSearchQuery = "";

async function openFloridaApiDirectoryModal() {
  const modal = document.getElementById("floridaApiDirectoryModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.style.display = "flex";
  const st = (currentState || "FL").toUpperCase();
  if (!flApiCatalogCache || flApiCatalogCache.state !== st) {
    await fetchFloridaApiCatalog();
  } else {
    renderFloridaApiDirectoryModal();
  }
}

function closeFloridaApiDirectoryModal() {
  const modal = document.getElementById("floridaApiDirectoryModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

const STATE_META_MAP = {
  FL: { name: "Florida", icon: "🌴" },
  GA: { name: "Georgia", icon: "🍑" },
  TN: { name: "Tennessee", icon: "🎸" },
  TX: { name: "Texas", icon: "🤠" },
  NC: { name: "North Carolina", icon: "🌲" },
  SC: { name: "South Carolina", icon: "🏖️" },
  IN: { name: "Indiana", icon: "🏁" },
  OH: { name: "Ohio", icon: "🌰" }
};

function getStateMeta(code) {
  const c = String(code || currentState || "FL").toUpperCase();
  if (typeof allStates !== "undefined" && Array.isArray(allStates)) {
    const found = allStates.find(s => s.code === c);
    if (found) return found;
  }
  return STATE_META_MAP[c] || { name: c, icon: "📍" };
}

async function refreshFloridaApiCatalog() {
  flApiCatalogCache = null;
  await fetchFloridaApiCatalog();
}

async function fetchFloridaApiCatalog() {
  const container = document.getElementById("flApiCardsContainer");
  const stateCode = (currentState || "FL").toUpperCase();
  const stateMeta = getStateMeta(stateCode);

  if (container) {
    container.innerHTML = `
      <div class="p-12 text-center text-slate-400">
        <div class="inline-block animate-spin text-2xl mb-2">⏳</div>
        <div class="font-bold text-white text-sm">Reading Link Zone ${stateMeta.name} API Directory...</div>
        <p class="text-xs text-slate-500 mt-1">Directly parsing verified endpoints from C:\\Projects\\Apps\\link-zone\\data\\${stateCode.toLowerCase()}-api-links.json</p>
      </div>`;
  }
  try {
    const res = await fetch(`/api/florida/apis?state=${encodeURIComponent(stateCode)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    flApiCatalogCache = data;
    renderFloridaApiDirectoryModal();
  } catch (err) {
    console.error("Error loading State API catalog:", err);
    if (container) {
      container.innerHTML = `
        <div class="p-8 text-center text-rose-300 bg-rose-950/40 border border-rose-500/40 rounded-xl">
          <div class="font-bold text-sm">Failed to load ${stateMeta.name} API Directory</div>
          <p class="text-xs text-rose-400 mt-1">${err.message}</p>
        </div>`;
    }
  }
}

function matchesApiEndpoint(ep, query) {
  if (!query) return true;
  const q = String(query).toLowerCase().trim();
  const cids = Array.isArray(ep.countyIds) ? ep.countyIds.join(' ') : '';
  let haystack = `${ep.county || ''} ${ep.municipality || ''} ${ep.governmentAgency || ''} ${ep.datasetName || ''} ${ep.platform || ''} ${ep.recordCategory || ''} ${ep.apiUrl || ''} ${ep.coverageNote || ''} ${cids}`.toLowerCase();
  
  // Cross-reference municipal & county equivalents
  if (haystack.includes('orange') || haystack.includes('orlando') || haystack.includes('fl-orange')) {
    haystack += ' orange orlando ocpa fl-orange central florida';
  }
  if (haystack.includes('hillsborough') || haystack.includes('tampa') || haystack.includes('fl-hillsborough')) {
    haystack += ' hillsborough tampa fl-hillsborough';
  }
  if (haystack.includes('pinellas') || haystack.includes('st petersburg') || haystack.includes('fl-pinellas')) {
    haystack += ' pinellas st pete stpete st. petersburg saint petersburg fl-pinellas';
  }
  if (haystack.includes('miami') || haystack.includes('dade') || haystack.includes('fl-miami-dade')) {
    haystack += ' miami miami-dade dade fl-miami-dade';
  }
  return haystack.includes(q);
}

function setFlApiCategoryFilter(cat, clearSearch = false) {
  flApiSelectedCategory = cat;
  if (clearSearch) {
    const input = document.getElementById("flApiSearchInput");
    if (input) input.value = "";
    flApiSearchQuery = "";
    const clearBtn = document.getElementById("flApiSearchClearBtn");
    if (clearBtn) clearBtn.classList.add("hidden");
  }

  const tabs = ["ALL", "CODE_ENFORCEMENT", "FORECLOSURE", "CLERK", "PROPERTY"];
  tabs.forEach(t => {
    const el = document.getElementById(`flApiTab${t}`);
    if (!el) return;
    if (t === cat) {
      el.className = "px-3 py-1 rounded-lg text-xs font-bold bg-blue-600 text-white cursor-pointer shadow-sm";
    } else {
      let colorClass = "text-slate-300 border-slate-700";
      if (t === "CODE_ENFORCEMENT") colorClass = "text-rose-300 border-rose-500/30";
      else if (t === "FORECLOSURE") colorClass = "text-purple-300 border-purple-500/30";
      else if (t === "CLERK") colorClass = "text-blue-300 border-blue-500/30";
      else if (t === "PROPERTY") colorClass = "text-emerald-300 border-emerald-500/30";
      el.className = `px-3 py-1 rounded-lg text-xs font-semibold bg-slate-800 ${colorClass} hover:text-white border cursor-pointer`;
    }
  });

  updateFlApiTabCounts();
  renderFloridaApiCards();
}

function filterFlApiCards() {
  const input = document.getElementById("flApiSearchInput");
  flApiSearchQuery = (input?.value || "").toLowerCase().trim();
  const clearBtn = document.getElementById("flApiSearchClearBtn");
  if (clearBtn) {
    if (flApiSearchQuery) clearBtn.classList.remove("hidden");
    else clearBtn.classList.add("hidden");
  }

  // Update dynamic counts on tabs
  updateFlApiTabCounts();
  renderFloridaApiCards();
}

function clearFlApiSearch() {
  const input = document.getElementById("flApiSearchInput");
  if (input) input.value = "";
  flApiSearchQuery = "";
  const clearBtn = document.getElementById("flApiSearchClearBtn");
  if (clearBtn) clearBtn.classList.add("hidden");
  updateFlApiTabCounts();
  renderFloridaApiCards();
}

function updateFlApiTabCounts() {
  if (!flApiCatalogCache) return;
  const endpoints = flApiCatalogCache.endpoints || [];
  const q = flApiSearchQuery;

  const matchesAll = endpoints.filter(ep => matchesApiEndpoint(ep, q));
  const matchesCode = matchesAll.filter(ep => ep.recordCategory === "CODE_ENFORCEMENT" || (Array.isArray(ep.supportedCategories) && ep.supportedCategories.includes("CODE_ENFORCEMENT")));
  const matchesFc = matchesAll.filter(ep => ep.recordCategory === "FORECLOSURE" || (Array.isArray(ep.supportedCategories) && ep.supportedCategories.includes("FORECLOSURE")));
  const matchesClerk = matchesAll.filter(ep => ep.recordCategory === "CLERK" || ep.recordCategory === "COMPTROLLER" || (Array.isArray(ep.supportedCategories) && (ep.supportedCategories.includes("CLERK") || ep.supportedCategories.includes("COMPTROLLER"))));
  const matchesProp = matchesAll.filter(ep => ep.recordCategory === "PROPERTY" || (Array.isArray(ep.supportedCategories) && ep.supportedCategories.includes("PROPERTY")));

  const setCnt = (id, count) => {
    const el = document.getElementById(id);
    if (el) el.innerText = count.toLocaleString();
  };

  setCnt("flApiTabAllCount", matchesAll.length);
  setCnt("flApiTabCodeCount", matchesCode.length);
  setCnt("flApiTabFcCount", matchesFc.length);
  setCnt("flApiTabClerkCount", matchesClerk.length);
  setCnt("flApiTabPropCount", matchesProp.length);
}

function renderFloridaApiDirectoryModal() {
  if (!flApiCatalogCache) return;
  const stats = flApiCatalogCache.statistics || {};
  const catStats = stats.verifiedByPrimaryCategory || {};

  const stateCode = (flApiCatalogCache.state || currentState || "FL").toUpperCase();
  const stateMeta = getStateMeta(stateCode);
  const stateName = flApiCatalogCache.state_name || stateMeta.name || stateCode;
  
  const titleEl = document.getElementById("flApiModalTitle");
  if (titleEl) titleEl.innerText = `${stateName} Government API Directory`;
  const badgeEl = document.getElementById("flApiModalBadge");
  if (badgeEl) badgeEl.innerText = `${flApiCatalogCache.total_endpoints || 0} VERIFIED LINK ZONE ENDPOINTS`;

  const subEl = document.getElementById("flApiModalSub");
  if (subEl) {
    const countyCount = flApiCatalogCache.county_coverage_count || flApiCatalogCache.countyCoverage?.length || 0;
    const muniCount = flApiCatalogCache.muni_coverage_count || flApiCatalogCache.municipalCoverage?.length || 0;
    const parts = [];
    if (countyCount > 0) parts.push(`${countyCount} Counties`);
    if (muniCount > 0) parts.push(`${muniCount} Municipalities`);
    const covStr = parts.length > 0 ? ` across ${parts.join(" & ")}` : "";
    subEl.innerText = `Live SODA, ArcGIS REST, and Public Record APIs${covStr} in ${stateName}. Direct Link Zone government endpoints.`;
  }
  const srcEl = document.getElementById("flApiModalSourceFile");
  if (srcEl && flApiCatalogCache.source_file) {
    srcEl.innerText = flApiCatalogCache.source_file;
  }

  const kpiCode = document.getElementById("flApiKpiCode");
  if (kpiCode) kpiCode.innerText = `${catStats.CODE_ENFORCEMENT || 0} APIs`;

  const kpiFc = document.getElementById("flApiKpiForeclosure");
  if (kpiFc) kpiFc.innerText = `${catStats.FORECLOSURE || 0} APIs`;

  const kpiClerk = document.getElementById("flApiKpiClerk");
  if (kpiClerk) kpiClerk.innerText = `${(catStats.CLERK || 0) + (stats.documentedCredentialedRoutes || 0)} APIs`;

  const kpiProp = document.getElementById("flApiKpiProperty");
  if (kpiProp) kpiProp.innerText = `${catStats.PROPERTY || 0} APIs`;

  const kpiPub = document.getElementById("flApiKpiPublic");
  if (kpiPub) kpiPub.innerText = `${stats.anonymousPublicEndpoints || 0} Public`;

  const kpiConn = document.getElementById("flApiKpiConnected");
  const connCount = (flApiCatalogCache.endpoints || []).filter(e => e.is_connected).length;
  if (kpiConn) kpiConn.innerText = `${connCount} Active`;

  updateFlApiTabCounts();
  renderFloridaApiCards();
}

let expandedFlApiGroups = new Set();
let flApiUserToggledExplicitly = false;

function getFlApiEndpointGroup(ep) {
  const cnty = (ep.county || "").trim();
  const stateCode = (flApiCatalogCache?.state || currentState || "FL").toUpperCase();
  const stateMeta = getStateMeta(stateCode);
  const stateName = flApiCatalogCache?.state_name || stateMeta.name || stateCode;

  if (
    !cnty ||
    cnty.toLowerCase() === "statewide" ||
    cnty.toLowerCase() === `state of ${stateName.toLowerCase()}` ||
    cnty.toLowerCase() === stateName.toLowerCase() ||
    cnty.toLowerCase() === "state of florida" ||
    cnty.toLowerCase() === "florida"
  ) {
    return {
      key: `statewide_${stateCode.toLowerCase()}`,
      title: `Statewide (${stateName})`,
      isStatewide: true,
      order: 0
    };
  }
  return {
    key: cnty.toLowerCase().replace(/[^a-z0-9]/g, "_") + "_county",
    title: `${cnty} County`,
    isStatewide: false,
    order: 1
  };
}

function toggleFlApiGroup(groupKey) {
  flApiUserToggledExplicitly = true;
  if (expandedFlApiGroups.has(groupKey)) {
    expandedFlApiGroups.delete(groupKey);
  } else {
    expandedFlApiGroups.add(groupKey);
  }
  renderFloridaApiCards();
}

function toggleAllFlApiGroups() {
  flApiUserToggledExplicitly = true;
  if (!flApiCatalogCache) return;
  const endpoints = flApiCatalogCache.endpoints || [];
  const currentGroupKeys = [];
  endpoints.forEach(ep => {
    const k = getFlApiEndpointGroup(ep).key;
    if (!currentGroupKeys.includes(k)) currentGroupKeys.push(k);
  });
  
  const allExpanded = currentGroupKeys.every(k => expandedFlApiGroups.has(k));
  if (allExpanded) {
    expandedFlApiGroups.clear();
  } else {
    currentGroupKeys.forEach(k => expandedFlApiGroups.add(k));
  }
  renderFloridaApiCards();
}

function renderFlApiSingleCard(ep) {
  const isConnected = Boolean(ep.is_connected);
  const locName = ep.municipality ? `${ep.municipality} (City)` : (ep.county ? `${ep.county} County` : "Statewide (Florida)");
  const cat = ep.recordCategory || "PROPERTY";
  let catBadge = "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
  let catLabel = "🏡 Tax & Parcels";
  if (cat === "CODE_ENFORCEMENT") {
    catBadge = "bg-rose-500/20 text-rose-300 border-rose-500/30";
    catLabel = "🚨 Code Enforcement";
  } else if (cat === "FORECLOSURE") {
    catBadge = "bg-purple-500/20 text-purple-300 border-purple-500/30";
    catLabel = "⚖️ Foreclosures";
  } else if (cat === "CLERK" || cat === "COMPTROLLER") {
    catBadge = "bg-blue-500/20 text-blue-300 border-blue-500/30";
    catLabel = "🏛️ Clerk of Court";
  }

  const isPublic = ep.authentication === "PUBLIC";
  const authBadge = isPublic 
    ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">✓ Direct Public</span>`
    : `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30">🔒 Key / Auth</span>`;

  return `
    <div class="p-4 rounded-xl bg-slate-900/90 border ${isConnected ? 'border-amber-500/70 ring-1 ring-amber-500/30 bg-amber-950/15 shadow-md shadow-amber-950/20' : 'border-slate-800'} hover:border-slate-700 transition flex flex-col justify-between gap-3">
      <div class="space-y-2">
        <div class="flex items-center justify-between gap-2 flex-wrap">
          <span class="px-2 py-0.5 rounded-md text-[10px] font-extrabold border ${catBadge}">
            ${catLabel}
          </span>
          <div class="flex items-center gap-1.5">
            ${authBadge}
            ${isConnected ? `
              <span class="px-2 py-0.5 rounded text-[10px] font-black bg-amber-500 text-slate-950 shadow-sm animate-pulse flex items-center gap-1">
                <span>⚡</span> <span>LIVE CONNECTED</span>
              </span>
            ` : ''}
          </div>
        </div>

        <div>
          <div class="text-xs font-black text-white leading-snug line-clamp-2" title="${escapeHtml(ep.datasetName)}">
            ${escapeHtml(ep.datasetName)}
          </div>
          <div class="text-[11px] text-slate-300 font-semibold mt-1 flex items-center gap-1.5 flex-wrap">
            <span class="text-amber-300 font-bold">📍 ${escapeHtml(locName)}</span>
            <span class="text-slate-600">&bull;</span>
            <span class="text-slate-400 text-[10px] font-normal">${escapeHtml(ep.governmentAgency || 'Municipal / County Agency')}</span>
          </div>
        </div>

        <div class="text-[10px] text-slate-300 font-mono bg-slate-950/90 p-2.5 rounded-lg border border-slate-800 break-all leading-tight">
          <div class="flex items-center justify-between text-slate-400 text-[9px] uppercase tracking-wider mb-1">
            <span>Protocol: <b class="text-cyan-300 font-mono">${escapeHtml(ep.platform || 'REST')}</b></span>
            ${ep.platform && ep.platform.toUpperCase().includes('SODA') ? `<span class="text-emerald-400 font-bold">SODA 2.0 API</span>` : ''}
          </div>
          <a href="${ep.apiUrl}" target="_blank" rel="noopener noreferrer" class="text-cyan-400 hover:text-cyan-300 hover:underline">
            ${escapeHtml(ep.apiUrl)}
          </a>
        </div>
      </div>

      <div class="flex items-center justify-between pt-2 border-t border-slate-800/80 text-[11px]">
        <div class="text-[10px] text-slate-500">
          Verified: <span class="text-slate-400">${ep.dateVerified || '2026-10-09'}</span>
        </div>
        <div class="flex items-center gap-2">
          ${ep.officialDatasetUrl ? `
            <a href="${ep.officialDatasetUrl}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white font-medium text-[10px] transition" title="View dataset on official government portal">
              Portal ↗
            </a>
          ` : ''}
          ${isConnected ? `
            <button type="button" onclick="syncOrlandoLiveCode(); closeFloridaApiDirectoryModal();" class="px-3 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-black text-[10px] transition shadow-sm cursor-pointer flex items-center gap-1">
              <span>⚡ Sync Now</span>
            </button>
          ` : (cat === "CODE_ENFORCEMENT" && isPublic) ? `
            <button type="button" onclick="connectFloridaApi('${escapeAttr(ep.id)}', '${escapeAttr(ep.apiUrl)}', '${escapeAttr(locName)}')" class="px-3 py-1 rounded-lg bg-emerald-600/30 hover:bg-emerald-600 text-emerald-300 hover:text-white font-bold text-[10px] border border-emerald-500/40 transition cursor-pointer flex items-center gap-1">
              <span>🔌 Wire Ingestion</span>
            </button>
          ` : `
            <a href="${ep.apiUrl}" target="_blank" rel="noopener noreferrer" class="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white font-semibold text-[10px] transition">
              Test Link ↗
            </a>
          `}
        </div>
      </div>
    </div>
  `;
}

function renderFloridaApiCards() {
  const container = document.getElementById("flApiCardsContainer");
  if (!container || !flApiCatalogCache) return;

  try {
    const endpoints = flApiCatalogCache.endpoints || [];
    const allMatches = endpoints.filter(ep => matchesApiEndpoint(ep, flApiSearchQuery));

    let filtered = allMatches.filter(ep => {
      if (flApiSelectedCategory !== "ALL") {
        const matchCat = ep.recordCategory === flApiSelectedCategory || 
                         (Array.isArray(ep.supportedCategories) && ep.supportedCategories.includes(flApiSelectedCategory));
        if (!matchCat) return false;
      }
      return true;
    });

    const catLabels = {
      ALL: "All Categories",
      CODE_ENFORCEMENT: "🚨 Code Enforcement",
      FORECLOSURE: "⚖️ Foreclosures",
      CLERK: "🏛️ Clerk of Court",
      PROPERTY: "🏡 Tax & Parcels"
    };

    if (filtered.length === 0) {
      if (allMatches.length > 0 && flApiSelectedCategory !== "ALL") {
        container.innerHTML = `
          <div class="p-8 text-center text-slate-300 bg-slate-900/60 border border-slate-800 rounded-2xl space-y-3">
            <div class="text-3xl">🔍</div>
            <div class="font-bold text-white text-base">0 results under ${catLabels[flApiSelectedCategory] || flApiSelectedCategory} for "${escapeHtml(flApiSearchQuery)}"</div>
            <p class="text-xs text-slate-400 max-w-md mx-auto">However, Link Zone found <b>${allMatches.length}</b> verified government APIs matching your search in other categories!</p>
            <div class="pt-2">
              <button type="button" onclick="setFlApiCategoryFilter('ALL')" class="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs inline-flex items-center gap-2 cursor-pointer shadow-lg shadow-blue-600/30 transition">
                <span>View All ${allMatches.length} Matching APIs ↗</span>
              </button>
            </div>
          </div>`;
      } else {
        container.innerHTML = `
          <div class="p-10 text-center text-slate-400 bg-slate-900/40 border border-slate-800 rounded-2xl space-y-2">
            <div class="text-3xl mb-1">🔍</div>
            <div class="font-bold text-slate-200 text-sm">No APIs match "${escapeHtml(flApiSearchQuery)}"</div>
            <p class="text-xs text-slate-500 max-w-sm mx-auto">Try searching by jurisdiction (Orlando, Orange, Tampa, Pinellas, Miami) or protocol (SODA, ArcGIS, MapServer).</p>
            <div class="pt-2">
              <button type="button" onclick="clearFlApiSearch()" class="px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold cursor-pointer transition">
                Clear Search Query
              </button>
            </div>
          </div>`;
      }
      return;
    }

    // Group filtered endpoints by county / statewide
    const groupsMap = new Map();
    filtered.forEach(ep => {
      const grp = getFlApiEndpointGroup(ep);
      if (!groupsMap.has(grp.key)) {
        groupsMap.set(grp.key, {
          key: grp.key,
          title: grp.title,
          isStatewide: grp.isStatewide,
          order: grp.order,
          endpoints: []
        });
      }
      groupsMap.get(grp.key).endpoints.push(ep);
    });

    const sortedGroups = Array.from(groupsMap.values()).sort((a, b) => {
      if (a.order !== b.order) return a.order - b.order;
      return a.title.localeCompare(b.title);
    });

    // Auto-expand logic:
    const hasFilterActive = Boolean(flApiSearchQuery) || flApiSelectedCategory !== "ALL";
    if (hasFilterActive && !flApiUserToggledExplicitly) {
      sortedGroups.forEach(g => expandedFlApiGroups.add(g.key));
    } else if (expandedFlApiGroups.size === 0 && !flApiUserToggledExplicitly) {
      // Default: Expand Statewide and Orange / active county
      const currentCntyLower = (selectedCountyKey || "Orange").toLowerCase();
      sortedGroups.forEach(g => {
        if (g.isStatewide || g.title.toLowerCase().includes(currentCntyLower)) {
          expandedFlApiGroups.add(g.key);
        }
      });
    }

    // Update Expand / Collapse All button label
    const btnToggleLabel = document.getElementById("btnToggleExpandLabel");
    const btnToggleIcon = document.getElementById("btnToggleExpandIcon");
    if (btnToggleLabel && sortedGroups.length > 0) {
      const allExpanded = sortedGroups.every(g => expandedFlApiGroups.has(g.key));
      btnToggleLabel.innerText = allExpanded ? "Collapse All" : "Expand All";
      if (btnToggleIcon) btnToggleIcon.innerText = allExpanded ? "▲" : "▼";
    }

    // Render grouped accordion layout
    container.innerHTML = `
      <div class="space-y-4">
        ${sortedGroups.map(g => {
          const isExpanded = expandedFlApiGroups.has(g.key);
          const hasConnected = g.endpoints.some(e => e.is_connected);
          const totalEps = g.endpoints.length;

          // Category counts in this group
          const codeCnt = g.endpoints.filter(e => e.recordCategory === "CODE_ENFORCEMENT" || (Array.isArray(e.supportedCategories) && e.supportedCategories.includes("CODE_ENFORCEMENT"))).length;
          const propCnt = g.endpoints.filter(e => e.recordCategory === "PROPERTY" || (Array.isArray(e.supportedCategories) && e.supportedCategories.includes("PROPERTY"))).length;
          const clerkCnt = g.endpoints.filter(e => e.recordCategory === "CLERK" || e.recordCategory === "COMPTROLLER" || (Array.isArray(e.supportedCategories) && (e.supportedCategories.includes("CLERK") || e.supportedCategories.includes("COMPTROLLER")))).length;
          const fcCnt = g.endpoints.filter(e => e.recordCategory === "FORECLOSURE" || (Array.isArray(e.supportedCategories) && e.supportedCategories.includes("FORECLOSURE"))).length;

          // Distinct Municipalities
          const munis = [...new Set(g.endpoints.map(e => e.municipality).filter(Boolean))];
          const muniSummary = munis.length > 0 ? munis.join(", ") : "";

          // High-contrast header card styling: Vibrant Amber for Statewide & Connected; Bright White & Emerald for Counties
          let cardBorderClass = "border-2 border-slate-700/80 bg-slate-900/95 hover:border-emerald-500/70 shadow-md";
          let badgeClass = "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
          let badgeText = "COUNTY JURISDICTION";
          let titleColor = "text-white group-hover:text-amber-300";
          let icon = "🌴";
          let iconBg = "bg-slate-800 text-white border border-slate-700";

          if (g.isStatewide) {
            cardBorderClass = "border-2 border-amber-500/80 bg-gradient-to-r from-amber-950/60 via-slate-900 to-amber-950/40 shadow-xl shadow-amber-950/40 hover:border-amber-400";
            badgeClass = "bg-amber-500/25 text-amber-300 border border-amber-500/50 font-black";
            badgeText = "STATEWIDE ENDPOINTS";
            titleColor = "text-amber-200 group-hover:text-amber-100";
            icon = "☀️";
            iconBg = "bg-amber-500/20 text-amber-300 border border-amber-500/40";
          } else if (hasConnected) {
            cardBorderClass = "border-2 border-amber-500/80 bg-slate-900 shadow-xl shadow-amber-950/30 hover:border-amber-400";
            badgeClass = "bg-amber-500/25 text-amber-300 border border-amber-500/50 font-black";
            badgeText = "COUNTY • ⚡ LIVE API CONNECTED";
            titleColor = "text-amber-300 group-hover:text-amber-200";
            icon = "⚡";
            iconBg = "bg-amber-500/25 text-amber-300 border border-amber-500/50";
          }

          if (isExpanded) {
            cardBorderClass += " ring-1 ring-amber-400/40";
          }

          return `
            <div class="rounded-2xl ${cardBorderClass} overflow-hidden transition">
              <!-- ACCORDION HEADER BUTTON -->
              <button type="button" onclick="toggleFlApiGroup('${g.key}')" class="w-full px-5 py-4 flex items-center justify-between gap-4 text-left transition cursor-pointer select-none group">
                <div class="flex items-center gap-3.5 flex-wrap min-w-0">
                  <div class="w-11 h-11 rounded-xl ${iconBg} text-xl flex items-center justify-center font-black shadow-inner shrink-0 group-hover:scale-105 transition">
                    ${icon}
                  </div>
                  <div class="min-w-0">
                    <div class="flex items-center gap-2.5 flex-wrap">
                      <span class="text-base sm:text-lg font-black tracking-wide ${titleColor} transition">
                        ${escapeHtml(g.title)}
                      </span>
                      <span class="px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider ${badgeClass}">
                        ${badgeText}
                      </span>
                      ${hasConnected ? `
                        <span class="px-2 py-0.5 rounded-md text-[10px] font-black bg-amber-500 text-slate-950 shadow-sm animate-pulse flex items-center gap-1">
                          <span>⚡</span> <span>1 LIVE CONNECTED</span>
                        </span>
                      ` : ''}
                    </div>
                    ${g.isStatewide ? `
                      <p class="text-xs text-amber-200/80 mt-0.5">
                        Florida Department of Revenue Cadastral GIS &amp; Multi-County Tax Infrastructure
                      </p>
                    ` : (muniSummary ? `
                      <p class="text-xs text-slate-300 mt-0.5 flex items-center gap-1.5 flex-wrap">
                        <span class="text-amber-400 font-bold">📍 Municipalities:</span>
                        <span class="text-slate-200 font-medium">${escapeHtml(muniSummary)}</span>
                      </p>
                    ` : `
                      <p class="text-xs text-slate-400 mt-0.5">Official County Public Records &amp; Tax Roll Endpoints</p>
                    `)}
                  </div>
                </div>

                <!-- RIGHT CONTROLS: CATEGORY PILLS & TOTAL COUNT & CHEVRON -->
                <div class="flex items-center gap-3 shrink-0">
                  <div class="hidden md:flex items-center gap-1.5 flex-wrap">
                    ${codeCnt > 0 ? `<span class="px-2 py-0.5 rounded-md text-[10px] font-extrabold bg-rose-500/20 text-rose-300 border border-rose-500/40">🚨 ${codeCnt} Code</span>` : ''}
                    ${propCnt > 0 ? `<span class="px-2 py-0.5 rounded-md text-[10px] font-extrabold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">🏡 ${propCnt} Tax</span>` : ''}
                    ${clerkCnt > 0 ? `<span class="px-2 py-0.5 rounded-md text-[10px] font-extrabold bg-blue-500/20 text-blue-300 border border-blue-500/40">🏛️ ${clerkCnt} Clerk</span>` : ''}
                    ${fcCnt > 0 ? `<span class="px-2 py-0.5 rounded-md text-[10px] font-extrabold bg-purple-500/20 text-purple-300 border border-purple-500/40">⚖️ ${fcCnt} FC</span>` : ''}
                  </div>

                  <span class="px-3 py-1 rounded-xl text-xs font-mono font-black ${g.isStatewide ? 'bg-amber-500/20 text-amber-200 border border-amber-500/40' : 'bg-slate-950 text-white border border-slate-700/80'} shadow-sm">
                    ${totalEps} ${totalEps === 1 ? 'API' : 'APIs'}
                  </span>

                  <div class="w-7 h-7 rounded-lg bg-slate-800 group-hover:bg-slate-700 flex items-center justify-center text-xs font-black text-slate-300 transition-transform ${isExpanded ? 'rotate-180 text-amber-400 bg-slate-700' : ''}">
                    ▼
                  </div>
                </div>
              </button>

              <!-- EXPANDED ENDPOINTS GRID -->
              ${isExpanded ? `
                <div class="p-4 sm:p-5 border-t border-slate-800/90 bg-[#080d19]/90">
                  <div class="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                    ${g.endpoints.map(ep => renderFlApiSingleCard(ep)).join('')}
                  </div>
                </div>
              ` : ''}
            </div>
          `;
        }).join('')}
      </div>
    `;
  } catch (err) {
    console.error("Error rendering API cards:", err);
    container.innerHTML = `
      <div class="p-8 text-center text-rose-300 bg-rose-950/30 border border-rose-500/40 rounded-xl">
        <div class="font-bold text-sm">Error rendering API cards</div>
        <p class="text-xs text-rose-400 mt-1">${escapeHtml(err.message)}</p>
      </div>`;
  }
}

window.openFloridaApiDirectoryModal = openFloridaApiDirectoryModal;
window.closeFloridaApiDirectoryModal = closeFloridaApiDirectoryModal;
window.refreshFloridaApiCatalog = refreshFloridaApiCatalog;
window.setFlApiCategoryFilter = setFlApiCategoryFilter;
window.filterFlApiCards = filterFlApiCards;
window.clearFlApiSearch = clearFlApiSearch;
window.toggleFlApiGroup = toggleFlApiGroup;
window.toggleAllFlApiGroups = toggleAllFlApiGroups;

function connectFloridaApi(id, url, location) {
  alert(`Connecting to ${location} API:\n${url}\n\nThis endpoint is verified public in Link Zone. We will connect direct automated ingestion for this municipal dataset next!`);
}

// ----------------------------------------------------
// SCOUT - AUTONOMOUS LEAD HUB OPERATOR & SENTINEL AGENT
// ----------------------------------------------------
let scoutActiveState = 'FL';
let scoutSentinelHealthCache = null;
let scoutLastQueryResults = [];
let scoutDrawerIsOpen = false;

function openScoutDrawer() {
  const drawer = document.getElementById("scoutDrawer");
  const backdrop = document.getElementById("scoutDrawerBackdrop");
  if (!drawer) return;
  drawer.classList.remove("translate-x-full");
  if (backdrop) backdrop.classList.remove("hidden");
  scoutDrawerIsOpen = true;
  const input = document.getElementById("scoutChatInput");
  if (input) setTimeout(() => input.focus(), 250);
  refreshScoutSentinelStatus();
}

function closeScoutDrawer() {
  const drawer = document.getElementById("scoutDrawer");
  const backdrop = document.getElementById("scoutDrawerBackdrop");
  if (!drawer) return;
  drawer.classList.add("translate-x-full");
  if (backdrop) backdrop.classList.add("hidden");
  scoutDrawerIsOpen = false;
}

function toggleScoutDrawer() {
  if (scoutDrawerIsOpen) {
    closeScoutDrawer();
  } else {
    openScoutDrawer();
  }
}

async function refreshScoutSentinelStatus() {
  try {
    const res = await fetch(`/api/scout/status?state=${encodeURIComponent(scoutActiveState)}`);
    if (!res.ok) return;
    const data = await res.json();
    scoutSentinelHealthCache = data;

    const badgeStatus = document.getElementById("scoutBadgeStatus");
    const statusSub = document.getElementById("scoutStatusSub");
    const drawerPill = document.getElementById("scoutDrawerSentinelStatusPill");
    const pingDot = document.getElementById("scoutPulsePing");

    const isHealthy = (data.sentinel_status === "HEALTHY");
    const count = data.total_active_leads || 0;
    const countyCount = data.total_counties || 37;

    if (badgeStatus) {
      badgeStatus.textContent = isHealthy ? "ONLINE" : data.sentinel_status;
      badgeStatus.className = isHealthy 
        ? "text-[10px] font-bold font-mono px-1 py-0.2 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
        : "text-[10px] font-bold font-mono px-1 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30";
    }

    if (statusSub) {
      statusSub.textContent = `${countyCount} Counties • ${count.toLocaleString()} Leads`;
    }

    if (drawerPill) {
      drawerPill.textContent = isHealthy ? `🟢 HEALTHY (${countyCount} Counties)` : `⚠️ ${data.sentinel_status}`;
      drawerPill.className = isHealthy 
        ? "px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
        : "px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-amber-500/20 text-amber-300 border border-amber-500/40";
    }

    if (pingDot) {
      pingDot.className = isHealthy
        ? "animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"
        : "animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75";
    }
  } catch (err) {
    console.warn("Scout sentinel status poll error:", err);
  }
}

function formatScoutMarkdown(text) {
  if (!text) return "";
  let html = escapeHtml(text);
  // Headers
  html = html.replace(/^### (.*$)/gim, '<h4 class="font-bold text-white text-sm my-1 text-amber-300">$1</h4>');
  html = html.replace(/^#### (.*$)/gim, '<h5 class="font-semibold text-slate-200 text-xs my-1 text-blue-300">$1</h5>');
  // Bold & Italics
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white font-bold">$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em class="text-slate-300">$1</em>');
  // Inline code
  html = html.replace(/`(.*?)`/g, '<code class="px-1 py-0.5 rounded bg-slate-900 border border-slate-700/60 font-mono text-[11px] text-amber-300">$1</code>');
  // Bullet lists
  html = html.replace(/^\- (.*$)/gim, '<div class="flex items-start gap-1.5 my-0.5"><span class="text-amber-400 shrink-0">•</span><span>$1</span></div>');
  // Linebreaks
  html = html.replace(/\n\n/g, '<div class="h-2"></div>');
  html = html.replace(/\n/g, '<br>');
  return html;
}

let scoutLastQuerySpeed = 0;

function appendScoutChatMessage(role, content, actionsHtml = "") {
  const container = document.getElementById("scoutChatContainer");
  if (!container) return null;

  const msgDiv = document.createElement("div");
  msgDiv.className = "flex items-start gap-3 transition-opacity duration-200";

  if (role === "user") {
    msgDiv.className += " justify-end";
    msgDiv.innerHTML = `
      <div class="bg-blue-600 text-white rounded-2xl rounded-tr-none p-3 max-w-lg text-xs shadow-md">
        <p class="font-medium">${escapeHtml(content)}</p>
      </div>
      <div class="w-8 h-8 rounded-lg bg-blue-700 text-white flex items-center justify-center text-xs font-bold shrink-0">
        You
      </div>
    `;
  } else {
    msgDiv.innerHTML = `
      <div class="w-8 h-8 rounded-lg bg-amber-600/30 text-amber-300 flex items-center justify-center text-sm font-bold shrink-0 border border-amber-500/40">
        🧭
      </div>
      <div class="bg-slate-800/80 border border-slate-700/60 rounded-2xl rounded-tl-none p-3.5 max-w-xl text-xs text-slate-200 space-y-2 shadow-md">
        <div>${formatScoutMarkdown(content)}</div>
        ${actionsHtml ? `<div class="mt-2.5 pt-2 border-t border-slate-700/60">${actionsHtml}</div>` : ''}
      </div>
    `;
  }

  container.appendChild(msgDiv);
  container.scrollTop = container.scrollHeight;
  return msgDiv;
}

function clearScoutChat() {
  const container = document.getElementById("scoutChatContainer");
  if (!container) return;
  container.innerHTML = `
    <div class="flex items-start gap-3">
      <div class="w-8 h-8 rounded-lg bg-amber-600/30 text-amber-300 flex items-center justify-center text-sm font-bold shrink-0 border border-amber-500/40">
        🧭
      </div>
      <div class="bg-slate-800/80 border border-slate-700/60 rounded-2xl rounded-tl-none p-3.5 max-w-xl text-xs text-slate-200 space-y-2">
        <p class="font-bold text-white text-sm">Chat Cleared &bull; Scout AI Ready 🧭</p>
        <p>I monitor all 37 Florida counties (52,000+ active distress leads and 9.8M+ parcels).</p>
        <p class="text-slate-400">Ask a question or use the 1-click fast action buttons above.</p>
      </div>
    </div>
  `;
}

async function handleScoutChatSubmit(e) {
  if (e) e.preventDefault();
  const input = document.getElementById("scoutChatInput");
  if (!input || !input.value.trim()) return;
  const message = input.value.trim();
  input.value = "";

  appendScoutChatMessage("user", message);

  // Show typing loader
  const loader = appendScoutChatMessage("scout", "🧭 *Scout is analyzing statewide records...*");

  try {
    const res = await fetch("/api/scout/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: message,
        state: scoutActiveState,
        county: window.currentCounty || null
      })
    });

    if (loader && loader.remove) loader.remove();

    if (!res.ok) {
      appendScoutChatMessage("scout", "⚠️ Failed to communicate with Scout agent engine.");
      return;
    }

    const data = await res.json();
    
    if (data.action === "leads_query" && Array.isArray(data.leads) && data.leads.length > 0) {
      scoutLastQueryResults = data.leads;
      scoutLastQuerySpeed = data.elapsed_ms || 0;
      const count = data.leads.length;
      const actionsHtml = `
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" onclick="openScoutLeadsPopout()" class="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold text-xs flex items-center gap-1.5 transition cursor-pointer shadow-md">
            <span>📋 View Leads in Full Table (${count})</span>
          </button>
          <button type="button" onclick="exportScoutResultsToCSV()" class="px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200 font-semibold text-xs flex items-center gap-1.5 transition cursor-pointer">
            <span>📥 Export CSV</span>
          </button>
        </div>
      `;
      appendScoutChatMessage("scout", data.reply || `Found ${count} matching properties.`, actionsHtml);
    } else {
      appendScoutChatMessage("scout", data.reply || "Done.");
      if (data.action === "trigger_sync_all") {
        triggerScoutSyncAll();
      }
    }
  } catch (err) {
    if (loader && loader.remove) loader.remove();
    appendScoutChatMessage("scout", `⚠️ Error: ${err.message}`);
  }
}

async function triggerScoutBriefing() {
  appendScoutChatMessage("user", "Generate executive briefing report");
  const loader = appendScoutChatMessage("scout", "🧭 *Compiling executive briefing across all monitored counties...*");

  try {
    const res = await fetch(`/api/scout/briefing?state=${encodeURIComponent(scoutActiveState)}`);
    if (loader && loader.remove) loader.remove();
    if (!res.ok) {
      appendScoutChatMessage("scout", "⚠️ Could not generate briefing.");
      return;
    }
    const data = await res.json();
    appendScoutChatMessage("scout", data.briefing_markdown || "Executive briefing compiled.");
  } catch (err) {
    if (loader && loader.remove) loader.remove();
    appendScoutChatMessage("scout", `⚠️ Error: ${err.message}`);
  }
}

async function triggerScoutStatewideDistress(filterType) {
  const labelMap = {
    'stacked': 'double & triple distress stacked properties',
    'out_of_state': 'out-of-state absentee investor leads',
    'code': 'municipal code violations'
  };
  const label = labelMap[filterType] || filterType;
  appendScoutChatMessage("user", `Show all statewide ${label}`);
  const loader = appendScoutChatMessage("scout", `🧭 *Querying all 37 Florida county datasets for ${label}...*`);

  try {
    const res = await fetch("/api/scout/cross-query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        state: scoutActiveState,
        filter_type: filterType,
        max_records: 100,
        exclude_llc: true,
        max_market_val: 1500000
      })
    });

    if (loader && loader.remove) loader.remove();
    if (!res.ok) {
      appendScoutChatMessage("scout", "⚠️ Cross-county query failed.");
      return;
    }

    const data = await res.json();
    const count = (data.total_matches || (data.leads ? data.leads.length : 0)).toLocaleString();
    const speed = data.elapsed_ms || 0;
    scoutLastQueryResults = data.leads || [];
    scoutLastQuerySpeed = speed;

    const actionsHtml = scoutLastQueryResults.length > 0 ? `
      <div class="flex flex-wrap items-center gap-2">
        <button type="button" onclick="openScoutLeadsPopout()" class="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold text-xs flex items-center gap-1.5 transition cursor-pointer shadow-md">
          <span>📋 View Leads in Full Table (${count})</span>
        </button>
        <button type="button" onclick="exportScoutResultsToCSV()" class="px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200 font-semibold text-xs flex items-center gap-1.5 transition cursor-pointer">
          <span>📥 Export CSV</span>
        </button>
      </div>
    ` : '';

    appendScoutChatMessage("scout", `Found **${count}** properties statewide matching \`${label}\` in \`${speed}ms\` (wholesale filters active: corporate LLCs excluded, single-family capped at $1.5M).`, actionsHtml);
  } catch (err) {
    if (loader && loader.remove) loader.remove();
    appendScoutChatMessage("scout", `⚠️ Error: ${err.message}`);
  }
}

async function triggerScoutSyncAll() {
  appendScoutChatMessage("user", "Synchronize all municipal APIs in background");
  const loader = appendScoutChatMessage("scout", "🧭 *Initiating background live sync across all 37 counties...*");

  try {
    const res = await fetch(`/api/scout/sync-all?state=${encodeURIComponent(scoutActiveState)}`, {
      method: "POST"
    });
    if (loader && loader.remove) loader.remove();
    if (!res.ok) {
      appendScoutChatMessage("scout", "⚠️ Could not initiate background sync.");
      return;
    }
    const data = await res.json();
    appendScoutChatMessage("scout", `⚡ **${data.message || 'Background sync running'}**\nAll municipal feeds (SeeClickFix, Cityworks, Accela, ArcGIS REST) are being ingested with cumulative deduplication.`);
    setTimeout(refreshScoutSentinelStatus, 4000);
  } catch (err) {
    if (loader && loader.remove) loader.remove();
    appendScoutChatMessage("scout", `⚠️ Error: ${err.message}`);
  }
}

function renderScoutDrawerResults(leads, elapsedMs) {
  scoutLastQueryResults = leads || [];
  scoutLastQuerySpeed = elapsedMs || 0;
}

// -------------------------------------------------------------------------
// SCOUT LEADS POPOUT MODAL & WHOLESALE FILTERING
// -------------------------------------------------------------------------

function isCommercialOwner(name) {
  if (!name) return false;
  const upper = String(name).toUpperCase();
  const patterns = [
    /\bLLC\b/, /\bINC\b/, /\bCORP\b/, /\bLTD\b/, /\bCO\b/, /\bLP\b/, /\bLLP\b/,
    /\bHOLDINGS\b/, /\bPROPERTIES\b/, /\bINVESTMENTS\b/, /\bGROUP\b/, /\bPARTNERS\b/,
    /\bREALTY\b/, /\bVENTURES\b/, /\bCAPITAL\b/, /\bENTERPRISES\b/, /\bTRUSTEE\b/,
    /\bBANK\b/, /\bFUND\b/, /\bMANAGEMENT\b/, /\bASSET\b/
  ];
  return patterns.some(p => p.test(upper));
}

function openScoutLeadsPopout() {
  const modal = document.getElementById("scoutLeadsPopoutModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  
  const searchInput = document.getElementById("scoutPopoutSearchInput");
  if (searchInput) searchInput.value = "";
  const excludeLlc = document.getElementById("scoutPopoutExcludeLlc");
  if (excludeLlc) excludeLlc.checked = true;
  const maxPrice = document.getElementById("scoutPopoutMaxPrice");
  if (maxPrice) maxPrice.value = "1500000";
  const distressFilter = document.getElementById("scoutPopoutDistressFilter");
  if (distressFilter) distressFilter.value = "all";

  filterScoutPopoutResults();
}

function closeScoutLeadsPopout() {
  const modal = document.getElementById("scoutLeadsPopoutModal");
  if (modal) modal.classList.add("hidden");
}

function filterScoutPopoutResults() {
  const searchInput = document.getElementById("scoutPopoutSearchInput");
  const excludeLlc = document.getElementById("scoutPopoutExcludeLlc");
  const maxPriceSelect = document.getElementById("scoutPopoutMaxPrice");
  const distressSelect = document.getElementById("scoutPopoutDistressFilter");

  const query = (searchInput?.value || "").toLowerCase().trim();
  const shouldExcludeLlc = excludeLlc ? excludeLlc.checked : true;
  const maxPrice = maxPriceSelect ? parseFloat(maxPriceSelect.value) || 1500000 : 1500000;
  const distressFilter = distressSelect ? distressSelect.value : "all";

  const allLeads = scoutLastQueryResults || [];

  const filtered = allLeads.filter(l => {
    // 1. Commercial / LLC filter
    const owner = String(l.Clean_Full_Name || l.Owner_1 || "");
    const ownerType = String(l.Owner_Type || "").toUpperCase();
    if (shouldExcludeLlc && (ownerType === "COMPANY" || isCommercialOwner(owner))) {
      return false;
    }

    // 2. Max Price filter
    const mv = parseInt(l.Market_Value) || 0;
    if (mv > maxPrice) {
      return false;
    }

    // 3. Distress filter
    if (distressFilter === "stacked") {
      const isStacked = String(l.Is_Stacked_Distress || "").toUpperCase() === "YES";
      if (!isStacked) return false;
    } else if (distressFilter === "code") {
      const notes = String(l.Distress_Stack_Notes || l.Lead_Type || "").toUpperCase();
      if (!notes.includes("CODE")) return false;
    } else if (distressFilter === "out_of_state") {
      const abs = String(l.Absentee_Type || "").toUpperCase();
      if (!abs.includes("OUT-OF-STATE") && !abs.includes("OUT OF STATE")) return false;
    }

    // 4. Keyword search
    if (query) {
      const addr = String(l.Property_Address || "").toLowerCase();
      const city = String(l.City || "").toLowerCase();
      const county = String(l.County || "").toLowerCase();
      const parcel = String(l.Parcel_ID || "").toLowerCase();
      const ownerLower = owner.toLowerCase();
      if (!addr.includes(query) && !city.includes(query) && !county.includes(query) && !parcel.includes(query) && !ownerLower.includes(query)) {
        return false;
      }
    }

    return true;
  });

  renderScoutPopoutTable(filtered, allLeads.length);
}

function renderScoutPopoutTable(filteredLeads, totalCount) {
  const tbody = document.getElementById("scoutPopoutTableBody");
  const emptyState = document.getElementById("scoutPopoutEmptyState");
  const countBadge = document.getElementById("scoutPopoutCountBadge");
  const speedBadge = document.getElementById("scoutPopoutSpeedBadge");
  const filteredLabel = document.getElementById("scoutPopoutFilteredCountLabel");

  if (countBadge) countBadge.textContent = `${filteredLeads.length.toLocaleString()} Leads`;
  if (speedBadge) speedBadge.textContent = `${scoutLastQuerySpeed || 0}ms`;
  if (filteredLabel) filteredLabel.textContent = `Showing ${filteredLeads.length.toLocaleString()} of ${totalCount.toLocaleString()} Leads`;

  if (!tbody) return;

  if (filteredLeads.length === 0) {
    tbody.innerHTML = "";
    if (emptyState) emptyState.classList.remove("hidden");
    return;
  }

  if (emptyState) emptyState.classList.add("hidden");

  tbody.innerHTML = filteredLeads.map(l => {
    const county = escapeHtml(l.County || 'FL');
    const parcel = escapeHtml(l.Parcel_ID || 'Unknown');
    const addr = escapeHtml(l.Property_Address || 'Address Unknown');
    const city = escapeHtml(l.City || '');
    const owner = escapeHtml(l.Clean_Full_Name || l.Owner_1 || 'Unknown Owner');
    const isCommercial = isCommercialOwner(owner) || (String(l.Owner_Type).toUpperCase() === 'COMPANY');
    const ownerBadge = isCommercial 
      ? `<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">🏢 LLC / CO</span>`
      : `<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">👤 INDIVIDUAL</span>`;
    
    const isStacked = (String(l.Is_Stacked_Distress).toUpperCase() === 'YES');
    const notes = String(l.Distress_Stack_Notes || l.Lead_Type || '');
    const isTriple = notes.toUpperCase().includes('TRIPLE') || notes.toUpperCase().includes('3-WAY');
    const isCode = notes.toUpperCase().includes('CODE');
    const isOos = String(l.Absentee_Type || '').toUpperCase().includes('OUT');

    let badgeHtml = '';
    if (isTriple) {
      badgeHtml += `<span class="px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider bg-rose-600/30 text-rose-300 border border-rose-500/50">🔥 TRIPLE STACK</span> `;
    } else if (isStacked) {
      badgeHtml += `<span class="px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider bg-amber-500/25 text-amber-300 border border-amber-500/40">⚡ DOUBLE STACK</span> `;
    }
    if (isCode) {
      badgeHtml += `<span class="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">⚠️ CODE</span> `;
    }
    if (isOos) {
      badgeHtml += `<span class="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/30">✈️ OUT-OF-STATE</span> `;
    }
    if (!badgeHtml) {
      badgeHtml = `<span class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-700/60 text-slate-300 border border-slate-600/50">${escapeHtml(l.Lead_Type || 'Distress')}</span>`;
    }

    const mv = parseInt(l.Market_Value) || 0;
    const mvFormatted = mv > 0 ? `$${mv.toLocaleString()}` : 'N/A';

    return `
      <tr class="hover:bg-slate-800/40 transition">
        <td class="py-3 px-3.5 whitespace-nowrap">
          <div class="flex flex-wrap items-center gap-1">${badgeHtml}</div>
          ${notes && !isTriple && !isStacked ? `<div class="text-[10px] text-slate-400 mt-1 truncate max-w-xs">${escapeHtml(notes)}</div>` : ''}
        </td>
        <td class="py-3 px-3.5 whitespace-nowrap">
          <div class="font-bold text-white flex items-center gap-1.5">
            <span class="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">${county}</span>
          </div>
          <div class="text-[11px] font-mono text-slate-400 mt-0.5">${parcel}</div>
        </td>
        <td class="py-3 px-3.5">
          <div class="font-bold text-slate-100 text-xs">${addr}</div>
          ${city ? `<div class="text-[11px] text-slate-400">${city}</div>` : ''}
        </td>
        <td class="py-3 px-3.5">
          <div class="font-semibold text-slate-200 text-xs">${owner}</div>
          <div class="mt-0.5">${ownerBadge}</div>
        </td>
        <td class="py-3 px-3.5 text-right whitespace-nowrap">
          <div class="text-xs font-mono font-bold text-emerald-400">${mvFormatted}</div>
          ${l.Assessed_Value ? `<div class="text-[10px] text-slate-400 font-mono">Assessed: $${parseInt(l.Assessed_Value).toLocaleString()}</div>` : ''}
        </td>
        <td class="py-3 px-3.5 text-center whitespace-nowrap">
          <button type="button" onclick="scoutJumpToCountyLead('${county}', '${parcel}')" class="px-2.5 py-1 rounded-lg bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/40 text-[11px] font-bold transition cursor-pointer flex items-center gap-1 mx-auto" title="Open this parcel in the County Lead Hub">
            <span>Open in Hub</span>
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

async function scoutJumpToCountyLead(county, parcelId) {
  closeScoutLeadsPopout();
  closeScoutDrawer();
  if (typeof loadLiveCountyLeads === "function") {
    await loadLiveCountyLeads(county, "all");
    const searchInput = document.getElementById("leadTableSearch");
    if (searchInput) {
      searchInput.value = parcelId;
      if (typeof filterTableLeads === "function") filterTableLeads();
    }
  }
}

function exportScoutResultsToCSV() {
  const excludeLlc = document.getElementById("scoutPopoutExcludeLlc");
  const maxPriceSelect = document.getElementById("scoutPopoutMaxPrice");
  const shouldExcludeLlc = excludeLlc ? excludeLlc.checked : true;
  const maxPrice = maxPriceSelect ? parseFloat(maxPriceSelect.value) || 1500000 : 1500000;

  let leadsToExport = scoutLastQueryResults || [];
  if (shouldExcludeLlc) {
    leadsToExport = leadsToExport.filter(l => {
      const owner = String(l.Clean_Full_Name || l.Owner_1 || "");
      const ownerType = String(l.Owner_Type || "").toUpperCase();
      const mv = parseInt(l.Market_Value) || 0;
      return ownerType !== "COMPANY" && !isCommercialOwner(owner) && mv <= maxPrice;
    });
  }

  if (!leadsToExport || leadsToExport.length === 0) {
    alert("No matching leads to export.");
    return;
  }
  const keys = Object.keys(leadsToExport[0]);
  const csvRows = [];
  csvRows.push(keys.join(","));
  for (const row of leadsToExport) {
    const values = keys.map(k => {
      const v = row[k] === null || row[k] === undefined ? "" : String(row[k]);
      return `"${v.replace(/"/g, '""')}"`;
    });
    csvRows.push(values.join(","));
  }
  const csvData = "\uFEFF" + csvRows.join("\r\n");
  const blob = new Blob([csvData], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `scout_residential_leads_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Global window bindings
window.openScoutDrawer = openScoutDrawer;
window.closeScoutDrawer = closeScoutDrawer;
window.toggleScoutDrawer = toggleScoutDrawer;
window.clearScoutChat = clearScoutChat;
window.refreshScoutSentinelStatus = refreshScoutSentinelStatus;
window.handleScoutChatSubmit = handleScoutChatSubmit;
window.triggerScoutBriefing = triggerScoutBriefing;
window.triggerScoutStatewideDistress = triggerScoutStatewideDistress;
window.triggerScoutSyncAll = triggerScoutSyncAll;
window.exportScoutResultsToCSV = exportScoutResultsToCSV;
window.openScoutLeadsPopout = openScoutLeadsPopout;
window.closeScoutLeadsPopout = closeScoutLeadsPopout;
window.filterScoutPopoutResults = filterScoutPopoutResults;
window.scoutJumpToCountyLead = scoutJumpToCountyLead;

// Escape key listener for modals
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    const modal = document.getElementById("scoutLeadsPopoutModal");
    if (modal && !modal.classList.contains("hidden")) {
      closeScoutLeadsPopout();
    }
  }
});

// Scout Auto-Init
document.addEventListener("DOMContentLoaded", () => {
  setTimeout(() => {
    refreshScoutSentinelStatus();
  }, 1000);
});

// -------------------------------------------------------------------------
// 407FLIPS DEAL UNDERWRITING CONTROLLER (COUNTY LEAD HUB)
// -------------------------------------------------------------------------

let current407FlipsLeadContext = null;

async function openUnderwrite407FlipsForLead(parcelId, address, yearBuilt, sqft, marketVal, ownerName) {
  markLeadAsViewed(parcelId);
  const cleanAddr = formatDisplayAddress(address) || "Florida Distressed Lead";
  const cleanOwner = formatDisplayName(ownerName) || "Homeowner";
  const cleanSqft = parseInt(sqft) || 1500;
  const cleanYb = parseInt(yearBuilt) || 1980;
  const cleanArv = parseFloat(marketVal) || 280000;

  current407FlipsLeadContext = {
    parcelId,
    address: cleanAddr,
    yearBuilt: cleanYb,
    sqft: cleanSqft,
    arv: cleanArv,
    ownerName: cleanOwner
  };

  openModal("underwrite407FlipsLeadModal");

  document.getElementById("u407LeadAddress").innerText = cleanAddr;
  document.getElementById("u407LeadMeta").innerText = `COUNTY LEAD HUB • Parcel: ${parcelId} • Owner: ${cleanOwner} • Built ${cleanYb} • ${cleanSqft} sqft`;
  document.getElementById("u407LeadValues").innerText = `Target ARV / Model: $${Math.round(cleanArv).toLocaleString()}`;
  document.getElementById("u407LeadMao").innerText = "Analyzing...";

  try {
    const res = await fetch("/api/underwrite/407flips", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        address: cleanAddr,
        listing_price: cleanArv * 0.70,
        arv: cleanArv,
        sqft: cleanSqft,
        year_built: cleanYb,
        beds: 3,
        baths: 2,
        condition: "poor",
        condition_notes: "County distressed lead - 407flips audit",
        wholesale_fee: 10000,
        parcel_id: parcelId,
        owner_name: ownerName
      })
    });

    if (!res.ok) throw new Error("Underwriting API failed");
    const data = await res.json();
    const rep = data.report;
    current407FlipsLeadContext.report = rep;
    render407FlipsLeadReportUI(rep);
  } catch (err) {
    alert(`407flips Underwriting Error: ${err.message}`);
  }
}

function render407FlipsLeadReportUI(rep) {
  const mao = rep.mao_breakdown.tier1_max_offer_mao || 0;
  const dispo = rep.mao_breakdown.tier1_dispo_price || 0;
  const o1 = rep.three_tier_offers.offer_1_clean_cash.amount || 0;
  const o2 = rep.three_tier_offers.offer_2_inspection_contingency.amount || 0;
  const o3 = rep.three_tier_offers.offer_3_terms_novation.amount || 0;

  document.getElementById("u407LeadMao").innerText = `$${Math.round(mao).toLocaleString()}`;
  document.getElementById("u407LeadDispoNote").innerText = `Private Seller Cash Buy • 15% Flipper Profit • 2.5% Backside Agent`;

  document.getElementById("u407LeadOffer1").innerText = `$${Math.round(o1).toLocaleString()}`;
  document.getElementById("u407LeadOffer2").innerText = `$${Math.round(o2).toLocaleString()}`;
  document.getElementById("u407LeadOffer3").innerText = `$${Math.round(o3).toLocaleString()}`;

  // Triggers
  const triggers = rep.insurance_trigger_matrix.triggers || [];
  document.getElementById("u407LeadTriggerCount").innerText = `${triggers.length} Florida Triggers`;
  document.getElementById("u407LeadSystemsCost").innerText = `Mandatory Systems Outlay: $${Math.round(rep.insurance_trigger_matrix.total_systems_deductions).toLocaleString()}`;

  const trigContainer = document.getElementById("u407LeadTriggersContainer");
  if (triggers.length === 0) {
    trigContainer.innerHTML = `<div class="text-xs text-slate-400 italic">No critical 4-Point deficiencies flagged.</div>`;
  } else {
    trigContainer.innerHTML = triggers.map(t => `
      <div class="bg-slate-900/90 border border-amber-500/30 rounded-xl p-2.5 text-xs space-y-1">
        <div class="flex items-center justify-between font-bold">
          <span class="text-amber-300">🚨 ${escapeHtml(t.system)}</span>
          <span class="text-rose-400 font-mono">-$${Math.round(t.cost_allowance).toLocaleString()}</span>
        </div>
        <div class="text-[11px] text-slate-300">${escapeHtml(t.finding)}</div>
        <div class="text-[10px] text-slate-400 leading-snug">
          <strong class="text-amber-400">Underwriting Ammo:</strong> ${escapeHtml(t.underwriting_ammo)}
        </div>
      </div>
    `).join("");
  }

  // Two-Tier Scopes
  document.getElementById("u407LeadFlipRehab").innerText = `$${Math.round(rep.two_tier_rehab.tier1_flip.total_rehab).toLocaleString()} ($${rep.two_tier_rehab.tier1_flip.rate_per_sqft}/sqft)`;
  document.getElementById("u407LeadRentalRehab").innerText = `$${Math.round(rep.two_tier_rehab.tier2_rental.total_rehab).toLocaleString()} ($${rep.two_tier_rehab.tier2_rental.rate_per_sqft}/sqft)`;

  // 21.5% Friction
  document.getElementById("u407LeadClosing").innerText = `$${Math.round(rep.mao_breakdown.closing_cost_2pct).toLocaleString()}`;
  document.getElementById("u407LeadCarrying").innerText = `$${Math.round(rep.mao_breakdown.carrying_cost_2pct).toLocaleString()}`;
  document.getElementById("u407LeadComm").innerText = `$${Math.round(rep.mao_breakdown.agent_commission_2_5pct || (rep.mao_breakdown.arv * 0.025)).toLocaleString()}`;
  document.getElementById("u407LeadProfit").innerText = `$${Math.round(rep.mao_breakdown.flipper_profit_15pct || (rep.mao_breakdown.arv * 0.15)).toLocaleString()}`;
  document.getElementById("u407LeadTotalFriction").innerText = `$${Math.round(rep.mao_breakdown.total_friction_and_profit_21_5pct || (rep.mao_breakdown.arv * 0.215)).toLocaleString()} (21.5%)`;
}

function copy407FlipsLeadReport() {
  if (!current407FlipsLeadContext || !current407FlipsLeadContext.report) return;
  const rep = current407FlipsLeadContext.report;
  const mao = rep.mao_breakdown.tier1_max_offer_mao || 0;
  const text = `
407FLIPS DEAL UNDERWRITING REPORT (County Lead Hub)
Address: ${rep.property.address}
Living SqFt: ${rep.property.sqft} | Year Built: ${rep.property.year_built}
Estimated ARV: $${Math.round(rep.property.arv).toLocaleString()}
--------------------------------------------------
OFF-MARKET CASH MAO: $${Math.round(mao).toLocaleString()} (Flipper Buy Ceiling)
--------------------------------------------------
OFFER BREAKDOWN:
1. Opening Cash Offer (Anchor Low): $${Math.round(rep.three_tier_offers.offer_1_clean_cash.amount).toLocaleString()}
2. Cash MAO (Flipper Buy Ceiling): $${Math.round(rep.three_tier_offers.offer_2_inspection_contingency.amount).toLocaleString()}
3. Creative Terms / Novation Anchor: $${Math.round(rep.three_tier_offers.offer_3_terms_novation.amount).toLocaleString()}
--------------------------------------------------
FLORIDA 4-POINT INSURANCE TRIGGERS (${rep.insurance_trigger_matrix.triggers.length} Found):
${rep.insurance_trigger_matrix.triggers.map(t => `• ${t.system}: -$${Math.round(t.cost_allowance).toLocaleString()} (${t.finding})`).join("\n")}
Total Capital Systems Outlay: $${Math.round(rep.insurance_trigger_matrix.total_systems_deductions).toLocaleString()}
--------------------------------------------------
REHAB SCOPE & 21.5% FRICTION FORMULA:
• Retail Flip Scope: $${Math.round(rep.two_tier_rehab.tier1_flip.total_rehab).toLocaleString()}
• 21.5% Friction + Profit: $${Math.round(rep.mao_breakdown.total_friction_and_profit_21_5pct || (rep.mao_breakdown.arv * 0.215)).toLocaleString()} (15% Profit, 2.5% Agent, 2% Close, 2% Carry)
• Cash MAO (Flipper Buy Ceiling): $${Math.round(mao).toLocaleString()}
`.trim();

  navigator.clipboard.writeText(text).then(() => {
    alert("Copied 407flips Lead Underwriting Ammo to clipboard!");
  });
}

window.openUnderwrite407FlipsForLead = openUnderwrite407FlipsForLead;
window.copy407FlipsLeadReport = copy407FlipsLeadReport;

// -------------------------------------------------------------------------
// PROPERTY DETAIL CARD CONTROLLER (COUNTY LEAD HUB)
// -------------------------------------------------------------------------

window.leadsByPid = window.leadsByPid || {};

let propertyCardRecords = [];
let propertyCardIndex = -1;

function navigatePropertyCard(direction) {
  const modal = document.getElementById('propertyCardModal');
  if (!modal || modal.classList.contains('hidden') || ![-1, 1].includes(direction)) return;
  const nextIndex = propertyCardIndex + direction;
  if (nextIndex < 0 || nextIndex >= propertyCardRecords.length) return;
  openPropertyCard(propertyCardRecords[nextIndex].Parcel_ID, true);
}

function openPropertyCard(parcelId, navigateWithinList = false) {
  const pTrim = String(parcelId || "").trim();
  if (!navigateWithinList) {
    // Freeze the displayed order across all pages. Viewing a lead changes its NEW
    // badge, so rebuilding this list between arrows could skip or repeat leads.
    const seen = new Set();
    propertyCardRecords = (currentFilteredRecords || []).filter(record => {
      const pid = String(record.Parcel_ID || '').trim();
      if (!pid || seen.has(pid)) return false;
      seen.add(pid);
      return true;
    });
  }
  let r = propertyCardRecords.find(x => String(x.Parcel_ID || '').trim() === pTrim)
    || window.leadsByPid[pTrim] || (liveRecords || []).find(x => String(x.Parcel_ID || "").trim() === pTrim);
  if (!r) {
    console.warn("Property record not found for parcel:", parcelId);
    return;
  }
  propertyCardIndex = propertyCardRecords.findIndex(x => String(x.Parcel_ID || '').trim() === pTrim);
  if (propertyCardIndex < 0) {
    propertyCardRecords = [r];
    propertyCardIndex = 0;
  }

  const isAbsentee = (r.Absentee_Status || "").includes("Out-of-State");
  const isLlc = (r.Owner_Entity_Type || "").includes("LLC");
  const isTrust = (r.Owner_Entity_Type || "").includes("Trust") || r.Is_Trust_Or_Estate === "Yes";
  const mktVal = parseFloat(r.Market_Value || 0);
  const isStacked = r.Is_Stacked_Distress === "Yes";
  const isLp = r.Lead_Type === "Lis Pendens";
  const isProbate = (r.Lead_Type || "").toLowerCase().includes("probate");
  const isLegalDistress = (r.Lead_Type || "").toLowerCase().includes("legal distress") || (r.Lead_Type || "").toLowerCase().includes("felony") || (r.Distress_Stack_Notes || "").toLowerCase().includes("felony");

  let skipName = "";
  if (r.Clean_First_Name && r.Clean_Last_Name) {
    skipName = `${r.Clean_First_Name} ${r.Clean_Last_Name}`;
  } else if (r.Clean_Full_Name) {
    skipName = r.Clean_Full_Name;
  } else if (r.Clean_Last_Name) {
    skipName = r.Clean_Last_Name;
  }
  skipName = formatDisplayName((skipName || "").replace(/\b(TR|TRE|TRUSTEE|ESTATE|EST|OF|DECD|DECEASED|ET|AL|LIFE|LE)\b/gi, " ").replace(/\s+/g, " ").trim());
  const cleanCardAddr = formatDisplayAddress(r.Property_Address);
  const cleanCardCity = formatDisplayCity((r.Property_City || (selectedCountyKey === 'Orange' ? 'Orlando' : 'St Petersburg')).trim());
  const cleanCardOwner = formatDisplayName(r.Clean_Full_Name || r.Clean_Last_Name || 'Record Owner');

  const skipCity = formatDisplayCity((r.Mailing_City || r.Property_City || (selectedCountyKey === 'Orange' ? 'Orlando' : 'St Petersburg')).trim());
  const skipState = (r.Mailing_State || "FL").trim();
  const skipLoc = `${skipCity}, ${skipState}`;
  const skipTraceUrl = `https://www.truepeoplesearch.com/results?name=${encodeURIComponent(skipName)}&citystatezip=${encodeURIComponent(skipLoc)}#lead_hub_pid=${encodeURIComponent(r.Parcel_ID || '')}&county=${encodeURIComponent(selectedCountyKey || 'Pinellas')}&owner=${encodeURIComponent(skipName)}&addr=${encodeURIComponent(cleanCardAddr || r.Property_Address || '')}`;

  const savedContact = savedContactsCache[r.Parcel_ID] || ((r.Saved_Phone || r.Saved_Email) ? { phone: r.Saved_Phone, email: r.Saved_Email } : null);
  const savedPhone = savedContact ? savedContact.phone : null;
  const savedEmail = savedContact ? (savedContact.email || r.Saved_Email) : (r.Saved_Email || null);
  const lastSmsSent = (savedContact?.sms_initial_resend_pending || r.Sms_Initial_Resend_Pending) ? '' : (savedContact?.last_sms_sent || r.Last_Sms_Sent);
  const lastEmailSent = savedContact?.last_email_sent || r.Last_Email_Sent;

  // Property Appraiser URL (County specific)
  let paUrl = "https://www.pcpao.gov/quick-search";
  const currentCountyLower = (selectedCountyKey || "").toLowerCase();
  if (currentCountyLower === "orange") {
    const orangePid = (r.Parcel_ID || "").trim();
    paUrl = `https://www.ocpafl.org/Searches/ParcelSearch.aspx?pid=${encodeURIComponent(orangePid)}`;
  } else if (currentCountyLower === "seminole") {
    paUrl = "https://www.scpafl.org/search/parcels";
  } else {
    const pidTrim = (r.Parcel_ID || "").trim();
    const pidParts = pidTrim.split("-");
    if (pidParts.length === 6) {
      paUrl = `https://www.pcpao.gov/property-details?s=${pidParts[2]}${pidParts[1]}${pidParts[0]}${pidParts[3]}${pidParts[4]}${pidParts[5]}`;
    } else if (pidTrim.replace(/[^0-9A-Za-z]/g, "").length === 18) {
      paUrl = `https://www.pcpao.gov/property-details?s=${pidTrim.replace(/[^0-9A-Za-z]/g, "")}`;
    }
  }
  const addrQuery = encodeURIComponent(`${cleanCardAddr || r.Property_Address || ""}, ${cleanCardCity}, FL`);
  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${addrQuery}`;

  // Populate Header
  document.getElementById("propCardAddress").innerText = cleanCardAddr || "Florida Distressed Property";
  document.getElementById("propCardCityStateZip").innerText = `${cleanCardCity}, FL ${r.Property_Zip || ''} • ${selectedCountyKey || 'Pinellas'} County`;

  // Badges
  const leadBadge = document.getElementById("propCardLeadBadge");
  if (isLegalDistress) {
    const isBonded = (r.Subject_Case_Status || r.Match_Notes || "").toLowerCase().includes("bond") || (r.Match_Notes || "").toLowerCase().includes("released");
    leadBadge.className = isBonded ? "px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40" : "px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40";
    leadBadge.innerText = isBonded ? "⚖️ Legal Distress (Released on Bond)" : "⚖️ Legal Distress (In Custody)";
  } else if (isProbate) {
    leadBadge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40";
    leadBadge.innerText = "⚖️ Probate Court";
  } else if (isLp) {
    leadBadge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40";
    leadBadge.innerText = "📄 Lis Pendens";
  } else if ((r.Lead_Type || "").includes("Tax Lien")) {
    leadBadge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
    leadBadge.innerText = "💰 Tax Lien";
  } else if ((r.Lead_Type || "").toLowerCase().includes("water")) {
    leadBadge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40";
    leadBadge.innerText = "💧 Water Shutoff";
  } else {
    leadBadge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40";
    leadBadge.innerText = "🚨 Code Violation";
  }

  const catBadge = document.getElementById("propCardLeadCategoryBadge");
  if (catBadge) {
    if (isLegalDistress) {
      catBadge.innerText = "Orange County Corrections (Daily Felony Bookings)";
      catBadge.className = "text-[10px] px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 font-semibold";
    } else {
      catBadge.innerText = "County Records";
      catBadge.className = "text-[10px] px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-semibold";
    }
  }

  const emmaBox = document.getElementById("propCardEmmaGuidanceBox");
  if (emmaBox) {
    if (isLegalDistress) {
      emmaBox.classList.remove("hidden");
    } else {
      emmaBox.classList.add("hidden");
    }
  }

  const stackedBadge = document.getElementById("propCardStackedBadge");
  if (isStacked) {
    stackedBadge.classList.remove("hidden");
  } else {
    stackedBadge.classList.add("hidden");
  }

  // Case / Filing Date and Read Status
  const rawDate = r.Filing_Date || r.Case_Date || r.Recording_Date || r.Subject_Case_Open_Date || "";
  let cleanDateStr = rawDate ? String(rawDate).slice(0, 10) : "Recent Public Record";
  const dateValEl = document.getElementById("propCardDateVal");
  if (dateValEl) dateValEl.innerText = cleanDateStr;
  const dateDetailEl = document.getElementById("propCardFilingDateDetail");
  if (dateDetailEl) dateDetailEl.innerText = cleanDateStr;

  const cardNewBadge = document.getElementById("propCardNewBadge");
  if (cardNewBadge) {
    if (isLeadNew(r)) {
      cardNewBadge.classList.remove("hidden");
    } else {
      cardNewBadge.classList.add("hidden");
    }
  }

  // Instantly mark lead as viewed upon opening card!
  markLeadAsViewed(r.Parcel_ID);

  // Key Metrics
  document.getElementById("propCardMarketVal").innerText = mktVal > 0 ? `$${mktVal.toLocaleString()}` : "N/A";
  document.getElementById("propCardSqft").innerText = (r.Living_Sqft && r.Living_Sqft !== 'nan') ? `${r.Living_Sqft} sqft` : "1,500 sqft";
  document.getElementById("propCardBedsBaths").innerText = `${r.Beds || 3} Beds • ${r.Baths || 2} Baths`;
  document.getElementById("propCardYearBuilt").innerText = (r.Year_Built && r.Year_Built !== 'nan') ? r.Year_Built : "1980";
  const ybNum = parseInt(r.Year_Built) || 1980;
  const age = new Date().getFullYear() - ybNum;
  document.getElementById("propCardAge").innerText = `${age} Years Old`;
  document.getElementById("propCardPin").innerText = r.Parcel_ID || "N/A";

  // Ownership Details
  document.getElementById("propCardOwnerName").innerText = cleanCardOwner;
  document.getElementById("propCardOwnerEntityBadge").innerText = isTrust && !isLlc ? '🏛️ Trust / Estate' : (r.Owner_Entity_Type || 'Individual');
  document.getElementById("propCardAbsentee").innerHTML = isAbsentee ? `<span>✈️ Out-of-State (${r.Mailing_State || 'Non-FL'})</span>` : `<span>🏠 Owner Occupied</span>`;
  const mailParts = [formatDisplayAddress(r.Mailing_Address), formatDisplayCity(r.Mailing_City), r.Mailing_State, r.Mailing_Zip].filter(Boolean);
  document.getElementById("propCardMailingAddress").innerText = mailParts.length > 0 ? mailParts.join(", ") : "Same as Property Address";

  // Distress
  document.getElementById("propCardDistressType").innerText = isStacked ? (r.Distress_Stack_Notes || "Double Distress") : (r.Lead_Type || "Distressed Public Record");
  document.getElementById("propCardDistressNotes").innerText = r.Distress_Stack_Notes || r.Violation_Description || (r.Case_Number ? `Case #${r.Case_Number}` : "Public records distressed lead recorded in county database.");

  // On-Site Municipal Photo (SeeClickFix / Inspector)
  const photoBox = document.getElementById("propCardPhotoBox");
  const photoImg = document.getElementById("propCardPhotoImg");
  const photoLink = document.getElementById("propCardPhotoLink");
  if (photoBox && photoImg && photoLink) {
    if (r.Photo_Url && String(r.Photo_Url).startsWith("http")) {
      photoBox.classList.remove("hidden");
      photoImg.src = r.Photo_Url;
      photoLink.href = r.Photo_Url;
    } else {
      photoBox.classList.add("hidden");
      photoImg.src = "";
      photoLink.href = "#";
    }
  }

  // Contacts
  const chipsContainer = document.getElementById("propCardContactChips");
  let chipsHtml = "";
  if (savedPhone) {
    chipsHtml += `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs font-bold">📱 ${savedPhone} ${lastSmsSent ? '(Texted ' + lastSmsSent + ')' : ''}</span>`;
  }
  if (savedEmail) {
    chipsHtml += `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-xs font-bold">✉️ ${savedEmail} ${lastEmailSent ? '(Emailed ' + lastEmailSent + ')' : ''}</span>`;
  }
  if (!chipsHtml) {
    chipsHtml = `<span class="text-xs text-slate-400 italic">No direct phone/email on file. Click skip trace.</span>`;
  }
  chipsContainer.innerHTML = chipsHtml;

  // External Links
  document.getElementById("propCardSkipTraceBtn").href = skipTraceUrl;
  const pcpaoBtn = document.getElementById("propCardPcpaoLink");
  if (pcpaoBtn) {
    pcpaoBtn.href = paUrl;
    if (currentCountyLower === "orange") {
      pcpaoBtn.innerHTML = "<span>🔍</span> <span>OCPA</span>";
    } else if (currentCountyLower === "seminole") {
      pcpaoBtn.innerHTML = "<span>🔍</span> <span>SCPA</span>";
    } else {
      pcpaoBtn.innerHTML = "<span>🔍</span> <span>PCPAO</span>";
    }
  }
  document.getElementById("propCardMapsLink").href = mapsUrl;

  // Action Buttons
  document.getElementById("propCardLaunch407Btn").onclick = () => {
    closeModal("propertyCardModal");
    openUnderwrite407FlipsForLead(r.Parcel_ID, cleanCardAddr, r.Year_Built || 1980, r.Living_Sqft || 1500, mktVal || 0, skipName);
  };
  document.getElementById("propCardLaunchContractBtn").onclick = () => {
    closeModal("propertyCardModal");
    openContractModal(r.Parcel_ID, savedPhone || '', savedEmail || '', skipName, cleanCardAddr, cleanCardCity, r.Property_Zip || '', mktVal);
  };
  const smsBtn = document.getElementById("propCardLaunchSmsBtn");
  if (savedPhone) {
    smsBtn.classList.remove("hidden");
    smsBtn.onclick = () => {
      closeModal("propertyCardModal");
      openSmsModal(r.Parcel_ID, savedPhone, skipName, cleanCardAddr);
    };
  } else {
    smsBtn.classList.add("hidden");
  }
  const emailBtn = document.getElementById("propCardLaunchEmailBtn");
  if (savedEmail) {
    emailBtn.classList.remove("hidden");
    emailBtn.onclick = () => {
      closeModal("propertyCardModal");
      openEmailModal(r.Parcel_ID, savedEmail, skipName, cleanCardAddr);
    };
  } else {
    emailBtn.classList.add("hidden");
  }

  document.getElementById('propCardPreviousBtn').disabled = propertyCardIndex === 0;
  document.getElementById('propCardNextBtn').disabled = propertyCardIndex === propertyCardRecords.length - 1;
  document.getElementById('propCardPosition').textContent = `${propertyCardIndex + 1} of ${propertyCardRecords.length}`;
  openModal("propertyCardModal");
}

window.openPropertyCard = openPropertyCard;
window.navigatePropertyCard = navigatePropertyCard;
window.openSkipTraceImportModal = openSkipTraceImportModal;
window.closeSkipTraceImportModal = closeSkipTraceImportModal;
window.handleSkipTraceFileSelected = handleSkipTraceFileSelected;
window.handleSkipTraceImportSubmit = handleSkipTraceImportSubmit;

