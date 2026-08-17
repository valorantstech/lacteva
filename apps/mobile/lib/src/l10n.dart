/// Words, money and dates for the field app (DEMO-013 §13).
///
/// **No configuration of its own.** There is no map from India to rupees in
/// this file. The platform resolved that when the dairy was onboarded and
/// sends it with the session; a second copy here would be a second answer, and
/// the two would disagree the first time somebody changed a setting.
///
/// **No `flutter_localizations` codegen.** The standard stack solves problems
/// this app does not have — locale-resolved asset bundles, plural rule
/// engines, a `.arb` toolchain — and would add a build step to render a few
/// dozen short strings. This is a map and a lookup, deliberately the same
/// shape as the portal's, so a translator sees one vocabulary rather than two.
///
/// **The rule that matters more than the mechanism:** strings are fetched by
/// KEY. Nothing here or anywhere in the app asks what country it is in.
library;

import 'package:flutter/widgets.dart';

import 'session.dart';

typedef Catalog = Map<String, String>;

const Catalog _en = {
  'driver.title': "Today's route",
  'driver.start': 'Start run',
  'driver.complete': 'Complete run',
  'driver.record': 'Record',
  'driver.remaining': '{count} stops remaining',
  'driver.pending': '{count} waiting to sync',
  'driver.sync': 'Sync now',
  'driver.needsSignal': 'Starting or completing a run needs a connection.',
  'driver.notLinked': 'Not set up as a driver yet',
  'driver.notLinkedDetail':
      'Your login exists, but no driver profile is linked to it. Ask the dairy office.',
  'driver.noRun': 'No run assigned today',
  'driver.noRunDetail': 'When the office assigns you a run, it appears here.',
  'driver.skippedDefaultNote': 'skipped at the gate',
  'driver.outcome.delivered': 'Delivered',
  'driver.outcome.skipped': 'Skipped',
  'driver.outcome.returned': 'Returned',
  'driver.outcome.cancelled': 'Cancelled',
  'round.title': "Today's round",
  'round.empty': 'No customers on this round',
  'round.emptyDetail': 'Customers appear here once the dairy registers them.',
  'round.delivered': 'Delivered',
  'round.customers': 'Customers',
  'round.quantity': 'Quantity',
  'round.value': 'Value',
  'round.notRecorded': 'not yet recorded',
  // DEMO-016: a generated round arrives as `scheduled`. The API sends the
  // status CODE; the catalog decides the word, like everything else here.
  'status.scheduled': 'scheduled',
  'status.delivered': 'delivered',
  'status.skipped': 'not delivered',
  'status.returned': 'returned',
  'status.cancelled': 'cancelled',
  'round.allSent': 'All deliveries sent',
  'round.waiting': '{count} waiting to send',
  'round.sync': 'Send now',
  'round.refresh': 'Refresh',

  'slot.morning': 'Morning',
  'slot.evening': 'Evening',
  'record.title': 'Delivery',
  'record.recorded': 'Recorded',
  'record.delivered': 'DELIVERED',
  'record.notDelivered': 'NOT DELIVERED',
  'record.returned': 'RETURNED',
  'record.quantityHint': 'Quantity (leave blank for the standing order)',
  'record.amountNote':
      'The amount is calculated by the platform from the agreed rate — it is never entered here.',
  'record.queued': 'Saved on this phone. It will be sent when there is signal.',

  'customer.today': 'Today',
  'customer.noDeliveryToday': 'No delivery recorded yet today.',
  'customer.owe': 'What I owe',
  'customer.billed': 'Billed {billed} · paid {paid}',
  'customer.thisMonth': 'This month',
  'customer.deliveries': '{count} deliveries',
  'customer.bills': 'My bills',
  'customer.receipts': 'My receipts',
  'customer.noReceipts': 'A receipt appears here after each payment.',
  'customer.history': 'Delivery history',
  'customer.bill': 'Bill',
  'customer.amountDue': 'Amount due',
  'customer.paid': 'Paid',
  'customer.outstanding': 'Outstanding',
  'customer.subtotal': 'Subtotal',
  'customer.adjustments': 'Adjustments',
  'customer.broughtForward': 'Brought forward',
  'customer.everyDelivery': 'Every delivery on this bill',
  'customer.checked':
      'Checked by the dairy: this bill matches the deliveries below.',
  'customer.mismatch':
      'This bill no longer matches its deliveries. Contact the dairy.',

  'auth.signIn': 'Sign in',
  'auth.email': 'Email',
  'auth.password': 'Password',
  'auth.signingIn': 'Signing in…',

  'common.retry': 'Try again',
  'common.loading': 'Loading…',
  'common.offline': 'No signal',
  'common.nothingHere': 'Nothing for this account on mobile',
};

