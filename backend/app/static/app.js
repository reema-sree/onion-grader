/**
 * Kisan Setu - Main Application Controller (PWA)
 * Implements 14 responsive screens, Role Guards, Interactive Canvas, Web Speech API, 6-Stage Grading,
 * and complete Admin Dashboard & Governance (Users, Centres, Grading Rules Versioning, and Immutable Audit Log).
 */

import { api } from "./api.js";
import { t, getLang, setLang, applyTranslations } from "./i18n.js";
import { initDB, saveOfflineLot, getAllOfflineLots, updateLotSyncStatus, syncAllPendingLots } from "./db.js";
import { computeGrade, checkClientBlur, runOnDeviceInference, determineOnionBucket } from "./grading_engine.js";

// Global App State
const state = {
  currentRole: "staff", // "staff" | "farmer" | "admin"
  isAssistedMode: false,
  activeScreen: "screen-splash",
  activeAdminSubtab: "users",
  currentLot: null,
  capturedImages: [],
  currentDetections: [],
  currentGradeResult: null,
  selectedDetection: null,
  showAnnotationBoxes: true,
  mediaStream: null,
  speechSynth: window.speechSynthesis || null,
  auditLogCache: [],
};

// ── Toast Utility ────────────────────────────────────────────────────────────
export function showToast(message, duration = 3000) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `<span>💬</span><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ── Speech Synthesis (Read Aloud) ───────────────────────────────────────────
function speakText(text) {
  if (!state.speechSynth) {
    showToast(t("speech_not_supported"));
    return;
  }
  state.speechSynth.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  const lang = getLang();
  if (lang === "hi") utterance.lang = "hi-IN";
  else if (lang === "te") utterance.lang = "te-IN";
  else utterance.lang = "en-IN";
  utterance.rate = 0.95;
  state.speechSynth.speak(utterance);
}

// ── Screen Router & Role Guards ──────────────────────────────────────────────
export function navigateTo(screenId) {
  if (!api.isAuthenticated() && screenId !== "screen-splash" && screenId !== "screen-role-select") {
    screenId = "screen-role-select";
  }

  // Handle Admin Theme & Widescreen
  const header = document.getElementById("global-header");
  const isAdmin = api.getRole() === "admin";

  if (isAdmin) {
    document.body.classList.add("admin-mode");
    header?.classList.add("admin-theme");
  } else {
    document.body.classList.remove("admin-mode");
    header?.classList.remove("admin-theme");
  }

  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  const target = document.getElementById(screenId);
  if (target) {
    target.classList.add("active");
    state.activeScreen = screenId;
    window.scrollTo(0, 0);
  }

  // Manage bottom navigation visibility
  const nav = document.getElementById("bottom-navigation");
  const logoutBtn = document.getElementById("logout-btn");
  const adminTab = document.getElementById("nav-admin-tab");
  const farmerTab = document.getElementById("nav-farmer-tab");
  const staffTab = document.getElementById("nav-staff-tab");
  const noNavScreens = ["screen-splash", "screen-role-select", "screen-capture", "screen-analysis"];

  if (adminTab) adminTab.style.display = isAdmin ? "flex" : "none";
  if (farmerTab) farmerTab.style.display = api.getRole() === "farmer" ? "flex" : "none";
  if (staffTab) staffTab.style.display = api.getRole() === "farmer" ? "none" : "flex";

  if (nav) {
    if (noNavScreens.includes(screenId) || !api.isAuthenticated()) {
      nav.style.display = "none";
    } else {
      nav.style.display = "flex";
      document.querySelectorAll(".nav-item").forEach(item => {
        if (item.getAttribute("data-nav") === screenId) {
          item.classList.add("active");
        } else {
          item.classList.remove("active");
        }
      });
    }
  }

  if (logoutBtn) {
    logoutBtn.style.display = api.isAuthenticated() ? "flex" : "none";
  }

  // Route-specific triggers
  if (screenId === "screen-dashboard") loadDashboardData();
  if (screenId === "screen-admin-dashboard") loadAdminDashboardData();
  if (screenId === "screen-admin-management") switchAdminMgmtSubtab(state.activeAdminSubtab);
  if (screenId === "screen-farmer-batches") loadFarmerBatches();
  if (screenId === "screen-create-batch") initCreateBatchScreen();
  if (screenId === "screen-capture") initCameraView();
  else stopCameraStream();
}

// ── App Initialization ──────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  await initDB();
  applyTranslations();
  setupNetworkMonitor();
  setupGlobalEvents();

  if (api.isAuthenticated()) {
    const role = api.getRole();
    state.currentRole = role;
    if (role === "admin") {
      navigateTo("screen-admin-dashboard");
    } else if (role === "farmer") {
      navigateTo("screen-farmer-batches");
    } else {
      navigateTo("screen-dashboard");
    }
  } else {
    navigateTo("screen-splash");
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js").catch(e => console.warn("[PWA SW]", e));
  }
});

// ── Network & Offline Queue Monitor ──────────────────────────────────────────
function setupNetworkMonitor() {
  const banner = document.getElementById("offline-banner");
  function updateStatus() {
    if (navigator.onLine) {
      banner.classList.remove("active");
      triggerBackgroundSync();
    } else {
      banner.classList.add("active");
    }
  }
  window.addEventListener("online", updateStatus);
  window.addEventListener("offline", updateStatus);
  updateStatus();
}

async function triggerBackgroundSync() {
  try {
    const res = await syncAllPendingLots();
    if (res.synced > 0) {
      showToast(`Synced ${res.synced} offline batch(es) to cloud`);
    }
  } catch (err) {
    console.warn("[Sync]", err);
  }
}

// ── Global Event Listeners ──────────────────────────────────────────────────
function setupGlobalEvents() {
  // Language Switcher in Header
  document.getElementById("lang-toggle-btn")?.addEventListener("click", () => {
    const current = getLang();
    const next = current === "en" ? "hi" : current === "hi" ? "te" : "en";
    setLang(next);
    showToast(`Language: ${next.toUpperCase()}`);
  });

  // Splash language buttons
  document.querySelectorAll(".lang-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".lang-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      setLang(btn.getAttribute("data-lang"));
    });
  });

  // Splash Get Started
  document.getElementById("splash-get-started-btn")?.addEventListener("click", () => {
    navigateTo("screen-role-select");
  });

  // Role Selection Cards
  document.querySelectorAll(".role-card").forEach(card => {
    card.addEventListener("click", () => {
      document.querySelectorAll(".role-card").forEach(c => c.classList.remove("selected"));
      card.classList.add("selected");
      const role = card.getAttribute("data-role");
      state.currentRole = role;

      const emailForm = document.getElementById("login-form-email");
      const phoneForm = document.getElementById("login-form-phone");
      const assistedWrapper = document.getElementById("assisted-mode-wrapper");

      if (role === "farmer") {
        emailForm.style.display = "none";
        phoneForm.style.display = "block";
      } else {
        emailForm.style.display = "block";
        phoneForm.style.display = "none";
        if (assistedWrapper) {
          assistedWrapper.style.display = role === "staff" ? "flex" : "none";
        }
      }
    });
  });

  // Assisted Mode Toggle
  document.getElementById("assisted-mode-toggle")?.addEventListener("change", (e) => {
    state.isAssistedMode = e.target.checked;
    if (state.isAssistedMode) {
      document.body.classList.add("assisted-mode");
      speakText(t("assisted_mode_hint"));
      showToast(t("assisted_mode_hint"));
    } else {
      document.body.classList.remove("assisted-mode");
    }
  });

  // Email/Password Login
  document.getElementById("email-login-btn")?.addEventListener("click", handleEmailLogin);
  document.getElementById("farmer-otp-btn")?.addEventListener("click", handleFarmerOtpLogin);

  // Logout Button
  document.getElementById("logout-btn")?.addEventListener("click", () => {
    api.clearSession();
    state.currentLot = null;
    document.body.classList.remove("admin-mode");
    showToast(t("logout"));
    navigateTo("screen-role-select");
  });

  // Back Buttons
  document.querySelectorAll(".back-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-target");
      if (target) navigateTo(target);
    });
  });

  // Bottom Navigation Click
  document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", () => {
      const target = item.getAttribute("data-nav");
      if (target) navigateTo(target);
    });
  });

  // Dashboard Actions
  document.getElementById("dash-new-batch-quick-btn")?.addEventListener("click", () => {
    navigateTo("screen-create-batch");
  });
  document.getElementById("dash-refresh-btn")?.addEventListener("click", loadDashboardData);

  // Admin Dashboard Period Selector
  document.getElementById("admin-period-select")?.addEventListener("change", (e) => {
    loadAdminDashboardData(e.target.value);
  });

  // Admin Navigation Grid Cards
  document.querySelectorAll("[data-admin-tab]").forEach(card => {
    card.addEventListener("click", () => {
      const subtab = card.getAttribute("data-admin-tab");
      state.activeAdminSubtab = subtab;
      navigateTo("screen-admin-management");
    });
  });

  // Admin Management Sub-Tabs
  document.querySelectorAll("[data-mgmt-tab]").forEach(btn => {
    btn.addEventListener("click", () => {
      const subtab = btn.getAttribute("data-mgmt-tab");
      switchAdminMgmtSubtab(subtab);
    });
  });

  // Admin Users Search & Role Filter
  document.getElementById("admin-search-users")?.addEventListener("input", loadAdminUsers);
  document.getElementById("admin-filter-role")?.addEventListener("change", loadAdminUsers);
  document.getElementById("admin-add-user-btn")?.addEventListener("click", openCreateUserModal);
  document.getElementById("cancel-create-user-btn")?.addEventListener("click", () => {
    document.getElementById("create-user-modal").classList.remove("active");
  });
  document.getElementById("save-create-user-btn")?.addEventListener("click", handleSaveCreateUser);

  // Admin Centres Actions
  document.getElementById("admin-add-centre-btn")?.addEventListener("click", () => {
    document.getElementById("create-centre-modal").classList.add("active");
  });
  document.getElementById("cancel-create-centre-btn")?.addEventListener("click", () => {
    document.getElementById("create-centre-modal").classList.remove("active");
  });
  document.getElementById("save-create-centre-btn")?.addEventListener("click", handleSaveCreateCentre);

  // Admin Grading Rules Actions
  document.getElementById("rules-publish-btn")?.addEventListener("click", handlePublishGradingRules);

  // Audit Log Controls
  document.getElementById("audit-filter-batch")?.addEventListener("input", loadAdminAuditLogs);
  document.getElementById("audit-filter-action")?.addEventListener("change", loadAdminAuditLogs);
  document.getElementById("admin-audit-export-btn")?.addEventListener("click", handleExportAuditCsv);
  document.getElementById("close-audit-diff-btn")?.addEventListener("click", () => {
    document.getElementById("audit-diff-modal").classList.remove("active");
  });
  document.getElementById("dismiss-diff-btn")?.addEventListener("click", () => {
    document.getElementById("audit-diff-modal").classList.remove("active");
  });

  // Dashboard Stat Tiles Filter
  document.querySelectorAll(".stat-tile").forEach(tile => {
    tile.addEventListener("click", () => {
      document.querySelectorAll(".stat-tile").forEach(t => t.classList.remove("active"));
      tile.classList.add("active");
      const filter = tile.getAttribute("data-filter");
      filterDashboardBatches(filter);
    });
  });

  // Create Batch Form
  document.getElementById("create-batch-submit-btn")?.addEventListener("click", handleCreateBatchSubmit);
  document.getElementById("quick-add-farmer-btn")?.addEventListener("click", () => {
    document.getElementById("quick-add-farmer-modal").classList.add("active");
  });
  document.getElementById("cancel-quick-farmer-btn")?.addEventListener("click", () => {
    document.getElementById("quick-add-farmer-modal").classList.remove("active");
  });
  document.getElementById("save-quick-farmer-btn")?.addEventListener("click", handleSaveQuickFarmer);

  // Camera Controls
  document.getElementById("camera-shutter-btn")?.addEventListener("click", handleShutterCapture);
  document.getElementById("camera-file-input")?.addEventListener("change", handleGalleryFileInput);
  document.getElementById("start-analysis-btn")?.addEventListener("click", handleStartAnalysis);

  // Analysis Controls
  document.getElementById("analysis-cancel-btn")?.addEventListener("click", () => {
    navigateTo("screen-capture");
  });
  document.getElementById("analysis-retake-btn")?.addEventListener("click", () => {
    navigateTo("screen-capture");
  });

  // Results Controls
  document.getElementById("results-review-btn")?.addEventListener("click", () => {
    navigateTo("screen-verify");
  });
  document.getElementById("results-gen-report-btn")?.addEventListener("click", () => {
    if (state.currentLot && state.currentLot.status !== "approved" && state.currentLot.status !== "overridden") {
      showToast(t("verify_first_hint"));
      setTimeout(() => navigateTo("screen-verify"), 1000);
    } else {
      handleGenerateReport();
    }
  });

  // Bottom Sheet Close
  document.getElementById("close-bottom-sheet-btn")?.addEventListener("click", () => {
    document.getElementById("onion-bottom-sheet-backdrop").classList.remove("active");
  });
  document.getElementById("sheet-save-relabel-btn")?.addEventListener("click", handleSaveOnionRelabel);

  // Verification Controls
  document.getElementById("verify-approve-btn")?.addEventListener("click", handleApproveLot);
  document.getElementById("verify-override-toggle-btn")?.addEventListener("click", () => {
    const card = document.getElementById("override-form-card");
    card.style.display = card.style.display === "none" ? "block" : "none";
  });
  document.getElementById("override-reason-textarea")?.addEventListener("input", handleOverrideReasonInput);
  document.getElementById("submit-override-btn")?.addEventListener("click", handleSubmitOverride);

  // Digital Report Controls
  document.getElementById("download-pdf-btn")?.addEventListener("click", handleDownloadPdf);
  document.getElementById("share-report-btn")?.addEventListener("click", handleShareReport);

  // Farmer Batches Filter Chips
  document.querySelectorAll("[data-farmer-filter]").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("[data-farmer-filter]").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      filterFarmerBatches(chip.getAttribute("data-farmer-filter"));
    });
  });

  // Farmer Detail Controls
  document.getElementById("farmer-speak-btn")?.addEventListener("click", handleFarmerReadAloud);
  document.getElementById("farmer-toggle-boxes-btn")?.addEventListener("click", handleFarmerToggleBoxes);
  document.getElementById("farmer-download-pdf-btn")?.addEventListener("click", handleDownloadPdf);
}

// ── Auth Handlers ───────────────────────────────────────────────────────────
async function handleEmailLogin() {
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value.trim();
  const btn = document.getElementById("email-login-btn");

  if (!email || !password) {
    showToast("Please enter email and password");
    return;
  }

  try {
    btn.disabled = true;
    btn.textContent = t("loading");
    const data = await api.loginEmail(email, password);
    showToast(`${t("welcome_back")}!`);
    if (data.user.role === "admin") {
      navigateTo("screen-admin-dashboard");
    } else {
      navigateTo("screen-dashboard");
    }
  } catch (err) {
    showToast(`Login failed: ${err.message || err.detail}`);
  } finally {
    btn.disabled = false;
    btn.textContent = t("login_btn");
  }
}

async function handleFarmerOtpLogin() {
  const phone = document.getElementById("farmer-phone-input").value.trim();
  const otpGroup = document.getElementById("otp-input-group");
  const otpInput = document.getElementById("farmer-otp-input");
  const btn = document.getElementById("farmer-otp-btn");

  if (!phone) {
    showToast("Please enter phone number");
    return;
  }

  if (otpGroup.style.display === "none") {
    try {
      btn.disabled = true;
      btn.textContent = t("loading");
      await api.requestPhoneOtp(phone);
      otpGroup.style.display = "block";
      btn.textContent = t("verify_login");
      showToast("OTP sent: 123456");
    } catch (err) {
      showToast(`OTP request failed: ${err.message}`);
      btn.textContent = t("get_otp");
    } finally {
      btn.disabled = false;
    }
    return;
  }

  const otp = otpInput.value.trim();
  if (!otp) {
    showToast("Please enter the 6-digit OTP");
    return;
  }

  try {
    btn.disabled = true;
    btn.textContent = t("loading");
    await api.verifyPhoneOtp(phone, otp);
    showToast("Logged in as Farmer");
    navigateTo("screen-farmer-batches");
  } catch (err) {
    showToast(`OTP verification failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = t("verify_login");
  }
}

