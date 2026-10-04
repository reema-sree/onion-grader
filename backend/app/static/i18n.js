/**
 * Kisan Setu - Internationalization (i18n) Module
 * Supports English, Hindi (हिन्दी), and Telugu (తెలుగు)
 */

export const translations = {
  en: {
    // Brand & General
    app_name: "Kisan Setu",
    tagline: "AI Powered Onion Grading",
    demo_mode: "DEMO MODE",
    offline_notice: "You are offline. Results will be saved locally and synced when online.",
    online_status: "Online",
    offline_status: "Offline",
    syncing: "Syncing...",
    sync_now: "Sync Now",
    loading: "Loading...",
    retry: "Retry",
    cancel: "Cancel",
    confirm: "Confirm",
    back: "Back",
    save: "Save",
    continue: "Continue",
    close: "Close",
    logout: "Log Out",

    // Roles
    role_staff: "Procurement Staff",
    role_staff_desc: "Grade and verify onion batches at procurement centres",
    role_farmer: "Farmer",
    role_farmer_desc: "View your verified batch reports and grading certificates",
    role_admin: "Administrator",
    role_admin_desc: "Manage centres, users, and grading rules",
    welcome_back: "Welcome Back",
    login_to_continue: "Select your role to continue",

    // Auth
    email_label: "Email Address",
    password_label: "Password",
    phone_label: "Phone Number",
    otp_label: "6-Digit OTP",
    get_otp: "Get OTP",
    verify_login: "Verify & Log In",
    login_btn: "Log In",
    assisted_mode: "Assisted Mode (CSC Operator)",
    assisted_mode_hint: "Larger text, simplified buttons, and voice guidance enabled",
    mock_otp_hint: "Dev Mode: Use OTP 123456",

    // Dashboard & Admin Overview
    dashboard_greeting: "Hello",
    stat_scanned: "Scanned Today",
    stat_approved: "Approved",
    stat_pending: "Pending Review",
    new_batch: "+ New Batch",
    recent_batches: "Recent Batches",
    all_batches: "All Batches",
    view_all: "View All",
    no_batches: "No batches found",

    // Admin Dashboard KPI
    admin_dashboard_title: "System Overview",
    admin_kpi_total_batches: "Total Batches",
    admin_kpi_centres: "Active Centres",
    admin_kpi_avg_grade_a: "Avg Grade A %",
    admin_kpi_override_rate: "Override Rate %",
    period_7d: "Last 7 Days",
    period_30d: "Last 30 Days",
    period_all: "All Time",
    centre_performance: "Centre Performance (Avg Grade A %)",
    high_override_warning: "High Override Rate (>15%)",
    admin_nav_users: "Users",
    admin_nav_centres: "Procurement Centres",
    admin_nav_rules: "Grading Rules",
    admin_nav_audit: "Audit Logs",

    // Navigation
    nav_home: "Home",
    nav_batches: "Batches",
    nav_reports: "Reports",
    nav_profile: "Profile",
    nav_admin: "Admin",

    // Create Batch
    create_batch_title: "Create Batch",
    batch_id_label: "Batch Code",
    batch_id_auto: "Assigned automatically (e.g. KS-2026-00001)",
    farmer_label: "Farmer",
    select_farmer: "Select Farmer",
    quick_add_farmer: "+ Quick Add Farmer",
    farmer_name: "Farmer Full Name",
    farmer_phone: "Phone Number",
    centre_label: "Procurement Centre",
    crop_label: "Crop",
    crop_onion: "Onion",
    crop_tomato_coming_soon: "Tomato (Coming Soon)",
    crop_potato_coming_soon: "Potato (Coming Soon)",
    date_label: "Batch Date",
    weight_label: "Weight (kg) - Optional",
    continue_to_camera: "Continue to Camera",

    // Capture Camera
    capture_title: "Capture Batch",
    camera_hint: "Place the printed ArUco marker flat and spread onions apart",
    marker_detected: "Reference Marker Detected (5.0 cm)",
    marker_missing: "Marker Missing — Place beside onions",
    blur_warning: "Photo seems blurry. Hold camera steady and retake.",
    photos_count: "Photos",
    take_photo: "Shutter",
    upload_file: "Gallery / File",
    analyse_batch: "Analyse Batch",
    max_photos_hint: "1 to 3 photos per batch",

    // AI Analysis
    analysis_title: "AI Analysis",
    analysing_subtitle: "Detecting individual onions & assessing quality...",
    cancel_analysis: "Cancel",
    stage_quality: "Image Quality & Blur Check",
    stage_marker: "Reference Marker Calibration",
    stage_detection: "Onion Detection & Segmentation",
    stage_size: "Physical Size Measurement",
    stage_defects: "Defect & Rot Classification",
    stage_grading: "Three-Bucket Agmark Grading",
    retake_photo: "Retake Photo",

    // Results
    results_title: "AI Inspection Results",
    total_onions: "Total Onions",
    grade_a: "Grade A (Premium)",
    grade_urs: "URS (Undersized)",
    grade_defective: "Defective",
    tap_onion_hint: "Tap any onion below to view details or adjust classification",
    needs_attention_title: "Needs Attention",
    review_verify_btn: "Review & Verify",
    generate_report_btn: "Generate Report",
    verify_first_hint: "Batch must be verified by staff before generating official report",

    // Onion Detail Bottom Sheet
    onion_details: "Onion Details",
    diameter: "Diameter",
    confidence: "Confidence",
    bucket_label: "Bucket",
    relabel_class: "Relabel Class",
    save_override: "Save Class Change",

    // Verification
    verification_title: "Quality Verification",
    ai_grade_result: "AI Calculated Grade",
    is_result_correct: "Is this grading result correct?",
    approve_btn: "Approve AI Result",
    override_btn: "Override Result",
    new_grade_label: "New Lot Grade",
    override_reason_label: "Reason for Override (Required, min 10 characters)",
    override_reason_placeholder: "e.g. Physical cross-cut inspection found internal rot...",
    submit_override: "Confirm Override",
    verified_by_label: "Verified by",
    verified_at_label: "Verified at",

    // Digital Report
    report_title: "Quality Inspection Certificate",
    scan_to_verify: "Scan QR to verify report online",
    download_pdf: "Download Official PDF",
    share_report: "Share Report",
    share_whatsapp: "Share on WhatsApp",
    share_copied: "Verification link copied to clipboard!",
    verified_stamp: "OFFICIALLY VERIFIED",
    overridden_stamp: "OVERRIDDEN BY STAFF",

    // Farmer Screen
    farmer_greeting: "Welcome",
    my_batches_title: "My Graded Batches",
    filter_all: "All",
    filter_grade_a: "Grade A",
    filter_urs: "URS",
    filter_defective: "Defective",
    read_aloud: "Read Aloud (Voice)",
    speech_not_supported: "Text to speech is not supported in this browser.",
    farmer_empty: "No verified batches yet. Batches will appear here once verified by centre staff.",
    view_images: "Captured Images",
    toggle_annotation: "Toggle AI Overlay",

    // Admin Users Management
    manage_users_title: "User Management",
    search_users_placeholder: "Search by name, email, or phone...",
    filter_role_all: "All Roles",
    filter_role_farmer: "Farmer",
    filter_role_staff: "Staff",
    filter_role_csc: "CSC Operator",
    filter_role_admin: "Admin",
    add_user_btn: "+ Add User",
    user_status_active: "Active",
    user_status_inactive: "Deactivated",

    // Admin Centres Management
    manage_centres_title: "Procurement Centres",
    add_centre_btn: "+ Add Centre",
    centre_code_label: "Centre Code (e.g. C01, C02)",
    centre_name_label: "Centre Name",
    district_label: "District",
    state_label: "State",

    // Admin Grading Rules
    manage_rules_title: "Grading Rules Governance",
    current_rule_version: "Active Rule Version",
    min_size_label: "Min Diameter for Grade A (cm)",
    grade_a_threshold_label: "Grade A Lot Threshold (%)",
    defective_threshold_label: "Defective Lot Threshold (%)",
    rule_change_note_label: "Version Change Note (Required, min 5 chars)",
    save_new_version_btn: "Publish New Rule Version",
    rules_immutable_notice: "Saving creates a new versioned snapshot (e.g., v2.1). Past certificates remain linked to their original grading rule version.",

    // Audit Log
    audit_log_title: "System Audit Trail",
    export_csv: "📥 Export CSV",
    filter_action_all: "All Actions",
    filter_entity_all: "All Entities",
    audit_readonly_badge: "Strictly Read-Only (Immutable)",
    view_diff: "View Diff JSON",

    // Profile & Settings
    profile_title: "My Profile",
    language: "Language",
    app_version: "Version v2.0 (Agmark Compliant)",
    privacy_terms: "Terms & Privacy Policy",
    about_kisan_setu: "Kisan Setu is an open digital public infrastructure project for objective agricultural produce grading."
  },

  hi: {
    // Brand & General
    app_name: "किसान सेतु",
    tagline: "एआई आधारित प्याज ग्रेडिंग",
    demo_mode: "डेमो मोड",
    offline_notice: "आप ऑफ़लाइन हैं। परिणाम स्थानीय रूप से सहेजे जाएंगे।",
    online_status: "ऑनलाइन",
    offline_status: "ऑफ़लाइन",
    syncing: "सिंक हो रहा है...",
    sync_now: "सिंक करें",
    loading: "लोड हो रहा है...",
    retry: "पुनः प्रयास करें",
    cancel: "रद्द करें",
    confirm: "पुष्टि करें",
    back: "वापस",
    save: "सहेजें",
    continue: "आगे बढ़ें",
    close: "बंद करें",
    logout: "लॉग आउट",

    // Admin Dashboard KPI
    admin_dashboard_title: "प्रशासनिक डैशबोर्ड",
    admin_kpi_total_batches: "कुल बैच",
    admin_kpi_centres: "सक्रिय केंद्र",
    admin_kpi_avg_grade_a: "औसत ग्रेड ए %",
    admin_kpi_override_rate: "ओवरराइड दर %",
    period_7d: "पिछले 7 दिन",
    period_30d: "पिछले 30 दिन",
    period_all: "अब तक का समय",
    centre_performance: "केंद्र प्रदर्शन (औसत ग्रेड ए %)",
    high_override_warning: "उच्च ओवरराइड दर (>15%)",
    admin_nav_users: "उपयोगकर्ता",
    admin_nav_centres: "खरीद केंद्र",
    admin_nav_rules: "ग्रेडिंग नियम",
    admin_nav_audit: "ऑडिट लॉग",

    // Navigation
    nav_home: "होम",
    nav_batches: "बैच सूची",
    nav_reports: "रिपोर्ट",
    nav_profile: "प्रोफ़ाइल",
    nav_admin: "एडमिन",

    // Admin Users Management
    manage_users_title: "उपयोगकर्ता प्रबंधन",
    search_users_placeholder: "नाम, ईमेल या फोन से खोजें...",
    filter_role_all: "सभी भूमिकाएं",
    add_user_btn: "+ नया उपयोगकर्ता जोड़ें",
    user_status_active: "सक्रिय",
    user_status_inactive: "निष्क्रिय",

    // Admin Centres Management
    manage_centres_title: "खरीद केंद्र प्रबंधन",
    add_centre_btn: "+ नया केंद्र जोड़ें",
    centre_code_label: "केंद्र कोड (उदा. C01, C02)",

    // Admin Grading Rules
    manage_rules_title: "ग्रेडिंग नियम शासन",
    current_rule_version: "वर्तमान सक्रिय संस्करण",
    save_new_version_btn: "नया नियम संस्करण प्रकाशित करें",

    // Audit Log
    audit_log_title: "सिस्टम ऑडिट ट्रेल",
    export_csv: "📥 सीएसवी डाउनलोड करें",
    audit_readonly_badge: "केवल पढ़ने योग्य (अपरिवर्तनीय)",
    view_diff: "अंतर JSON देखें"
  },

  te: {
    // Brand & General
    app_name: "కిసాన్ సేతు",
    tagline: "ఏఐ ఆధారిత ఉల్లిపాయల గ్రేడింగ్",
    demo_mode: "డెమో మోడ్",
    offline_notice: "మీరు ఆఫ్‌లైన్‌లో ఉన్నారు. ఫలితాలు స్థానికంగా సేవ్ చేయబడతాయి.",
    online_status: "ఆన్‌లైన్",
    offline_status: "ఆఫ్‌లైన్",
    syncing: "సింక్ అవుతోంది...",
    sync_now: "సింక్ చేయండి",
    loading: "లోడ్ అవుతోంది...",
    retry: "మళ్ళీ ప్రయత్నించండి",
    cancel: "రద్దు చేయండి",
    confirm: "నిర్ధారించండి",
    back: "వెనుకకు",
    save: "సేవ్ చేయండి",
    continue: "కొనసాగించండి",
    close: "మూసివేయండి",
    logout: "లాగ్ అవుట్",

    // Admin Dashboard KPI
    admin_dashboard_title: "అడ్మిన్ డాష్‌బోర్డ్",
    admin_kpi_total_batches: "మొత్తం బ్యాచ్‌లు",
    admin_kpi_centres: "కేంద్రాలు",
    admin_kpi_avg_grade_a: "సగటు గ్రేడ్ ఎ %",
    admin_kpi_override_rate: "సవరణ రేటు %",
    period_7d: "గత 7 రోజులు",
    period_30d: "గత 30 రోజులు",
    period_all: "మొత్తం సమయం",
    centre_performance: "కేంద్రాల పనితీరు",
    high_override_warning: "ఎక్కువ సవరణలు (>15%)",
    admin_nav_users: "వినియోగదారులు",
    admin_nav_centres: "సేకరణ కేంద్రాలు",
    admin_nav_rules: "గ్రేడింగ్ నిబంధనలు",
    admin_nav_audit: "ఆడిట్ లాగ్స్",

    // Navigation
    nav_home: "హోమ్",
    nav_batches: "బ్యాచ్‌లు",
    nav_reports: "నివేదికలు",
    nav_profile: "ప్రొఫైల్",
    nav_admin: "అడ్మిన్",

    // Admin Users Management
    manage_users_title: "వినియోగదారుల నిర్వహణ",
    search_users_placeholder: "పేరు, ఈమెయిల్ లేదా ఫోన్‌ ద్వారా వెతకండి...",
    add_user_btn: "+ కొత్త వినియోగదారుని చేర్చండి",

    // Admin Centres Management
    manage_centres_title: "సేకరణ కేంద్రాలు",
    add_centre_btn: "+ కొత్త కేంద్రాన్ని చేర్చండి",

    // Admin Grading Rules
    manage_rules_title: "గ్రేడింగ్ నిబంధనలు",
    current_rule_version: "ప్రస్తుత వెర్షన్",
    save_new_version_btn: "కొత్త నిబంధన వెర్షన్ ప్రచురించండి",

    // Audit Log
    audit_log_title: "సిస్టమ్ ఆడిట్ ట్రాక్",
    export_csv: "📥 CSV డౌన్‌లోడ్",
    audit_readonly_badge: "మార్చడానికి వీలులేనిది",
    view_diff: "JSON వ్యత్యాసం చూడండి"
  }
};

let currentLang = localStorage.getItem("kisan_setu_lang") || "en";

export function getLang() {
  return currentLang;
}

export function setLang(lang) {
  if (translations[lang]) {
    currentLang = lang;
    localStorage.setItem("kisan_setu_lang", lang);
    applyTranslations();
  }
}

export function t(key) {
  const dict = translations[currentLang] || translations.en;
  return dict[key] || translations.en[key] || key;
}

export function applyTranslations() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    const key = el.getAttribute("data-i18n-placeholder");
    el.setAttribute("placeholder", t(key));
  });
  document.querySelectorAll("[data-i18n-title]").forEach(el => {
    const key = el.getAttribute("data-i18n-title");
    el.setAttribute("title", t(key));
  });
}
