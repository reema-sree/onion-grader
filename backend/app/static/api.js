/**
 * Kisan Setu - Unified API Client
 * Connects frontend PWA to FastAPI backend with full token & error management.
 */

const API_BASE = window.location.origin;

class ApiClient {
  constructor() {
    this.token = localStorage.getItem("kisan_setu_token") || null;
    this.user = JSON.parse(localStorage.getItem("kisan_setu_user") || "null");
  }

  setSession(token, user) {
    this.token = token;
    this.user = user;
    if (token) {
      localStorage.setItem("kisan_setu_token", token);
    } else {
      localStorage.removeItem("kisan_setu_token");
    }
    if (user) {
      localStorage.setItem("kisan_setu_user", JSON.stringify(user));
    } else {
      localStorage.removeItem("kisan_setu_user");
    }
  }

  clearSession() {
    this.setSession(null, null);
  }

  isAuthenticated() {
    return !!this.token && !!this.user;
  }

  getRole() {
    return this.user ? this.user.role : null;
  }

  async request(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const headers = options.headers || {};

    if (this.token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    try {
      const resp = await fetch(url, { ...options, headers });
      
      if (resp.status === 401) {
        this.clearSession();
        window.dispatchEvent(new CustomEvent("kisan_setu_auth_expired"));
      }

      if (!resp.ok) {
        let errDetail = "Request failed";
        try {
          const errData = await resp.json();
          errDetail = errData.detail || errData.message || JSON.stringify(errData);
        } catch (_) {
          errDetail = `${resp.status} ${resp.statusText}`;
        }
        const error = new Error(typeof errDetail === "string" ? errDetail : JSON.stringify(errDetail));
        error.status = resp.status;
        error.detail = errDetail;
        throw error;
      }

      const contentType = resp.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        return await resp.json();
      }
      return resp;
    } catch (err) {
      if (!navigator.onLine) {
        err.isOffline = true;
      }
      throw err;
    }
  }

  // ── Auth Endpoints ────────────────────────────────────────────────────────
  async loginEmail(email, password) {
    const data = await this.request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    this.setSession(data.access_token, data.user);
    return data;
  }

  async requestPhoneOtp(phone) {
    return await this.request("/auth/phone-otp/request", {
      method: "POST",
      body: JSON.stringify({ phone }),
    });
  }

  async verifyPhoneOtp(phone, otp) {
    const data = await this.request("/auth/phone-otp/verify", {
      method: "POST",
      body: JSON.stringify({ phone, otp }),
    });
    this.setSession(data.access_token, data.user);
    return data;
  }

  // ── Dashboard & Admin Summaries ──────────────────────────────────────────
  async getDashboardSummary() {
    return await this.request("/dashboard/summary");
  }

  async getAdminSummary(period = "30d") {
    return await this.request(`/admin/summary?period=${period}`);
  }

  async getCentres() {
    return await this.request("/admin/centres");
  }

  async createCentre(payload) {
    return await this.request("/admin/centres", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async updateCentre(centreId, payload) {
    return await this.request(`/admin/centres/${centreId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  async getUsers(params = {}) {
    const qs = new URLSearchParams();
    if (typeof params === "string") {
      qs.append("role", params);
    } else if (typeof params === "object") {
      if (params.role) qs.append("role", params.role);
      if (params.search) qs.append("search", params.search);
      if (params.centre_id) qs.append("centre_id", params.centre_id);
    }
    return await this.request(`/admin/users${qs.toString() ? "?" + qs.toString() : ""}`);
  }

  async createUser(payload) {
    return await this.request("/admin/users", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async updateUser(userId, payload) {
    return await this.request(`/admin/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  async toggleUserActive(userId) {
    return await this.request(`/admin/users/${userId}/toggle-active`, {
      method: "POST",
    });
  }

  async getGradingRules() {
    return await this.request("/admin/grading-rules");
  }

  async updateGradingRules(payload) {
    return await this.request("/admin/grading-rules", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async getAuditLogs(params = {}) {
    const qs = new URLSearchParams();
    if (params.action) qs.append("action", params.action);
    if (params.entity_type) qs.append("entity_type", params.entity_type);
    if (params.actor_id) qs.append("actor_id", params.actor_id);
    if (params.batch_code) qs.append("batch_code", params.batch_code);
    if (params.date_from) qs.append("date_from", params.date_from);
    if (params.date_to) qs.append("date_to", params.date_to);
    if (params.limit) qs.append("limit", params.limit);
    if (params.skip) qs.append("skip", params.skip);

    return await this.request(`/admin/audit-logs${qs.toString() ? "?" + qs.toString() : ""}`);
  }

  getAuditLogExportUrl(params = {}) {
    const qs = new URLSearchParams();
    if (params.action) qs.append("action", params.action);
    if (params.entity_type) qs.append("entity_type", params.entity_type);
    if (params.actor_id) qs.append("actor_id", params.actor_id);
    if (params.date_from) qs.append("date_from", params.date_from);
    if (params.date_to) qs.append("date_to", params.date_to);
    return `${API_BASE}/admin/audit-logs/export${qs.toString() ? "?" + qs.toString() : ""}`;
  }

  // ── Lots Lifecycle ────────────────────────────────────────────────────────
  async createLot(payload) {
    return await this.request("/lots", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async uploadLotImages(lotId, files) {
    const formData = new FormData();
    for (const file of files) {
      formData.append("files", file);
    }
    return await this.request(`/lots/${lotId}/images`, {
      method: "POST",
      headers: {},
      body: formData,
    });
  }

  async startGrading(lotId) {
    return await this.request(`/lots/${lotId}/grade`, {
      method: "POST",
    });
  }

  async getGradeStatus(lotId) {
    return await this.request(`/lots/${lotId}/grade/status`);
  }

  async getLot(lotId) {
    return await this.request(`/lots/${lotId}`);
  }

  async listLots(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return await this.request(`/lots${qs ? "?" + qs : ""}`);
  }

  async getFarmerLots() {
    return await this.request("/me/lots");
  }

  async verifyLot(lotId, decision, newGrade = null, reason = null) {
    return await this.request(`/lots/${lotId}/verify`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        new_grade: newGrade,
        reason,
      }),
    });
  }

  async overrideLotDetection(lotId, detectionId, newClass, reason) {
    return await this.request(`/lots/${lotId}/override`, {
      method: "POST",
      body: JSON.stringify({
        reason,
        detection_overrides: [
          {
            detection_id: detectionId,
            new_class: newClass,
          },
        ],
      }),
    });
  }

  async generateReport(lotId) {
    return await this.request(`/lots/${lotId}/report`, {
      method: "POST",
    });
  }

  async syncOfflineLot(offlinePayload) {
    return await this.request("/lots/sync", {
      method: "POST",
      body: JSON.stringify(offlinePayload),
    });
  }

  async sendReportSms(lotId, toPhone = null) {
    return await this.request(`/lots/${lotId}/send-sms`, {
      method: "POST",
      body: JSON.stringify({ to_phone: toPhone }),
    });
  }
}

export const api = new ApiClient();