// ── Screen 13: Admin Dashboard ──────────────────────────────────────────────
async function loadAdminDashboardData(period = "30d") {
  try {
    const summary = await api.getAdminSummary(period);
    document.getElementById("kpi-total-batches").textContent = summary.total_batches || 0;
    document.getElementById("kpi-total-centres").textContent = summary.total_centres || 0;
    document.getElementById("kpi-avg-grade-a").textContent = `${(summary.avg_grade_a_pct || 0).toFixed(1)}%`;
    document.getElementById("kpi-override-rate").textContent = `${(summary.override_rate || 0).toFixed(1)}%`;

    renderCentrePerformanceChart(summary.per_centre_grade_a || []);
  } catch (err) {
    console.warn("[Admin Summary Error]", err);
  }
}

function renderCentrePerformanceChart(centres) {
  const container = document.getElementById("centre-chart-container");
  if (!container) return;

  if (!centres || centres.length === 0) {
    container.innerHTML = `<p style="font-size:0.85rem; color:var(--color-text-muted);">No centre performance data available.</p>`;
    return;
  }

  container.innerHTML = centres.map(c => {
    const isHighOverride = c.override_rate > 15.0;
    const barColor = isHighOverride ? "warning" : "";
    return `
      <div class="chart-bar-row">
        <div class="chart-bar-header">
          <span>${c.centre_code}: ${c.centre_name}</span>
          <span>
            ${c.avg_grade_a_pct.toFixed(1)}% Grade A
            ${isHighOverride ? `<span class="demo-badge" style="background:#FEE2E2; color:#9B2C2C; margin-left:4px;">⚠ ${c.override_rate.toFixed(1)}% overrides</span>` : ""}
          </span>
        </div>
        <div class="chart-bar-track">
          <div class="chart-bar-fill ${barColor}" style="width: ${Math.min(100, Math.max(5, c.avg_grade_a_pct))}%;"></div>
        </div>
      </div>
    `;
  }).join("");
}