const Catalog _hi = {
  'driver.title': 'आज का रूट',
  'driver.start': 'रन शुरू करें',
  'driver.complete': 'रन पूरा करें',
  'driver.record': 'दर्ज करें',
  'driver.remaining': '{count} स्टॉप बाक़ी',
  'driver.pending': '{count} सिंक के लिए प्रतीक्षा में',
  'driver.sync': 'अभी सिंक करें',
  'driver.needsSignal': 'रन शुरू या पूरा करने के लिए कनेक्शन चाहिए।',
  'driver.notLinked': 'अभी ड्राइवर के रूप में सेट नहीं',
  'driver.notLinkedDetail':
      'आपका लॉगिन मौजूद है, पर कोई ड्राइवर प्रोफ़ाइल जुड़ी नहीं है। डेयरी कार्यालय से कहें।',
  'driver.noRun': 'आज कोई रन नहीं मिला',
  'driver.noRunDetail': 'कार्यालय के रन सौंपते ही वह यहाँ दिखेगा।',
  'driver.skippedDefaultNote': 'गेट पर छोड़ा गया',
  'driver.outcome.delivered': 'डिलीवर हुआ',
  'driver.outcome.skipped': 'छोड़ा गया',
  'driver.outcome.returned': 'वापस आया',
  'driver.outcome.cancelled': 'रद्द',
  'round.title': 'आज का राउंड',
  'round.empty': 'इस राउंड में कोई ग्राहक नहीं',
  'round.emptyDetail': 'डेयरी द्वारा पंजीकृत होने पर ग्राहक यहाँ दिखेंगे।',
  'round.delivered': 'वितरित',
  'round.customers': 'ग्राहक',
  'round.quantity': 'मात्रा',
  'round.value': 'मूल्य',
  'round.notRecorded': 'अभी दर्ज नहीं',
  'status.scheduled': 'निर्धारित',
  'status.delivered': 'वितरित',
  'status.skipped': 'वितरित नहीं',
  'status.returned': 'वापस',
  'status.cancelled': 'रद्द',
  'round.allSent': 'सभी वितरण भेजे गए',
  'round.waiting': '{count} भेजने के लिए शेष',
  'round.sync': 'अभी भेजें',
  'round.refresh': 'ताज़ा करें',

  'slot.morning': 'सुबह',
  'slot.evening': 'शाम',
  'record.title': 'वितरण',
  'record.recorded': 'दर्ज किया गया',
  'record.delivered': 'वितरित',
  'record.notDelivered': 'वितरित नहीं',
  'record.returned': 'वापस',
  'record.quantityHint': 'मात्रा (नियमित आदेश हेतु खाली छोड़ें)',
  'record.amountNote':
      'राशि की गणना प्लेटफ़ॉर्म तय दर से करता है — यहाँ कभी दर्ज नहीं की जाती।',
  'record.queued': 'इस फ़ोन में सहेजा गया। सिग्नल मिलने पर भेजा जाएगा।',

  'customer.today': 'आज',
  'customer.noDeliveryToday': 'आज अभी कोई वितरण दर्ज नहीं हुआ।',
  'customer.owe': 'मुझ पर बकाया',
  'customer.billed': 'बिल {billed} · भुगतान {paid}',
  'customer.thisMonth': 'इस महीने',
  'customer.deliveries': '{count} वितरण',
  'customer.bills': 'मेरे बिल',
  'customer.receipts': 'मेरी रसीदें',
  'customer.noReceipts': 'प्रत्येक भुगतान के बाद रसीद यहाँ दिखेगी।',
  'customer.history': 'वितरण इतिहास',
  'customer.bill': 'बिल',
  'customer.amountDue': 'देय राशि',
  'customer.paid': 'भुगतान किया',
  'customer.outstanding': 'बकाया',
  'customer.subtotal': 'उप-योग',
  'customer.adjustments': 'समायोजन',
  'customer.broughtForward': 'पिछला शेष',
  'customer.everyDelivery': 'इस बिल का प्रत्येक वितरण',
  'customer.checked':
      'डेयरी द्वारा जाँचा गया: यह बिल नीचे के वितरणों से मेल खाता है।',
  'customer.mismatch':
      'यह बिल अब अपने वितरणों से मेल नहीं खाता। डेयरी से संपर्क करें।',

  'auth.signIn': 'साइन इन करें',
  'auth.email': 'ईमेल',
  'auth.password': 'पासवर्ड',
  'auth.signingIn': 'साइन इन हो रहा है…',

  'common.retry': 'पुनः प्रयास करें',
  'common.loading': 'लोड हो रहा है…',
  'common.offline': 'सिग्नल नहीं',
  'common.nothingHere': 'इस खाते के लिए मोबाइल पर कुछ नहीं',
};

