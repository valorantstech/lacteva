/**
 * The portal's message catalogs (DEMO-013 §6).
 *
 * One file, keyed by language, keys namespaced by area. English is both the
 * default and the reference: a key missing from another catalog falls back to
 * it, so a partial translation degrades to a working screen rather than to
 * blanks.
 *
 * **Keys, not sentences, are the interface.** A component asks for
 * `nav.customers`; it never asks what country it is in. That is the whole
 * point — adding Arabic is a new object below, not a new branch anywhere.
 *
 * **What is deliberately NOT here.** Money and dates. Those are not
 * translation: an amount is formatted from an exact decimal string
 * (`components/money.tsx`) and carries the organization's currency, and a date
 * is rendered in the organization's timezone. Putting them in a catalog would
 * invite a translator to change a number.
 *
 * Hindi covers the areas the work order prioritises — authentication,
 * navigation, dashboard, the sales and procurement screens, common actions,
 * validation. It is not yet complete for every deep page, and the fallback
 * makes that a partly-English screen rather than a broken one.
 */

export type Catalog = Record<string, string>;

const en: Catalog = {
  // --- common actions -------------------------------------------------------
  "action.save": "Save",
  "action.cancel": "Cancel",
  "action.close": "Close",
  "action.search": "Search",
  "action.refresh": "Refresh",
  "action.retry": "Try again",
  "action.create": "Create",
  "action.edit": "Edit",
  "action.view": "View",
  "action.back": "Back",
  "action.next": "Next",
  "action.previous": "Previous",
  "action.export": "Export",
  "action.print": "Print",
  "action.signOut": "Sign out",

  // --- authentication -------------------------------------------------------
  "auth.signIn": "Sign in",
  "auth.signingIn": "Signing in…",
  "auth.email": "Email",
  "auth.password": "Password",
  "auth.organization": "Organization",
  "auth.signedInAs": "Signed in as",
  "auth.chooseOrganization": "Choose an organization",
  "auth.failed": "Email or password is incorrect.",

  // --- navigation -----------------------------------------------------------
  "nav.operations": "Operations",
  "nav.sales": "Sales",
  "nav.pricing": "Pricing",
  "nav.finance": "Finance",
  "nav.platform": "Platform",
  "nav.dashboard": "Dashboard",
  "nav.centers": "Centers",
  "nav.suppliers": "Suppliers",
  "nav.transactions": "Transactions",
  "nav.customers": "Customers",
  "nav.deliveries": "Deliveries",
  "nav.billing": "Billing",
  "nav.receivables": "Who owes money",
  "nav.rateCards": "Rate cards",
  "nav.matrices": "Matrices",
  "nav.playground": "Playground",
  "nav.settlements": "Settlements",
  "nav.payments": "Payments",
  "nav.receipts": "Receipts",
  "nav.reports": "Reports",
  "nav.notifications": "Notifications",
  "nav.sync": "Sync",
  "nav.users": "Users",
  "nav.roles": "Roles",
  "nav.organizations": "Organizations",
  "nav.audit": "Audit",
  "nav.configuration": "Configuration",
  "nav.settings": "Settings",

  // --- dashboard ------------------------------------------------------------
  "dashboard.title": "Dashboard",
  "dashboard.procurement": "Procurement",
  "dashboard.sales": "Sales",
  "dashboard.today": "Today",
  "dashboard.thisMonth": "This month",
  "dashboard.collected": "Collected",
  "dashboard.delivered": "Delivered",
  "dashboard.outstanding": "Outstanding",
  "dashboard.needsAttention": "Needs attention",

  // --- entities -------------------------------------------------------------
  "entity.customer": "Customer",
  "entity.supplier": "Supplier",
  "entity.center": "Collection centre",
  "entity.delivery": "Delivery",
  "entity.invoice": "Bill",
  "entity.payment": "Payment",
  "entity.receipt": "Receipt",
  "entity.settlement": "Settlement",
  "entity.user": "User",
  "entity.role": "Role",

  // --- fields ---------------------------------------------------------------
  "field.name": "Name",
  "field.code": "Code",
  "field.phone": "Phone",
  "field.address": "Address",
  "field.status": "Status",
  "field.date": "Date",
  "field.quantity": "Quantity",
  "field.amount": "Amount",
  "field.unitPrice": "Unit price",
  "field.currency": "Currency",
  "field.total": "Total",
  "field.paid": "Paid",
  "field.balance": "Balance",
  "field.period": "Period",
  "field.language": "Language",
  "field.timezone": "Timezone",
  "field.country": "Country",

  // --- states ---------------------------------------------------------------
  "state.loading": "Loading…",
  "state.empty": "Nothing to show yet",
  "state.error": "Something went wrong",
  "state.unreachable": "Could not reach the platform",
  "state.noPermission": "You do not have permission to see this",

  // --- validation -----------------------------------------------------------
  "validation.required": "This field is required",
  "validation.invalid": "This value is not valid",
  "validation.tooLong": "This value is too long",
  "validation.mustBeNumber": "Enter a number",

  // --- organization settings (DEMO-013) -------------------------------------
  "settings.title": "Organization settings",
  "settings.locale": "Country and language",
  "settings.localeHelp":
    "These decide what your money is counted in, when your business day begins, and which languages your people can work in.",
  "settings.country": "Country",
  "settings.currency": "Currency",
  "settings.timezone": "Timezone",
  "settings.defaultLanguage": "Default language",
  "settings.supportedLanguages": "Languages your organization has enabled",
  "settings.myLanguage": "My language",
  "settings.myLanguageHelp": "Only you see this. It changes nothing for anyone else.",
  "settings.saved": "Saved",
  "settings.countryFixed": "Country is set when the organization is created and is not changed here.",
};