// ── Screen 14: Admin Management Subtabs ──────────────────────────────────────
function switchAdminMgmtSubtab(subtab) {
  state.activeAdminSubtab = subtab;

  document.querySelectorAll("[data-mgmt-tab]").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-mgmt-tab") === subtab);
  });

  const titles = {
    users: t("manage_users_title"),
    centres: t("manage_centres_title"),
    rules: t("manage_rules_title"),
    audit: t("audit_log_title"),
  };
  document.getElementById("admin-mgmt-title").textContent = titles[subtab] || t("manage_users_title");

  document.getElementById("admin-subtab-users").style.display = subtab === "users" ? "block" : "none";
  document.getElementById("admin-subtab-centres").style.display = subtab === "centres" ? "block" : "none";
  document.getElementById("admin-subtab-rules").style.display = subtab === "rules" ? "block" : "none";
  document.getElementById("admin-subtab-audit").style.display = subtab === "audit" ? "block" : "none";

  if (subtab === "users") loadAdminUsers();
  if (subtab === "centres") loadAdminCentres();
  if (subtab === "rules") loadAdminGradingRules();
  if (subtab === "audit") loadAdminAuditLogs();
}

// ── Admin Subtab 1: Users ───────────────────────────────────────────────────
async function loadAdminUsers() {
  const tbody = document.getElementById("admin-users-tbody");
  if (!tbody) return;

  const search = document.getElementById("admin-search-users")?.value.trim();
  const role = document.getElementById("admin-filter-role")?.value;

  try {
    const users = await api.getUsers({ search, role });
    tbody.innerHTML = users.map(u => `
      <tr>
        <td>
          <strong>${u.name}</strong><br>
          <span style="font-size:0.75rem; color:var(--color-text-muted);">${u.email || u.phone || "No contact"}</span>
        </td>
        <td><span class="demo-badge" style="background:#E0F2F6; color:#093742;">${u.role.toUpperCase()}</span></td>
        <td>${u.centre_id ? `Centre #${u.centre_id}` : "Global"}</td>
        <td>
          <span style="color:${u.is_active ? '#10B981' : '#EF4444'}; font-weight:700;">
            ${u.is_active ? t("user_status_active") : t("user_status_inactive")}
          </span>
        </td>
        <td>
          <button class="btn btn-sm btn-outline user-toggle-btn" data-user-id="${u.id}">
            ${u.is_active ? "Deactivate" : "Activate"}
          </button>
        </td>
      </tr>
    `).join("");

    tbody.querySelectorAll(".user-toggle-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = parseInt(btn.getAttribute("data-user-id"));
        try {
          await api.toggleUserActive(id);
          showToast("User status updated");
          loadAdminUsers();
        } catch (err) {
          showToast(`Toggle failed: ${err.message}`);
        }
      });
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" style="color:red;">Error loading users: ${err.message}</td></tr>`;
  }
}

async function openCreateUserModal() {
  const modal = document.getElementById("create-user-modal");
  const centreSelect = document.getElementById("modal-user-centre");
  centreSelect.innerHTML = `<option value="">Global / No Centre</option>`;
  try {
    const centres = await api.getCentres();
    centres.forEach(c => {
      centreSelect.innerHTML += `<option value="${c.id}">${c.name} (${c.code})</option>`;
    });
  } catch (_) {}
  modal.classList.add("active");
}

async function handleSaveCreateUser() {
  const name = document.getElementById("modal-user-name").value.trim();
  const role = document.getElementById("modal-user-role").value;
  const centreId = document.getElementById("modal-user-centre").value;
  const email = document.getElementById("modal-user-email").value.trim();
  const phone = document.getElementById("modal-user-phone").value.trim();

  if (!name) {
    showToast("User name is required");
    return;
  }

  try {
    await api.createUser({
      name,
      role,
      centre_id: centreId ? parseInt(centreId) : null,
      email: email || null,
      phone: phone || null,
      password: "DemoPass123!",
    });
    showToast(`User ${name} created successfully!`);
    document.getElementById("create-user-modal").classList.remove("active");
    loadAdminUsers();
  } catch (err) {
    showToast(`User creation failed: ${err.message}`);
  }
}

// ── Admin Subtab 2: Centres ─────────────────────────────────────────────────
async function loadAdminCentres() {
  const tbody = document.getElementById("admin-centres-tbody");
  if (!tbody) return;

  try {
    const centres = await api.getCentres();
    tbody.innerHTML = centres.map(c => `
      <tr>
        <td><strong>${c.code}</strong></td>
        <td>${c.name}</td>
        <td>${c.district || ""}, ${c.state || ""}</td>
        <td>
          <span style="color:${c.is_active ? '#10B981' : '#EF4444'}; font-weight:700;">
            ${c.is_active ? "Active" : "Inactive"}
          </span>
        </td>
        <td>
          <button class="btn btn-sm btn-outline centre-toggle-btn" data-centre-id="${c.id}" data-active="${c.is_active}">
            ${c.is_active ? "Deactivate" : "Activate"}
          </button>
        </td>
      </tr>
    `).join("");

    tbody.querySelectorAll(".centre-toggle-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = parseInt(btn.getAttribute("data-centre-id"));
        const curr = btn.getAttribute("data-active") === "true";
        try {
          await api.updateCentre(id, { is_active: !curr });
          showToast("Centre status updated");
          loadAdminCentres();
        } catch (err) {
          showToast(`Centre update failed: ${err.message}`);
        }
      });
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" style="color:red;">Error loading centres: ${err.message}</td></tr>`;
  }
}