const Catalog _ar = {
  'driver.title': 'مسار اليوم',
  'driver.start': 'بدء الجولة',
  'driver.complete': 'إنهاء الجولة',
  'driver.record': 'تسجيل',
  'driver.remaining': '{count} محطات متبقية',
  'driver.pending': '{count} بانتظار المزامنة',
  'driver.sync': 'مزامنة الآن',
  'driver.needsSignal': 'بدء الجولة أو إنهاؤها يحتاج اتصالاً.',
  'driver.notLinked': 'لست معدًّا كسائق بعد',
  'driver.notLinkedDetail':
      'حسابك موجود، لكن لا يوجد ملف سائق مرتبط به. راجع مكتب الألبان.',
  'driver.noRun': 'لا توجد جولة اليوم',
  'driver.noRunDetail': 'عندما يسند المكتب جولة إليك ستظهر هنا.',
  'driver.skippedDefaultNote': 'تخطٍّ عند البوابة',
  'driver.outcome.delivered': 'تم التسليم',
  'driver.outcome.skipped': 'تم التخطي',
  'driver.outcome.returned': 'أُرجع',
  'driver.outcome.cancelled': 'أُلغي',
  'round.title': 'جولة اليوم',
  'round.empty': 'لا يوجد عملاء في هذه الجولة',
  'round.emptyDetail': 'يظهر العملاء هنا بمجرد أن تسجّلهم الألبان.',
  'round.delivered': 'مُسلَّم',
  'round.customers': 'العملاء',
  'round.quantity': 'الكمية',
  'round.value': 'القيمة',
  'round.notRecorded': 'لم يُسجَّل بعد',
  'status.scheduled': 'مجدول',
  'status.delivered': 'مُسلَّم',
  'status.skipped': 'غير مُسلَّم',
  'status.returned': 'مُرتجع',
  'status.cancelled': 'ملغى',
  'round.allSent': 'أُرسلت كل التوصيلات',
  'round.waiting': '{count} بانتظار الإرسال',
  'round.sync': 'أرسل الآن',
  'round.refresh': 'تحديث',

  'slot.morning': 'صباحًا',
  'slot.evening': 'مساءً',
  'record.title': 'تسليم',
  'record.recorded': 'تم التسجيل',
  'record.delivered': 'مُسلَّم',
  'record.notDelivered': 'غير مُسلَّم',
  'record.returned': 'مُرتجع',
  'record.quantityHint': 'الكمية (اتركها فارغة للطلب الدائم)',
  'record.amountNote':
      'تحسب المنصّة المبلغ من السعر المتفق عليه — ولا يُدخل هنا أبدًا.',
  'record.queued': 'حُفظ على هذا الهاتف. سيُرسل عند توفّر الشبكة.',

  'customer.today': 'اليوم',
  'customer.noDeliveryToday': 'لم يُسجَّل أي توصيل اليوم بعد.',
  'customer.owe': 'ما عليّ',
  'customer.billed': 'الفاتورة {billed} · المدفوع {paid}',
  'customer.thisMonth': 'هذا الشهر',
  'customer.deliveries': '{count} توصيلة',
  'customer.bills': 'فواتيري',
  'customer.receipts': 'إيصالاتي',
  'customer.noReceipts': 'يظهر الإيصال هنا بعد كل دفعة.',
  'customer.history': 'سجل التوصيلات',
  'customer.bill': 'فاتورة',
  'customer.amountDue': 'المبلغ المستحق',
  'customer.paid': 'المدفوع',
  'customer.outstanding': 'المتبقّي',
  'customer.subtotal': 'المجموع الفرعي',
  'customer.adjustments': 'التسويات',
  'customer.broughtForward': 'الرصيد السابق',
  'customer.everyDelivery': 'كل توصيلة في هذه الفاتورة',
  'customer.checked':
      'تم التحقق من قِبل الألبان: هذه الفاتورة تطابق التوصيلات أدناه.',
  'customer.mismatch': 'لم تعد هذه الفاتورة تطابق توصيلاتها. تواصل مع الألبان.',

  'auth.signIn': 'تسجيل الدخول',
  'auth.email': 'البريد الإلكتروني',
  'auth.password': 'كلمة المرور',
  'auth.signingIn': 'جارٍ تسجيل الدخول…',

  'common.retry': 'إعادة المحاولة',
  'common.loading': 'جارٍ التحميل…',
  'common.offline': 'لا توجد شبكة',
  'common.nothingHere': 'لا يوجد شيء لهذا الحساب على الجوال',
};

