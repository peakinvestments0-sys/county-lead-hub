// Florida Lead Hub Helper - Content Script
(function () {
  console.log("[FLH] Florida Lead Hub Helper extension active on:", window.location.href);

  const API_ENDPOINT = "http://localhost:8505/api/leads/update-contact";
  const PHONE_REGEX = /\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})/;
  const EMAIL_REGEX = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;

  // Parse URL hash if passed from Florida Lead Hub
  function parseHashParams() {
    if (!window.location.hash || !window.location.hash.includes("lead_hub_pid")) return null;
    const hashStr = window.location.hash.substring(1);
    const params = new URLSearchParams(hashStr);
    return {
      parcel_id: params.get("lead_hub_pid") || "",
      county: params.get("county") || "Pinellas",
      owner: params.get("owner") || "",
      address: params.get("addr") || ""
    };
  }

  // Handle lead storage
  let currentLead = null;
  const hashLead = parseHashParams();
  if (hashLead && hashLead.parcel_id) {
    currentLead = hashLead;
    chrome.storage.local.set({ activeLead: hashLead }, () => {
      console.log("[FLH] Active lead stored from URL hash:", hashLead);
      renderLeadBanner(hashLead);
    });
  } else {
    chrome.storage.local.get(["activeLead"], (res) => {
      currentLead = res?.activeLead || null;
      renderLeadBanner(currentLead);
    });
  }

  function renderLeadBanner(lead) {
    let banner = document.getElementById("flh-top-banner");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "flh-top-banner";
      banner.className = "flh-banner";

      // Attach to page
      const parent = document.body;
      if (parent) {
        if (parent.firstChild) {
          parent.insertBefore(banner, parent.firstChild);
        } else {
          parent.appendChild(banner);
        }
      }
    }

    const ownerName = lead?.owner || "Direct Search";
    const parcelId = lead?.parcel_id ? `PIN: <code>${lead.parcel_id}</code>` : "Manual Trace";
    const countyName = lead?.county || "Florida";

    banner.innerHTML = `
      <div style="display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 22px;">⚡</span>
        <div>
          <div class="flh-banner-title">Florida Lead Hub Connected</div>
          <div class="flh-banner-desc">Target: <strong style="color: #ffffff;">${ownerName}</strong> • ${parcelId} (${countyName})</div>
        </div>
      </div>
      <div id="flh-banner-action-area" style="display: flex; align-items: center; gap: 10px;">
        <span id="flh-banner-status-text" style="font-size: 11px; color: #38bdf8; font-weight: 600;">Scanning page for phone numbers & emails...</span>
      </div>
    `;
  }

  function updateBannerWithQuickPhone(phone, email) {
    const actionArea = document.getElementById("flh-banner-action-area");
    if (!actionArea) return;
    const key = `${phone}_${email || ''}`;
    if (actionArea.dataset.hasKey === key) return;
    actionArea.dataset.hasKey = key;

    actionArea.innerHTML = `
      <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 2px;">
        <span style="font-size: 11px; color: #94a3b8;">Cell: <strong style="color: #38bdf8; font-size: 12px;">${phone}</strong></span>
        ${email ? `<span style="font-size: 10px; color: #cbd5e1;">Email: <strong style="color: #34d399; font-family: monospace;">${email}</strong></span>` : ''}
      </div>
    `;
    const quickBtn = createPushButton(phone, email, true);
    actionArea.appendChild(quickBtn);
  }

  function extractPhone(str) {
    if (!str) return null;
    const clean = String(str).trim();
    const m = clean.match(PHONE_REGEX);
    return m ? m[0] : null;
  }

  function extractEmail(str) {
    if (!str) return null;
    const clean = String(str).trim();
    if (clean.includes("truepeoplesearch") || clean.endsWith(".png") || clean.endsWith(".jpg") || clean.endsWith(".svg")) {
      return null;
    }
    const m = clean.match(EMAIL_REGEX);
    return m ? m[0] : null;
  }

  function findPrimaryEmail() {
    // 1. Check mailto: or explicit email links
    const emailLinks = document.querySelectorAll('a[href^="mailto:"], a[data-link-to-more="email"]');
    for (const link of emailLinks) {
      const em = extractEmail(link.innerText || link.textContent || link.getAttribute("href"));
      if (em) return em;
    }
    // 2. Check content-value and small text containers
    const candidates = document.querySelectorAll('.content-value, span, div, p, a');
    for (const el of candidates) {
      if (el.closest("#flh-top-banner")) continue;
      const txt = (el.innerText || el.textContent || "").trim();
      if (txt.includes("@") && txt.length < 80) {
        const em = extractEmail(txt);
        if (em) return em;
      }
    }
    return null;
  }

  // Scan TruePeopleSearch DOM specifically for phone numbers & emails
  let isScanning = false;
  function scanAndInject() {
    if (isScanning) return;
    isScanning = true;

    try {
      let firstFoundPhone = null;
      const foundEmail = findPrimaryEmail();

      // 1. High-priority targeted phone elements on TruePeopleSearch
      const targetedElements = document.querySelectorAll(
        'a[href*="/find/phone/"], a[data-link-to-more="phone"], a[href^="tel:"], .content-value, span[itemprop="telephone"], div[data-detail-type="phone"]'
      );

      targetedElements.forEach(el => {
        if (el.closest("#flh-top-banner") || el.classList.contains("flh-push-btn")) return;
        const phone = extractPhone(el.innerText || el.textContent || el.getAttribute("href"));
        if (phone) {
          if (!firstFoundPhone) firstFoundPhone = phone;
          attachButtonToElement(el, phone, foundEmail);
        }
      });

      // 2. Broad search on leaf elements (links, spans, strong, b, h4) that contain a phone pattern
      const textContainers = document.querySelectorAll('a, span, strong, b, h4, h5, p');
      textContainers.forEach(el => {
        if (el.closest("#flh-top-banner") || el.closest(".flh-push-btn")) return;
        if (el.children.length > 1) return; // Only target near-leaf elements

        const txt = (el.innerText || el.textContent || "").trim();
        if (txt.length >= 10 && txt.length <= 40) {
          const phone = extractPhone(txt);
          if (phone) {
            if (!firstFoundPhone) firstFoundPhone = phone;
            attachButtonToElement(el, phone, foundEmail);
          }
        }
      });

      // Put primary button in top banner
      if (firstFoundPhone) {
        updateBannerWithQuickPhone(firstFoundPhone, foundEmail);
      } else {
        const statusText = document.getElementById("flh-banner-status-text");
        if (statusText) {
          statusText.innerText = "Navigate to person details or phone section...";
        }
      }
    } catch (e) {
      console.warn("[FLH] Error during phone/email scan:", e);
    } finally {
      isScanning = false;
    }
  }

  function attachButtonToElement(element, phone, email) {
    if (element.dataset.flhBound === "true") return;

    // Check if immediate next sibling is already a push button
    if (element.nextElementSibling && element.nextElementSibling.classList.contains("flh-push-btn")) {
      element.dataset.flhBound = "true";
      return;
    }

    element.dataset.flhBound = "true";
    const btn = createPushButton(phone, email, false);

    // Insert directly after the element
    if (element.parentNode) {
      if (element.nextSibling) {
        element.parentNode.insertBefore(btn, element.nextSibling);
      } else {
        element.parentNode.appendChild(btn);
      }
    }
  }

  function createPushButton(phone, email, isBanner = false) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `flh-push-btn ${isBanner ? 'flh-banner-btn' : ''}`;
    btn.innerHTML = `<span>🚀</span> <span>Push ${isBanner ? phone + ' ' : ''}to Lead Hub</span>`;
    btn.title = `Sync contact details directly into Florida Lead Hub for 1-click SMS & Email`;

    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();

      btn.disabled = true;
      btn.innerHTML = `<span>⏳</span> <span>Syncing...</span>`;

      chrome.storage.local.get(["activeLead"], async (res) => {
        const lead = res?.activeLead || currentLead || {};
        const cleanPhone = phone ? phone.replace(/[^0-9]/g, "") : "";
        const targetEmail = email || findPrimaryEmail() || "";

        const payload = {
          parcel_id: lead.parcel_id || "UNKNOWN",
          county: lead.county || "Pinellas",
          phone: phone ? phone.trim() : "",
          clean_phone: cleanPhone,
          email: targetEmail,
          owner: lead.owner || "",
          source: "TruePeopleSearch"
        };

        try {
          const response = await fetch(API_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });

          if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
          }

          const data = await response.json();
          console.log("[FLH] Successfully pushed contact to Lead Hub:", data);

          // Update all buttons on page
          document.querySelectorAll(".flh-push-btn").forEach(b => {
            b.classList.add("flh-saved");
            b.innerHTML = `<span>✓</span> <span>Saved to Lead Hub!</span>`;
          });

          const msgSummary = `${phone}${targetEmail ? ' & ' + targetEmail : ''}`;
          showToastNotification(`✓ ${msgSummary} saved to Lead Hub! Ready for 1-click SMS & Email.`);
        } catch (err) {
          console.error("[FLH] Error connecting to Lead Hub server:", err);
          btn.disabled = false;
          btn.style.background = "#dc2626";
          btn.innerHTML = `<span>⚠️</span> <span>Hub Offline</span>`;
          showToastNotification("⚠️ Could not reach http://localhost:8505. Make sure Lead Hub server is running.", true);
        }
      });
    });

    return btn;
  }

  function showToastNotification(msg, isError = false) {
    const existing = document.getElementById("flh-toast-msg");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.id = "flh-toast-msg";
    toast.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: ${isError ? '#991b1b' : '#065f46'};
      color: #ffffff;
      padding: 14px 22px;
      border-radius: 10px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 13px;
      font-weight: 700;
      box-shadow: 0 10px 25px rgba(0,0,0,0.6);
      z-index: 10000000;
      border: 1px solid ${isError ? '#f87171' : '#34d399'};
      display: flex;
      align-items: center;
      gap: 10px;
    `;
    toast.innerText = msg;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.transition = "opacity 0.4s";
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 400);
    }, 4500);
  }

  // Debounced execution to prevent excessive DOM processing
  let debounceTimeout = null;
  function triggerScan() {
    if (debounceTimeout) clearTimeout(debounceTimeout);
    debounceTimeout = setTimeout(() => {
      scanAndInject();
    }, 400);
  }

  // Initial runs
  triggerScan();
  setTimeout(triggerScan, 1000);
  setTimeout(triggerScan, 2500);

  // Safe MutationObserver with debouncing
  const observer = new MutationObserver((mutations) => {
    let relevant = false;
    for (const m of mutations) {
      if (m.target && m.target.id === "flh-top-banner") continue;
      if (m.target && m.target.classList && m.target.classList.contains("flh-push-btn")) continue;
      relevant = true;
      break;
    }
    if (relevant) {
      triggerScan();
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
})();