async function handleSaveCreateCentre() {
  const code = document.getElementById("modal-centre-code").value.trim();
  const name = document.getElementById("modal-centre-name").value.trim();
  const district = document.getElementById("modal-centre-district").value.trim();
  const stateVal = document.getElementById("modal-centre-state").value.trim();

  if (!code || !name) {
    showToast("Centre Code and Name are required");
    return;
  }

  try {
    await api.createCentre({
      code,
      name,
      district: district || null,
      state: stateVal || null,
      is_active: true,
    });
    showToast(`Centre ${name} (${code}) created!`);
    document.getElementById("create-centre-modal").classList.remove("active");
    loadAdminCentres();
  } catch (err) {
    showToast(`Centre creation failed: ${err.message}`);
  }
}

// ── Admin Subtab 3: Grading Rules Governance ────────────────────────────────
async function loadAdminGradingRules() {
  try {
    const rules = await api.getGradingRules();
    document.getElementById("rules-current-version-tag").textContent = `Version ${rules.version || "v2.0"}`;
    document.getElementById("rules-min-size-input").value = rules.min_size_cm || 6.0;

    let gAThresh = 70;
    let defThresh = 30;
    if (rules.lot_grade_rules) {
      rules.lot_grade_rules.forEach(r => {
        if (r.grade === "Grade A" && r.threshold) gAThresh = r.threshold;
        if (r.grade === "Defective" && r.threshold) defThresh = r.threshold;
      });
    }
    document.getElementById("rules-grade-a-thresh").value = gAThresh;
    document.getElementById("rules-defective-thresh").value = defThresh;

    const versionNum = parseFloat((rules.version || "v2.0").replace("v", "")) || 2.0;
    document.getElementById("rules-new-version-input").value = `v${(versionNum + 0.1).toFixed(1)}`;
  } catch (err) {
    showToast(`Error loading grading rules: ${err.message}`);
  }
}

async function handlePublishGradingRules() {
  const minSize = parseFloat(document.getElementById("rules-min-size-input").value);
  const gradeAThresh = parseFloat(document.getElementById("rules-grade-a-thresh").value);
  const defThresh = parseFloat(document.getElementById("rules-defective-thresh").value);
  const newVersion = document.getElementById("rules-new-version-input").value.trim();
  const note = document.getElementById("rules-change-note").value.trim();

  if (!note || note.length < 5) {
    showToast("Please enter a version change note (min 5 characters)");
    return;
  }

  try {
    const updated = await api.updateGradingRules({
      min_size_cm: minSize,
      grade_a_threshold: gradeAThresh,
      defective_threshold: defThresh,
      version: newVersion,
      change_note: note,
    });
    showToast(`Published Rule Version ${updated.version}!`);
    document.getElementById("rules-change-note").value = "";
    loadAdminGradingRules();
  } catch (err) {
    showToast(`Rule update failed: ${err.message}`);
  }
}