const Map<String, Catalog> catalogs = {'en': _en, 'hi': _hi, 'ar': _ar};

/// `hi-IN` → `hi`. The catalog key for a BCP-47 tag: the region carries the
/// money and the clock, which live on the organization, not in the words.
String baseLanguage(String? tag) =>
    (tag ?? 'en').split('-').first.toLowerCase();

/// Look a string up for a session, falling back language → English → the key.
///
/// A missing translation shows an English sentence, which a rider can act on.
/// A missing key shows the key, which an engineer can grep for. Neither is a
/// blank space on a phone at 5 a.m.
class L10n {
  const L10n(this.language);

  factory L10n.of(Session? session) => L10n(baseLanguage(session?.locale));

  final String language;

  String t(String key, [Map<String, Object?> vars = const {}]) {
    final catalog = catalogs[language] ?? _en;
    var text = catalog[key] ?? _en[key] ?? key;
    vars.forEach((name, value) {
      text = text.replaceAll('{$name}', '${value ?? ''}');
    });
    return text;
  }
}

/// Dates, and why this file has no timezone arithmetic (DEMO-014 §9).
///
/// A handset cannot convert to an arbitrary IANA zone without shipping a
/// timezone database, and its own clock is not the dairy's — a rider who has
/// crossed a border, or a phone left on the wrong setting, must not move a
/// business day.
///
/// So the app performs NO conversion. Every date it displays is a business
/// date the platform already computed in the organization's clock
/// (`core/business_time.py`) and sent as a plain `YYYY-MM-DD` string, and the
/// app renders it verbatim. `delivery_date`, the report's echoed `date_from`,
/// an invoice period: all of them arrive correct and leave untouched.
///
/// `organization.timezone` is carried on the session for one purpose — so a
/// screen can TELL a person which clock they are looking at — and never to
/// compute with.
String businessDate(String? isoDate) => (isoDate ?? '').trim();

/// The clock this person's dairy runs on, for a screen that wants to say so.
String businessClock(Session? session) =>
    session?.organization?.timezone ?? 'UTC';

/// Languages written right to left (DEMO-014 §7).
///
/// A layout fact rather than a translation one, which is why it sits beside
/// the catalogs: Flutter's `Directionality` takes it, and the whole app flips
/// from one value instead of from a conditional per screen.
const Set<String> rtlLanguages = {'ar', 'fa', 'he', 'ur'};

bool isRtl(String? tag) => rtlLanguages.contains(baseLanguage(tag));

/// The text direction for a session's language.
TextDirection directionFor(Session? session) =>
    isRtl(session?.locale) ? TextDirection.rtl : TextDirection.ltr;

/// Money as the ORGANIZATION counts it.
///
/// The amount arrives as an exact decimal STRING and leaves as one: no
/// `double.parse`, no arithmetic. The symbol and code come from the session,
/// so an Indian dairy shows ₹ and a Kenyan one KSh without this function
/// knowing either country exists.
String money(String? amount, Session? session, {bool symbol = true}) {
  if (amount == null || amount.isEmpty) return '—';
  final org = session?.organization;
  if (org == null) return amount;
  return symbol && org.currencySymbol.isNotEmpty
      ? '${org.currencySymbol}$amount'
      : '$amount ${org.currencyCode}';
}
