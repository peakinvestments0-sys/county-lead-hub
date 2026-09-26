// Florida Lead Hub Helper - Popup JS
document.addEventListener("DOMContentLoaded", async () => {
  const statusEl = document.getElementById("serverStatus");
  const leadNameEl = document.getElementById("leadName");
  const leadDetailsEl = document.getElementById("leadDetails");

  // Check backend server health
  try {
    const res = await fetch("http://localhost:8505/api/stats");
    if (res.ok) {
      statusEl.innerHTML = `<span class="dot dot-green"></span> Online (8505)`;
      statusEl.style.color = "#10b981";
    } else {
      throw new Error();
    }
  } catch (err) {
    statusEl.innerHTML = `<span class="dot dot-red"></span> Offline`;
    statusEl.style.color = "#ef4444";
  }

  // Load current lead from storage
  chrome.storage.local.get(["activeLead"], (res) => {
    if (res && res.activeLead && res.activeLead.parcel_id) {
      const lead = res.activeLead;
      leadNameEl.innerText = lead.owner || "Homeowner";
      leadDetailsEl.innerText = `PIN: ${lead.parcel_id} • ${lead.county || 'Florida'}`;
    }
  });
});