// ── Admin Subtab 4: Audit Logs (Strictly Read-Only) ─────────────────────────
async function loadAdminAuditLogs() {
  const container = document.getElementById("audit-log-list-container");
  if (!container) return;

  const batchCode = document.getElementById("audit-filter-batch")?.value.trim();
  const action = document.getElementById("audit-filter-action")?.value;

  try {
    const logs = await api.getAuditLogs({ batch_code: batchCode, action: action, limit: 100 });
    state.auditLogCache = logs || [];

    if (!logs || logs.length === 0) {
      container.innerHTML = `<p style="font-size:0.85rem; color:var(--color-text-muted);">No audit log entries found matching criteria.</p>`;
      return;
    }

    container.innerHTML = logs.map(l => {
      const actorName = l.actor_name || `User #${l.actor_id || "Sys"}`;
      const initial = actorName.charAt(0).toUpperCase();
      const timeStr = new Date(l.created_at).toLocaleDateString("en-IN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

      return `
        <div class="audit-row" data-audit-id="${l.id}">
          <div class="audit-actor-avatar">${initial}</div>
          <div class="audit-info">
            <div style="display:flex; justify-content:space-between;">
              <span class="audit-action-title">${l.action}</span>
              <span class="audit-time">${timeStr}</span>
            </div>
            <div class="audit-reason">${l.reason || `Action on ${l.entity_type} #${l.entity_id}`}</div>
            <div style="margin-top:4px;">
              <span class="demo-badge" style="background:#E0F2F6; color:#093742;">Actor: ${actorName}</span>
              <button class="btn btn-sm btn-outline view-diff-btn" data-audit-id="${l.id}" style="min-height:22px; padding:1px 6px; font-size:0.7rem; margin-left:6px;" data-i18n="view_diff">
                View Diff JSON
              </button>
            </div>
          </div>
        </div>
      `;
    }).join("");

    container.querySelectorAll(".view-diff-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const id = parseInt(btn.getAttribute("data-audit-id"));
        openAuditDiffModal(id);
      });
    });
  } catch (err) {
    container.innerHTML = `<p style="color:red;">Error loading audit trail: ${err.message}</p>`;
  }
}

function openAuditDiffModal(auditId) {
  const log = state.auditLogCache.find(l => l.id === auditId);
  if (!log) return;

  document.getElementById("diff-action-tag").textContent = log.action;
  document.getElementById("diff-entity-tag").textContent = `${log.entity_type} #${log.entity_id}`;
  document.getElementById("diff-before-json").textContent = log.before ? JSON.stringify(log.before, null, 2) : "null (Created)";
  document.getElementById("diff-after-json").textContent = log.after ? JSON.stringify(log.after, null, 2) : "null";
  document.getElementById("diff-reason-text").textContent = `Reason: ${log.reason || "N/A"}`;

  document.getElementById("audit-diff-modal").classList.add("active");
}

function handleExportAuditCsv() {
  const batchCode = document.getElementById("audit-filter-batch")?.value.trim();
  const action = document.getElementById("audit-filter-action")?.value;
  const url = api.getAuditLogExportUrl({ batch_code: batchCode, action: action });
  window.open(url, "_blank");
}

// ── Staff Dashboard Helpers ─────────────────────────────────────────────────
let dashboardBatchesCache = [];

async function loadDashboardData() {
  const nameEl = document.getElementById("dash-user-name");
  const centreEl = document.getElementById("dash-centre-name");
  if (api.user) {
    nameEl.textContent = api.user.name || "Procurement Staff";
    centreEl.textContent = api.user.centre_id ? `📍 Centre #${api.user.centre_id}` : "📍 Main Procurement Centre";
  }

  try {
    const summary = await api.getDashboardSummary();
    document.getElementById("stat-scanned-count").textContent = summary.scanned_today || 0;
    document.getElementById("stat-approved-count").textContent = summary.approved_today || 0;
    document.getElementById("stat-pending-count").textContent = summary.pending_review || 0;

    const lotsResp = await api.listLots({ size: 20 });
    dashboardBatchesCache = lotsResp.items || [];
    renderDashboardBatches(dashboardBatchesCache);
  } catch (err) {
    console.warn("[Dashboard Error]", err);
    const offlineLots = await getAllOfflineLots();
    dashboardBatchesCache = offlineLots;
    renderDashboardBatches(offlineLots);
  }
}

function filterDashboardBatches(filterStatus) {
  if (!filterStatus || filterStatus === "all") {
    renderDashboardBatches(dashboardBatchesCache);
  } else {
    const filtered = dashboardBatchesCache.filter(b => b.status === filterStatus);
    renderDashboardBatches(filtered);
  }
}

function renderDashboardBatches(batches) {
  const container = document.getElementById("dashboard-batches-list");
  if (!container) return;

  if (!batches || batches.length === 0) {
    container.innerHTML = `<div class="card" style="text-align:center; padding:24px; color:var(--color-text-muted);">${t("no_batches")}</div>`;
    return;
  }

  container.innerHTML = batches.map(b => {
    const lotGradeLabel = (b.grade_result && b.grade_result.lot_grade_label) || (b.ai_result && b.ai_result.lot_grade_label) || b.status.toUpperCase();
    const gradeClass = lotGradeLabel.includes("Grade A") ? "grade-a" : lotGradeLabel.includes("Defective") ? "defective" : "urs";
    const dateStr = b.created_at ? new Date(b.created_at).toLocaleDateString("en-IN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "";

    return `
      <div class="batch-item" data-lot-id="${b.id || b.client_lot_id}">
        <div class="batch-thumb">🧅</div>
        <div class="batch-details">
          <div class="batch-code">${b.batch_code || b.lot_number || `KS-LOT-${b.id}`}</div>
          <div class="batch-meta">${b.farmer_name || "Farmer"} · ${dateStr}</div>
          <span class="lot-grade-chip ${gradeClass}">${lotGradeLabel}</span>
        </div>
        <span style="color:var(--color-forest); font-weight:700;">→</span>
      </div>
    `;
  }).join("");

  container.querySelectorAll(".batch-item").forEach(item => {
    item.addEventListener("click", async () => {
      const lotId = item.getAttribute("data-lot-id");
      try {
        const lot = await api.getLot(lotId);
        state.currentLot = lot;
        if (lot.grade_result || lot.ai_result) {
          state.currentGradeResult = lot.grade_result || lot.ai_result;
          state.currentDetections = lot.detections || [];
          displayInspectionResults(lot);
          navigateTo("screen-results");
        } else {
          navigateTo("screen-capture");
        }
      } catch (err) {
        showToast("Loading batch details...");
      }
    });
  });
}

// ── Screen 4: Create Batch ──────────────────────────────────────────────────
async function initCreateBatchScreen() {
  const dateInput = document.getElementById("create-date-input");
  if (dateInput) {
    dateInput.value = new Date().toISOString().split("T")[0];
  }

  const farmerSelect = document.getElementById("create-farmer-select");
  farmerSelect.innerHTML = `<option value="">Select Farmer...</option>`;
  try {
    const users = await api.getUsers("farmer");
    users.forEach(u => {
      farmerSelect.innerHTML += `<option value="${u.id}">${u.name} (${u.phone || "No phone"})</option>`;
    });
  } catch (_) {
    farmerSelect.innerHTML += `<option value="1">Ramesh Patil (+919876543210)</option>`;
  }

  const centreSelect = document.getElementById("create-centre-select");
  centreSelect.innerHTML = "";
  try {
    const centres = await api.getCentres();
    centres.forEach(c => {
      centreSelect.innerHTML += `<option value="${c.id}">${c.name} (${c.code || "C01"})</option>`;
    });
  } catch (_) {
    centreSelect.innerHTML = `<option value="1">Nashik APMC Centre (C01)</option>`;
  }
}

async function handleSaveQuickFarmer() {
  const name = document.getElementById("quick-farmer-name").value.trim();
  const phone = document.getElementById("quick-farmer-phone").value.trim();
  if (!name) {
    showToast("Farmer name is required");
    return;
  }
  const farmerSelect = document.getElementById("create-farmer-select");
  const tempId = Date.now();
  farmerSelect.innerHTML += `<option value="${tempId}" selected>${name} (${phone || "Quick Add"})</option>`;
  document.getElementById("quick-add-farmer-modal").classList.remove("active");
  showToast(`Farmer ${name} added!`);
}

async function handleCreateBatchSubmit() {
  const farmerSelect = document.getElementById("create-farmer-select");
  const centreSelect = document.getElementById("create-centre-select");
  const weightInput = document.getElementById("create-weight-input");
  const dateInput = document.getElementById("create-date-input");
  const submitBtn = document.getElementById("create-batch-submit-btn");

  const farmerId = farmerSelect.value ? parseInt(farmerSelect.value) : null;
  const farmerName = farmerSelect.options[farmerSelect.selectedIndex]?.text.split("(")[0].trim() || "Farmer";
  const centreId = centreSelect.value ? parseInt(centreSelect.value) : 1;
  const weightKg = weightInput.value ? parseFloat(weightInput.value) : null;
  const batchDate = dateInput.value ? new Date(dateInput.value).toISOString() : new Date().toISOString();

  try {
    submitBtn.disabled = true;
    submitBtn.textContent = t("loading");

    const newLot = await api.createLot({
      farmer_id: isNaN(farmerId) ? null : farmerId,
      farmer_name: farmerName,
      centre_id: centreId,
      weight_kg: weightKg,
      batch_date: batchDate,
      crop: "onion",
    });

    state.currentLot = newLot;
    state.capturedImages = [];
    document.getElementById("capture-batch-code-title").textContent = newLot.batch_code || `KS-LOT-${newLot.id}`;
    updateCapturedThumbnailsUI();
    navigateTo("screen-capture");
  } catch (err) {
    showToast(`Batch creation failed: ${err.message}`);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = t("continue_to_camera");
  }
}

// ── Screen 5: Camera & Capture ──────────────────────────────────────────────
async function initCameraView() {
  const video = document.getElementById("camera-video");
  const indicator = document.getElementById("live-marker-indicator");
  const indicatorText = document.getElementById("marker-indicator-text");

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 960 } }
    });
    state.mediaStream = stream;
    video.srcObject = stream;
    video.style.display = "block";

    setTimeout(() => {
      indicator.className = "marker-indicator detected";
      indicatorText.textContent = t("marker_detected");
    }, 1200);
  } catch (err) {
    console.warn("[Camera denied / unavailable]", err);
    video.style.display = "none";
    indicator.className = "marker-indicator missing";
    indicatorText.textContent = "Camera unavailable — Use Gallery upload";
  }
}

function stopCameraStream() {
  if (state.mediaStream) {
    state.mediaStream.getTracks().forEach(track => track.stop());
    state.mediaStream = null;
  }
}