const hi: Catalog = {
  // --- common actions -------------------------------------------------------
  "action.save": "सहेजें",
  "action.cancel": "रद्द करें",
  "action.close": "बंद करें",
  "action.search": "खोजें",
  "action.refresh": "ताज़ा करें",
  "action.retry": "पुनः प्रयास करें",
  "action.create": "बनाएँ",
  "action.edit": "संपादित करें",
  "action.view": "देखें",
  "action.back": "वापस",
  "action.next": "आगे",
  "action.previous": "पिछला",
  "action.export": "निर्यात करें",
  "action.print": "प्रिंट करें",
  "action.signOut": "साइन आउट",

  // --- authentication -------------------------------------------------------
  "auth.signIn": "साइन इन करें",
  "auth.signingIn": "साइन इन हो रहा है…",
  "auth.email": "ईमेल",
  "auth.password": "पासवर्ड",
  "auth.organization": "संगठन",
  "auth.signedInAs": "के रूप में साइन इन",
  "auth.chooseOrganization": "संगठन चुनें",
  "auth.failed": "ईमेल या पासवर्ड गलत है।",

  // --- navigation -----------------------------------------------------------
  "nav.operations": "संचालन",
  "nav.sales": "बिक्री",
  "nav.pricing": "मूल्य निर्धारण",
  "nav.finance": "वित्त",
  "nav.platform": "प्लेटफ़ॉर्म",
  "nav.dashboard": "डैशबोर्ड",
  "nav.centers": "संग्रह केंद्र",
  "nav.suppliers": "आपूर्तिकर्ता",
  "nav.transactions": "लेन-देन",
  "nav.customers": "ग्राहक",
  "nav.deliveries": "वितरण",
  "nav.billing": "बिलिंग",
  "nav.receivables": "बकाया राशि",
  "nav.rateCards": "दर कार्ड",
  "nav.matrices": "मैट्रिक्स",
  "nav.playground": "परीक्षण क्षेत्र",
  "nav.settlements": "निपटान",
  "nav.payments": "भुगतान",
  "nav.receipts": "रसीदें",
  "nav.reports": "रिपोर्ट",
  "nav.notifications": "सूचनाएँ",
  "nav.sync": "समन्वयन",
  "nav.users": "उपयोगकर्ता",
  "nav.roles": "भूमिकाएँ",
  "nav.organizations": "संगठन",
  "nav.audit": "अंकेक्षण",
  "nav.configuration": "कॉन्फ़िगरेशन",
  "nav.settings": "सेटिंग्स",

  // --- dashboard ------------------------------------------------------------
  "dashboard.title": "डैशबोर्ड",
  "dashboard.procurement": "खरीद",
  "dashboard.sales": "बिक्री",
  "dashboard.today": "आज",
  "dashboard.thisMonth": "इस महीने",
  "dashboard.collected": "एकत्रित",
  "dashboard.delivered": "वितरित",
  "dashboard.outstanding": "बकाया",
  "dashboard.needsAttention": "ध्यान देने योग्य",

  // --- entities -------------------------------------------------------------
  "entity.customer": "ग्राहक",
  "entity.supplier": "आपूर्तिकर्ता",
  "entity.center": "संग्रह केंद्र",
  "entity.delivery": "वितरण",
  "entity.invoice": "बिल",
  "entity.payment": "भुगतान",
  "entity.receipt": "रसीद",
  "entity.settlement": "निपटान",
  "entity.user": "उपयोगकर्ता",
  "entity.role": "भूमिका",

  // --- fields ---------------------------------------------------------------
  "field.name": "नाम",
  "field.code": "कोड",
  "field.phone": "फ़ोन",
  "field.address": "पता",
  "field.status": "स्थिति",
  "field.date": "दिनांक",
  "field.quantity": "मात्रा",
  "field.amount": "राशि",
  "field.unitPrice": "इकाई मूल्य",
  "field.currency": "मुद्रा",
  "field.total": "कुल",
  "field.paid": "भुगतान किया",
  "field.balance": "शेष",
  "field.period": "अवधि",
  "field.language": "भाषा",
  "field.timezone": "समय क्षेत्र",
  "field.country": "देश",

  // --- states ---------------------------------------------------------------
  "state.loading": "लोड हो रहा है…",
  "state.empty": "अभी दिखाने के लिए कुछ नहीं",
  "state.error": "कुछ गड़बड़ हो गई",
  "state.unreachable": "प्लेटफ़ॉर्म तक नहीं पहुँच सके",
  "state.noPermission": "आपको यह देखने की अनुमति नहीं है",

  // --- validation -----------------------------------------------------------
  "validation.required": "यह फ़ील्ड आवश्यक है",
  "validation.invalid": "यह मान मान्य नहीं है",
  "validation.tooLong": "यह मान बहुत लंबा है",
  "validation.mustBeNumber": "संख्या दर्ज करें",

  // --- organization settings ------------------------------------------------
  "settings.title": "संगठन सेटिंग्स",
  "settings.locale": "देश और भाषा",
  "settings.localeHelp":
    "ये तय करते हैं कि आपका पैसा किस मुद्रा में गिना जाए, आपका कार्यदिवस कब शुरू हो, और आपके लोग किन भाषाओं में काम कर सकें।",
  "settings.country": "देश",
  "settings.currency": "मुद्रा",
  "settings.timezone": "समय क्षेत्र",
  "settings.defaultLanguage": "डिफ़ॉल्ट भाषा",
  "settings.supportedLanguages": "आपके संगठन द्वारा सक्षम भाषाएँ",
  "settings.myLanguage": "मेरी भाषा",
  "settings.myLanguageHelp": "यह केवल आपको दिखता है। किसी और के लिए कुछ नहीं बदलता।",
  "settings.saved": "सहेजा गया",
  "settings.countryFixed": "देश संगठन बनाते समय तय होता है और यहाँ नहीं बदला जाता।",
};

export const CATALOGS: Record<string, Catalog> = { en, hi };

/** Every key English defines. The test that keeps catalogs honest reads this. */
export const KEYS = Object.keys(en);