function handleShutterCapture() {
  if (state.capturedImages.length >= 3) {
    showToast(t("max_photos_hint"));
    return;
  }

  const video = document.getElementById("camera-video");
  const canvas = document.getElementById("camera-canvas");
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;

  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  const blurCheck = checkClientBlur(canvas);
  if (blurCheck.isBlurry) {
    showToast(t("blur_warning"), 4000);
  }

  canvas.toBlob((blob) => {
    const file = new File([blob], `capture_${Date.now()}.jpg`, { type: "image/jpeg" });
    const dataUrl = canvas.toDataURL("image/jpeg");
    state.capturedImages.push({ file, dataUrl, isBlurry: blurCheck.isBlurry });
    updateCapturedThumbnailsUI();
    showToast(`Photo ${state.capturedImages.length}/3 captured`);
  }, "image/jpeg", 0.9);
}

function handleGalleryFileInput(e) {
  const files = Array.from(e.target.files);
  if (!files || files.length === 0) return;

  files.forEach(file => {
    if (state.capturedImages.length >= 3) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      state.capturedImages.push({ file, dataUrl: event.target.result, isBlurry: false });
      updateCapturedThumbnailsUI();
    };
    reader.readAsDataURL(file);
  });
}

function updateCapturedThumbnailsUI() {
  const counter = document.getElementById("capture-photo-counter");
  const startBtn = document.getElementById("start-analysis-btn");
  const count = state.capturedImages.length;

  counter.textContent = `${count} / 3`;
  startBtn.disabled = count === 0;

  for (let i = 1; i <= 3; i++) {
    const slot = document.getElementById(`thumb-slot-${i}`);
    if (state.capturedImages[i - 1]) {
      const imgObj = state.capturedImages[i - 1];
      slot.innerHTML = `
        <img src="${imgObj.dataUrl}" alt="Photo ${i}">
        <button class="thumb-delete" data-idx="${i - 1}">✕</button>
      `;
      slot.querySelector(".thumb-delete").addEventListener("click", (e) => {
        e.stopPropagation();
        state.capturedImages.splice(i - 1, 1);
        updateCapturedThumbnailsUI();
      });
    } else {
      slot.innerHTML = `<span>📷 ${i}</span>`;
    }
  }
}

// ── Screen 6: AI 6-Stage Analysis ───────────────────────────────────────────
async function handleStartAnalysis() {
  if (!state.currentLot) {
    showToast("No active batch selected");
    return;
  }
  if (state.capturedImages.length === 0) {
    showToast("Please take or upload at least 1 image");
    return;
  }

  navigateTo("screen-analysis");
  resetAnalysisChecklistUI();

  const lotId = state.currentLot.id;

  try {
    const files = state.capturedImages.map(img => img.file);
    await api.uploadLotImages(lotId, files);
    await api.startGrading(lotId);
    pollGradingPipeline(lotId);
  } catch (err) {
    console.warn("[Server Grading Failed, fallback to on-device]", err);
    runLocalOnDeviceGrading();
  }
}

function resetAnalysisChecklistUI() {
  const percentEl = document.getElementById("analysis-percent");
  const errorCard = document.getElementById("analysis-error-card");
  percentEl.textContent = "0%";
  errorCard.style.display = "none";

  const stages = [
    "image_quality_check",
    "marker_detection",
    "onion_detection",
    "size_measurement",
    "defect_detection",
    "grading"
  ];
  stages.forEach(name => {
    const item = document.getElementById(`stage-${name}`);
    if (item) {
      item.className = "stage-item pending";
      document.getElementById(`stage-desc-${name}`).textContent = "Pending...";
    }
  });
}

async function pollGradingPipeline(lotId) {
  const interval = setInterval(async () => {
    try {
      const statusData = await api.getGradeStatus(lotId);
      updatePipelineStagesUI(statusData.stages, statusData.overall_percent);

      if (statusData.failed_stage) {
        clearInterval(interval);
        showPipelineError(statusData.failed_stage, statusData.retake_message);
        return;
      }

      if (statusData.is_complete) {
        clearInterval(interval);
        const updatedLot = await api.getLot(lotId);
        state.currentLot = updatedLot;
        state.currentGradeResult = updatedLot.grade_result || updatedLot.ai_result;
        state.currentDetections = updatedLot.detections || [];
        displayInspectionResults(updatedLot);
        setTimeout(() => navigateTo("screen-results"), 400);
      }
    } catch (err) {
      clearInterval(interval);
      console.error("[Polling error]", err);
    }
  }, 350);
}

function updatePipelineStagesUI(stages, overallPercent) {
  document.getElementById("analysis-percent").textContent = `${overallPercent}%`;
  if (!stages) return;

  stages.forEach(s => {
    const item = document.getElementById(`stage-${s.name}`);
    const desc = document.getElementById(`stage-desc-${s.name}`);
    if (item && desc) {
      item.className = `stage-item ${s.status}`;
      desc.textContent = s.message || s.status.toUpperCase();
    }
  });
}

function showPipelineError(failedStage, retakeMessage) {
  const errorCard = document.getElementById("analysis-error-card");
  const guidanceEl = document.getElementById("analysis-error-guidance");
  errorCard.style.display = "block";
  guidanceEl.textContent = retakeMessage || "Quality check failed. Please retake the photo.";
  speakText(retakeMessage);
}

async function runLocalOnDeviceGrading() {
  const canvas = document.createElement("canvas");
  const img = new Image();
  img.src = state.capturedImages[0].dataUrl;
  await new Promise(r => { img.onload = r; });
  canvas.width = img.width;
  canvas.height = img.height;
  canvas.getContext("2d").drawImage(img, 0, 0);

  const localResult = await runOnDeviceInference(canvas, (progress) => {
    document.getElementById("analysis-percent").textContent = `${progress.percent}%`;
    const item = document.getElementById(`stage-${progress.currentStage}`);
    const desc = document.getElementById(`stage-desc-${progress.currentStage}`);
    if (item && desc) {
      item.className = "stage-item running";
      desc.textContent = progress.message;
    }
  });

  state.currentDetections = localResult.detections;
  state.currentGradeResult = localResult.grade_result;
  displayInspectionResults({
    ...state.currentLot,
    grade_result: localResult.grade_result,
    detections: localResult.detections,
  });

  setTimeout(() => navigateTo("screen-results"), 500);
}

// ── Screen 7: AI Results & Interactive Canvas ───────────────────────────────
function displayInspectionResults(lot) {
  const gr = state.currentGradeResult || {};
  const total = gr.total_onions || state.currentDetections.length;
  const gradeAPct = gr.grade_a_pct !== undefined ? gr.grade_a_pct : 0;
  const ursPct = gr.urs_pct !== undefined ? gr.urs_pct : 0;
  const defectivePct = gr.defective_pct !== undefined ? gr.defective_pct : 0;
  const lotGradeLabel = gr.lot_grade_label || "Grade A";

  document.getElementById("res-total-onions").textContent = total;
  document.getElementById("res-grade-a-pct").textContent = `${gradeAPct.toFixed(1)}%`;
  document.getElementById("res-grade-a-count").textContent = `${gr.grade_a_count || 0} onions`;
  document.getElementById("res-urs-pct").textContent = `${ursPct.toFixed(1)}%`;
  document.getElementById("res-urs-count").textContent = `${gr.urs_count || 0} onions`;
  document.getElementById("res-defective-pct").textContent = `${defectivePct.toFixed(1)}%`;
  document.getElementById("res-defective-count").textContent = `${gr.defective_count || 0} onions`;

  const chip = document.getElementById("results-lot-grade-chip");
  chip.textContent = lotGradeLabel;
  chip.className = `lot-grade-chip ${lotGradeLabel.includes("Grade A") ? "grade-a" : lotGradeLabel.includes("Defective") ? "defective" : "urs"}`;

  const needsAttBanner = document.getElementById("needs-attention-banner");
  if (lot.needs_attention) {
    needsAttBanner.style.display = "flex";
    document.getElementById("needs-attention-text").textContent = lot.attention_reason || "Marker missing or confidence low.";
  } else {
    needsAttBanner.style.display = "none";
  }

  drawResultsCanvas();

  if (state.isAssistedMode) {
    speakText(`Inspection complete. Overall Result: ${lotGradeLabel}. Grade A: ${gradeAPct} percent. Total Onions: ${total}.`);
  }
}

function drawResultsCanvas() {
  const canvas = document.getElementById("results-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  const img = new Image();
  img.src = (state.capturedImages[0] && state.capturedImages[0].dataUrl) || "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='640' height='480' fill='%23111'></svg>";

  img.onload = () => {
    canvas.width = img.width || 640;
    canvas.height = img.height || 480;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    state.currentDetections.forEach((det, idx) => {
      const [x1, y1, x2, y2] = det.bbox || [20, 20, 100, 100];
      const w = x2 - x1;
      const h = y2 - y1;
      const bucket = det.bucket || determineOnionBucket(det.current_class || det.class, det.diameter_cm);

      let strokeColor = "#10B981";
      let chipLabel = "A";
      if (bucket === "urs") {
        strokeColor = "#F59E0B";
        chipLabel = "URS";
      } else if (bucket === "defective") {
        strokeColor = "#EF4444";
        chipLabel = "DEF";
      }

      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 3;
      ctx.strokeRect(x1, y1, w, h);

      ctx.fillStyle = strokeColor;
      ctx.fillRect(x1, y1 - 22, 42, 22);
      ctx.fillStyle = "#FFFFFF";
      ctx.font = "bold 13px Inter, sans-serif";
      ctx.fillText(chipLabel, x1 + 6, y1 - 6);
    });
  };

  canvas.onclick = (e) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const clickX = (e.clientX - rect.left) * scaleX;
    const clickY = (e.clientY - rect.top) * scaleY;

    const clicked = state.currentDetections.find(det => {
      const [x1, y1, x2, y2] = det.bbox || [];
      return clickX >= x1 && clickX <= x2 && clickY >= y1 && clickY <= y2;
    });

    if (clicked) {
      openOnionBottomSheet(clicked);
    }
  };
}

// ── Bottom Sheet: Onion Detail & Relabel ─────────────────────────────────────
function openOnionBottomSheet(detection) {
  state.selectedDetection = detection;
  const sheet = document.getElementById("onion-bottom-sheet-backdrop");
  const title = document.getElementById("sheet-onion-title");
  const diam = document.getElementById("sheet-diameter");
  const conf = document.getElementById("sheet-confidence");
  const bucket = document.getElementById("sheet-bucket");
  const currClass = document.getElementById("sheet-current-class");
  const select = document.getElementById("sheet-relabel-select");

  title.textContent = `Onion #${detection.id || 1}`;
  diam.textContent = detection.diameter_cm ? `${detection.diameter_cm.toFixed(1)} cm` : "N/A";
  conf.textContent = detection.confidence ? `${Math.round(detection.confidence * 100)}%` : "98%";
  bucket.textContent = (detection.bucket || "grade_a").toUpperCase();
  currClass.textContent = (detection.current_class || detection.original_class || "good").toUpperCase();
  select.value = detection.current_class || detection.original_class || "good";

  sheet.classList.add("active");
}

async function handleSaveOnionRelabel() {
  if (!state.selectedDetection || !state.currentLot) return;
  const newClass = document.getElementById("sheet-relabel-select").value;
  const lotId = state.currentLot.id;
  const detId = state.selectedDetection.id;

  try {
    if (lotId) {
      await api.overrideLotDetection(lotId, detId, newClass, "Staff manual adjustment in review sheet");
    }

    state.selectedDetection.current_class = newClass;
    state.selectedDetection.bucket = determineOnionBucket(newClass, state.selectedDetection.diameter_cm);
    state.selectedDetection.is_overridden = true;

    const recomputed = computeGrade(state.currentDetections);
    state.currentGradeResult = recomputed;
    displayInspectionResults(state.currentLot);

    document.getElementById("onion-bottom-sheet-backdrop").classList.remove("active");
    showToast(`Onion #${detId} updated to ${newClass}`);
  } catch (err) {
    showToast(`Override failed: ${err.message}`);
  }
}

// ── Screen 8: Human Verification ────────────────────────────────────────────
async function handleApproveLot() {
  if (!state.currentLot) return;
  const lotId = state.currentLot.id;

  try {
    await api.verifyLot(lotId, "approved");
    showToast("Grading Result Approved!");
    state.currentLot.status = "approved";
    navigateTo("screen-report");
    loadDigitalReportData();
  } catch (err) {
    showToast(`Approval failed: ${err.message}`);
  }
}

function handleOverrideReasonInput(e) {
  const val = e.target.value;
  const counter = document.getElementById("override-char-count");
  const submitBtn = document.getElementById("submit-override-btn");
  counter.textContent = `${val.length} / 10 characters minimum`;
  submitBtn.disabled = val.length < 10;
}

async function handleSubmitOverride() {
  if (!state.currentLot) return;
  const lotId = state.currentLot.id;
  const newGrade = document.getElementById("override-new-grade-select").value;
  const reason = document.getElementById("override-reason-textarea").value.trim();

  if (reason.length < 10) {
    showToast("Reason must be at least 10 characters");
    return;
  }

  try {
    await api.verifyLot(lotId, "overridden", newGrade, reason);
    showToast(`Lot Overridden to ${newGrade}`);
    state.currentLot.status = "overridden";
    if (state.currentGradeResult) {
      state.currentGradeResult.lot_grade = newGrade;
      state.currentGradeResult.lot_grade_label = `${newGrade} (Overridden)`;
    }
    navigateTo("screen-report");
    loadDigitalReportData();
  } catch (err) {
    showToast(`Override submission failed: ${err.message}`);
  }
}

// ── Screen 9: Digital Report ────────────────────────────────────────────────
let currentReportData = null;

async function loadDigitalReportData() {
  if (!state.currentLot) return;
  const lot = state.currentLot;
  const gr = state.currentGradeResult || lot.final_result || lot.ai_result || {};

  document.getElementById("report-batch-code").textContent = lot.batch_code || `KS-LOT-${lot.id}`;
  document.getElementById("report-farmer-centre").textContent = `Farmer: ${lot.farmer_name || "Farmer"} · Centre #${lot.centre_id || 1}`;
  document.getElementById("report-date").textContent = new Date().toUTCString();

  document.getElementById("rep-grade-a-pct").textContent = `${(gr.grade_a_pct || 0).toFixed(1)}%`;
  document.getElementById("rep-grade-a-count").textContent = gr.grade_a_count || 0;
  document.getElementById("rep-urs-pct").textContent = `${(gr.urs_pct || 0).toFixed(1)}%`;
  document.getElementById("rep-urs-count").textContent = gr.urs_count || 0;
  document.getElementById("rep-defective-pct").textContent = `${(gr.defective_pct || 0).toFixed(1)}%`;
  document.getElementById("rep-defective-count").textContent = gr.defective_count || 0;

  try {
    const rep = await api.generateReport(lot.id);
    currentReportData = rep;
    document.getElementById("report-hash-preview").textContent = `SHA-256: ${rep.report_hash.slice(0, 24)}...`;
    const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(`${window.location.origin}/verify/${rep.id}/view`)}`;
    document.getElementById("report-qr-img").src = qrUrl;
  } catch (err) {
    console.warn("[Report generation]", err);
  }
}

async function handleGenerateReport() {
  navigateTo("screen-report");
  await loadDigitalReportData();
}

function handleDownloadPdf() {
  if (!currentReportData || !currentReportData.id) {
    showToast("Generating PDF certificate...");
    return;
  }
  const downloadUrl = `/reports/${currentReportData.id}/download`;
  window.open(downloadUrl, "_blank");
}

function handleShareReport() {
  const verifyUrl = currentReportData ? `${window.location.origin}/verify/${currentReportData.id}/view` : window.location.href;
  const text = `Kisan Setu Official Onion Grading Certificate for Batch ${state.currentLot?.batch_code || ""}: ${verifyUrl}`;

  if (navigator.share) {
    navigator.share({ title: "Kisan Setu Quality Report", text, url: verifyUrl }).catch(() => {});
  } else {
    const waUrl = `https://wa.me/?text=${encodeURIComponent(text)}`;
    window.open(waUrl, "_blank");
  }
}

// ── Screen 11: Farmer - My Batches ──────────────────────────────────────────
let farmerBatchesCache = [];

async function loadFarmerBatches() {
  const welcomeEl = document.getElementById("farmer-welcome-name");
  if (api.user) welcomeEl.textContent = api.user.name || "Farmer";

  try {
    const lots = await api.getFarmerLots();
    farmerBatchesCache = lots || [];
    renderFarmerBatches(farmerBatchesCache);
  } catch (err) {
    console.warn("[Farmer Lots Error]", err);
  }
}

function filterFarmerBatches(gradeFilter) {
  if (!gradeFilter || gradeFilter === "all") {
    renderFarmerBatches(farmerBatchesCache);
  } else {
    const filtered = farmerBatchesCache.filter(b => {
      const lbl = (b.grade_result && b.grade_result.lot_grade) || "";
      return lbl.toLowerCase().includes(gradeFilter.toLowerCase());
    });
    renderFarmerBatches(filtered);
  }
}

function renderFarmerBatches(batches) {
  const container = document.getElementById("farmer-batches-list");
  if (!container) return;

  if (!batches || batches.length === 0) {
    container.innerHTML = `<div class="card" style="text-align:center; padding:24px; color:var(--color-text-muted);">${t("farmer_empty")}</div>`;
    return;
  }

  container.innerHTML = batches.map(b => {
    const gr = b.grade_result || b.final_result || b.ai_result || {};
    const label = gr.lot_grade_label || "Grade A (75.0%)";
    const gradeClass = label.includes("Grade A") ? "grade-a" : label.includes("Defective") ? "defective" : "urs";
    const dateStr = b.batch_date ? new Date(b.batch_date).toLocaleDateString("en-IN", { month: "short", day: "numeric", year: "numeric" }) : "";

    return `
      <div class="batch-item" data-farmer-lot-id="${b.id}">
        <div class="batch-thumb">📦</div>
        <div class="batch-details">
          <div class="batch-code">${b.batch_code || `KS-LOT-${b.id}`}</div>
          <div class="batch-meta">${b.centre ? b.centre.name : "Nashik APMC"} · ${dateStr}</div>
          <span class="lot-grade-chip ${gradeClass}">${label}</span>
        </div>
        <span style="color:var(--color-forest); font-weight:700;">→</span>
      </div>
    `;
  }).join("");

  container.querySelectorAll(".batch-item").forEach(item => {
    item.addEventListener("click", () => {
      const id = parseInt(item.getAttribute("data-farmer-lot-id"));
      const selected = farmerBatchesCache.find(b => b.id === id);
      if (selected) {
        displayFarmerBatchDetail(selected);
      }
    });
  });
}

// ── Screen 12: Farmer - Batch Report & Voice Readout ────────────────────────
function displayFarmerBatchDetail(lot) {
  state.currentLot = lot;
  const gr = lot.grade_result || lot.final_result || lot.ai_result || {};
  const gradeAPct = gr.grade_a_pct || 75;
  const ursPct = gr.urs_pct || 17;
  const defectivePct = gr.defective_pct || 8;
  const label = gr.lot_grade_label || "Grade A (75.0%)";

  document.getElementById("farmer-detail-batch-code").textContent = lot.batch_code || `KS-LOT-${lot.id}`;
  document.getElementById("farmer-detail-centre").textContent = lot.centre ? lot.centre.name : "Nashik APMC Centre";
  document.getElementById("farmer-detail-lot-grade").textContent = label;

  document.getElementById("farmer-bar-grade-a-val").textContent = `${gradeAPct.toFixed(1)}%`;
  document.getElementById("farmer-bar-grade-a").style.width = `${gradeAPct}%`;
  document.getElementById("farmer-bar-urs-val").textContent = `${ursPct.toFixed(1)}%`;
  document.getElementById("farmer-bar-urs").style.width = `${ursPct}%`;
  document.getElementById("farmer-bar-defective-val").textContent = `${defectivePct.toFixed(1)}%`;
  document.getElementById("farmer-bar-defective").style.width = `${defectivePct}%`;

  drawFarmerDetailCanvas(lot);
  navigateTo("screen-farmer-detail");
}

function drawFarmerDetailCanvas(lot) {
  const canvas = document.getElementById("farmer-detail-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  canvas.width = 640;
  canvas.height = 420;
  ctx.fillStyle = "#1E293B";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = "#F8FAFC";
  ctx.font = "bold 16px Inter, sans-serif";
  ctx.fillText(`🧅 Inspection Capture for ${lot.batch_code || ""}`, 20, 40);

  if (state.showAnnotationBoxes && lot.detections) {
    lot.detections.forEach((det, i) => {
      const [x1, y1, x2, y2] = det.bbox || [30 + i * 50, 80, 80 + i * 50, 130];
      ctx.strokeStyle = det.bucket === "grade_a" ? "#10B981" : det.bucket === "urs" ? "#F59E0B" : "#EF4444";
      ctx.lineWidth = 2;
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    });
  }
}

function handleFarmerToggleBoxes() {
  state.showAnnotationBoxes = !state.showAnnotationBoxes;
  if (state.currentLot) drawFarmerDetailCanvas(state.currentLot);
  showToast(state.showAnnotationBoxes ? "AI Overlay ON" : "AI Overlay OFF");
}

function handleFarmerReadAloud() {
  if (!state.currentLot) return;
  const gr = state.currentLot.grade_result || state.currentLot.final_result || {};
  const code = state.currentLot.batch_code || "your batch";
  const grade = gr.lot_grade_label || "Grade A";
  const aPct = (gr.grade_a_pct || 0).toFixed(0);
  const ursPct = (gr.urs_pct || 0).toFixed(0);
  const defPct = (gr.defective_pct || 0).toFixed(0);

  let text = "";
  const lang = getLang();
  if (lang === "hi") {
    text = `नमस्ते किसान भाई। आपके प्याज बैच ${code} का अंतिम परिणाम ${grade} है। इसमें ग्रेड ए प्याज ${aPct} प्रतिशत, यूआरएस प्याज ${ursPct} प्रतिशत, और दोषपूर्ण प्याज ${defPct} प्रतिशत है।`;
  } else if (lang === "te") {
    text = `నమస్కారం రైతు సోదరా. మీ ఉల్లిపాయల బ్యాచ్ ${code} నాణ్యత ఫలితం ${grade}. ఇందులో గ్రేడ్ ఎ ${aPct} శాతం, యుఆర్ఎస్ ${ursPct} శాతం, మరియు లోపం ఉన్నవి ${defPct} శాతం ఉన్నాయి.`;
  } else {
    text = `Hello. Your onion batch ${code} has been verified as ${grade}. Grade A premium onions: ${aPct} percent. Under-rated onions: ${ursPct} percent. Defective onions: ${defPct} percent.`;
  }

  speakText(text);
}
