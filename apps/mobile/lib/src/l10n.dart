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
  // LACTEVA-ADMIN-003. A locked-out operator during a pilot is a support
  // call; step 1 says the same words whatever happened, because any other
  // pair of answers reveals whether an account exists.
  'auth.forgotPassword': 'Forgot password?',
  'auth.resetTitle': 'Reset your password',
  'auth.resetSendCode': 'Send reset code',
  'auth.resetSent':
      'If an account exists for {email}, a reset code has been sent.',
  'auth.resetCode': 'Reset code',
  'auth.resetNewPassword': 'New password',
  'auth.resetMinLength': 'At least 10 characters.',
  'auth.resetSubmit': 'Set new password',
  'auth.resetTooMany': 'Too many attempts — try again later.',
  'auth.resetDone': 'Your password was updated — sign in to continue.',

  'common.retry': 'Try again',
  'common.loading': 'Loading…',
  'common.offline': 'No signal',
  'common.nothingHere': 'Nothing for this account on mobile',
  'common.signOut': 'Sign out',

  // P1-LOCALE-I18N-001 — the operator surfaces.
  'common.couldNotReach': 'Could not reach the platform',
  'common.previous': 'Previous',
  'common.next': 'Next',
  'common.save': 'Save',
  'common.saving': 'Saving…',
  'common.done': 'Done',
  'common.edit': 'Edit',
  'common.required': 'Required',
  'common.nameTooShort': 'Name needs at least 2 characters',
  'common.activate': 'Activate',

  // Milk type LABELS for the wizard dropdown; the VALUE sent to the API stays
  // the raw code. Words match the platform's own parchi vocabulary
  // (_SLIP_MILK_HI in milk_collection/service.py).
  'milk.cow': 'cow',
  'milk.buffalo': 'buffalo',
  'milk.goat': 'goat',
  'milk.mixed': 'mixed',

  'login.queuedSafe':
      '{count} captured record(s) are safe on this phone and will sync after '
      'you sign in.',

  'wizard.stepTitle': 'Collection — step {n} of 6',
  'wizard.supplier': 'Supplier',
  'wizard.supplierCode': 'Supplier code',
  'wizard.supplierCodeHelp': 'QR scanning arrives with device integration',
  'wizard.identify': 'Identify supplier',
  'wizard.milk': 'Milk',
  'wizard.milkType': 'Milk type',
  'wizard.containerType': 'Container type',
  'wizard.containerId': 'Container identifier',
  'wizard.receiveMilk': 'Receive milk',
  'wizard.weight': 'Weight',
  'wizard.grossKg': 'Gross (kg)',
  'wizard.tareKg': 'Tare (kg)',
  'wizard.captureWeight': 'Capture weight',
  'wizard.mockScale': 'Use mock scale',
  'wizard.quality': 'Quality',
  'wizard.fatLabel': 'FAT %',
  'wizard.snfLabel': 'SNF %',
  'wizard.clrLabel': 'CLR',
  'wizard.captureQuality': 'Capture quality',
  'wizard.mockAnalyzer': 'Use mock analyzer',
  'wizard.review': 'Review',
  'wizard.netWeightLine': 'Net weight: {kg} kg',
  'wizard.qualityLine': 'FAT {fat} · SNF {snf} · CLR {clr}',
  'wizard.pricingLine': 'Pricing: {status}',
  'wizard.acceptComplete': 'Accept & complete',
  'wizard.reject': 'Reject…',
  'wizard.rejectReason': 'Rejection reason',
  'wizard.rejectReasonHelp':
      'The farmer reads this on the parchi — say what was actually wrong '
      '(sour, adulterated, smell…)',
  'wizard.rejectComplete': 'Reject & complete',
  'wizard.keepReviewing': 'Keep reviewing',
  'wizard.rejectWhy':
      'Say why the milk is rejected — it prints on the parchi',
  'wizard.savedQueued': 'Saved on this phone — queued to sync',
  'wizard.txState': 'Transaction {state}',
  'wizard.netLine': 'Net {kg} kg',
  'wizard.rejectedLine': 'Rejected: {reason}',
  'wizard.payable': 'Payable: {amount} {currency}',
  'wizard.nextSettlement': 'Will appear in the next supplier settlement.',
  'wizard.parchiQueued':
      'The parchi is issued when this phone syncs — the slip number comes '
      'from the platform, and this device will not invent one.',
  'wizard.parchi': 'Parchi {number}',
  'wizard.copyParchi': 'Copy parchi text',
  'wizard.getParchi': 'Get parchi',
  'wizard.fetchingParchi': 'Fetching parchi…',
  'wizard.parchiCopied': 'Parchi copied',

  'center.listTitle': 'Collection centers',
  'center.new': 'New center',
  'center.searchHint': 'Search by name or code',
  'center.noneMatch': 'No centers match.',
  'center.rateCards': 'Rate cards',
  'center.settlements': 'Settlements',
  'center.payments': 'Payments',
  'center.receipts': 'Receipts',
  'center.notifications': 'Notifications',
  'center.editTitle': 'Edit {code}',
  'center.newTitle': 'New collection center',
  'center.branch': 'Branch',
  'center.selectBranch': 'Select a branch',
  'center.name': 'Name',
  'center.code': 'Code',
  'center.codeHelp': 'Unique within your organization, e.g. KH-C1',
  'center.codeRequired': 'Code is required',
  'center.timezone': 'Timezone',
  'center.fallback': 'Center',
  'center.collections': 'Collections',
  'center.closeSession': 'Close session',
  'center.collectMilk': 'Collect milk',
  'center.todaySummary': "Today's summary",
  'center.pricingTest': 'Pricing resolution test',
  'center.noOpenSession': 'No open session at this centre',
  'center.closeSessionTitle': 'Close the session?',
  'center.closeSessionBody':
      'Closing "{label}" ends this shift at the centre. Collections already '
      'captured are unaffected; a new shift opens a new session.',
  'center.keepOpen': 'Keep it open',
  'center.sessionClosed': 'Session closed',
  'center.deactivate': 'Deactivate',
  'center.maintenance': 'Maintenance',
  'center.hours': 'Operating hours',
  'center.noHours':
      'No operating hours set — the center cannot be activated yet.',
  'center.calendar': 'Business calendar',
  'center.noEntries': 'No entries.',
  'center.orgTimezone': 'org timezone',

  'readiness.title': 'Operational readiness',
  'readiness.checksPassing': '{passed} of {total} checks passing',

  'history.title': 'Collections — {center}',
  'history.empty': 'No collections recorded at this centre yet.',
  'history.loadMore': 'Load more ({n} of {total})',
  'history.fallback': 'Collection',
  'history.state': 'State: {state}',
  'history.milk': 'Milk: {milk}',
  'history.net': 'Net: {kg} kg',
  'history.amount': 'Amount: {amount} {currency}',

  'today.title': "Today's collection",
  'today.milkCollected': 'Milk collected',
  'today.payable': 'Payable',
  'today.acceptedRejected': 'Accepted / Rejected',
  'today.suppliersServed': 'Suppliers served',
  'today.avgFat': 'Avg FAT',
  'today.avgSnf': 'Avg SNF',
  'today.unpriced': '{n} accepted without pricing',
  'today.checkRateCard': 'Check the rate card for this center.',
  'today.footer': 'Pull to refresh · full reports in the admin portal',

  'sync.title': 'Sync',
  'sync.offlineSaved':
      'Offline — collections are saved on this device ({count} waiting)',
  'sync.needAttention': '{count} item(s) need attention',
  'sync.syncingItems': 'Syncing {count} item(s)…',
  'sync.now': 'Sync now',
  'sync.online': 'Online',
  'sync.offline': 'Offline',
  'sync.lastSuccess': 'Last successful sync: {ago}',
  'sync.never': 'never',
  'sync.justNow': 'just now',
  'sync.minAgo': '{n} min ago',
  'sync.hAgo': '{n} h ago',
  'sync.dAgo': '{n} d ago',
  'sync.pending': 'Pending',
  'sync.synced': 'Synced',
  'sync.failed': 'Failed',
  'sync.conflicts': 'Conflicts',
  'sync.lastRun':
      'Last run: {applied} applied, {duplicates} already there, '
      '{conflicts} conflict(s), {failed} failed',
  'sync.cancelledSafe': 'Cancelled — nothing was lost',
  'sync.retryFailed': 'Retry failed',
  'sync.cancel': 'Cancel',
  'sync.needsAttention': 'Needs attention ({n})',
  'sync.queue': 'Queue ({n})',
  'sync.nothingCaptured': 'Nothing captured yet.',
  'sync.attempt': ' · attempt {n}',
  'sync.captured': 'Captured',
  'sync.operation': 'Operation',
  'sync.recordedAs': 'Recorded on the platform as',
  'sync.resolveWithSupervisor':
      'This item was not applied silently. Resolve it with your supervisor '
      'in the portal — the captured data stays on this device until then.',

  // The queue's operation kinds — codes stay keys, words come from here.
  'queue.kind.open_session': 'Open collection session',
  'queue.kind.close_session': 'Close collection session',
  'queue.kind.create_transaction': 'Start collection',
  'queue.kind.identify_supplier': 'Identify supplier',
  'queue.kind.receive_milk': 'Receive milk',
  'queue.kind.capture_weight': 'Capture weight',
  'queue.kind.capture_quality': 'Capture quality',
  'queue.kind.accept': 'Accept milk',
  'queue.kind.reject': 'Reject milk',
  'queue.kind.complete': 'Complete collection',
  'queue.kind.cancel': 'Cancel collection',

  'conflict.already_accepted': 'Already recorded on the platform',
  'conflict.supplier_unavailable': 'Supplier is no longer active',
  'conflict.session_closed': 'The collection session was closed',
  'conflict.rate_card_changed':
      'Prices changed — the collection was kept, the amount differs',
  'conflict.unresolved_reference': 'Waiting for an earlier step to sync',
  'conflict.invalid_state': 'The platform refused this step',
  'conflict.other': 'Needs attention',

  'supplier.title': 'Suppliers',
  'supplier.new': 'New supplier',
  'supplier.searchHint': 'Search name, code, or phone',
  'supplier.noneMatch': 'No suppliers match.',
  'supplier.editTitle': 'Edit {code}',
  'supplier.fullName': 'Full name',
  'supplier.phone': 'Phone',
  'supplier.village': 'Village',
  'supplier.fallback': 'Supplier',
  'supplier.suspend': 'Suspend',
  'supplier.centersAssigned': '{n} collection center(s) assigned',

  'home.nothingDetail':
      'Signed in as {email}. This app covers milk collection, the delivery '
      'round, and a customer\'s own account. Everything else is in the web '
      'portal.',
  'home.sessionUnclear':
      'Signed in, but the platform could not say what you may do. '
      'Check the connection and try again.',

  'customer.myDairy': 'My dairy',
  'customer.couldNotReachDairy':
      'Could not reach the dairy. Showing nothing rather than something out '
      'of date.',
  'customer.noBill': 'No bill has been issued yet.',
  'customer.noDeliveries': 'No deliveries recorded yet.',
  'customer.unbilled': '{n} delivery(s) not yet on a bill ({amount})',
  'customer.deliveriesLabel': 'Deliveries',
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
  'auth.forgotPassword': 'पासवर्ड भूल गए?',
  'auth.resetTitle': 'अपना पासवर्ड रीसेट करें',
  'auth.resetSendCode': 'रीसेट कोड भेजें',
  'auth.resetSent':
      'यदि {email} के लिए खाता मौजूद है, तो रीसेट कोड भेज दिया गया है।',
  'auth.resetCode': 'रीसेट कोड',
  'auth.resetNewPassword': 'नया पासवर्ड',
  'auth.resetMinLength': 'कम से कम 10 अक्षर।',
  'auth.resetSubmit': 'नया पासवर्ड सेट करें',
  'auth.resetTooMany': 'बहुत अधिक प्रयास — बाद में पुनः प्रयास करें।',
  'auth.resetDone': 'आपका पासवर्ड बदल दिया गया — जारी रखने के लिए साइन इन करें।',

  'common.retry': 'पुनः प्रयास करें',
  'common.loading': 'लोड हो रहा है…',
  'common.offline': 'सिग्नल नहीं',
  'common.nothingHere': 'इस खाते के लिए मोबाइल पर कुछ नहीं',
  'common.signOut': 'साइन आउट',

  // P1-LOCALE-I18N-001 — the operator surfaces.
  'common.couldNotReach': 'प्लेटफ़ॉर्म से संपर्क नहीं हो सका',
  'common.previous': 'पिछला',
  'common.next': 'अगला',
  'common.save': 'सहेजें',
  'common.saving': 'सहेजा जा रहा है…',
  'common.done': 'हो गया',
  'common.edit': 'संपादित करें',
  'common.required': 'आवश्यक',
  'common.nameTooShort': 'नाम में कम से कम 2 अक्षर चाहिए',
  'common.activate': 'सक्रिय करें',

  // Vocabulary from the platform's parchi (_SLIP_MILK_HI).
  'milk.cow': 'गाय',
  'milk.buffalo': 'भैंस',
  'milk.goat': 'बकरी',
  'milk.mixed': 'मिश्रित',

  'login.queuedSafe':
      '{count} दर्ज रिकॉर्ड इस फ़ोन में सुरक्षित हैं और साइन इन के बाद सिंक होंगे।',

  'wizard.stepTitle': 'संग्रह — 6 में से चरण {n}',
  'wizard.supplier': 'आपूर्तिकर्ता',
  'wizard.supplierCode': 'आपूर्तिकर्ता कोड',
  'wizard.supplierCodeHelp': 'QR स्कैनिंग डिवाइस एकीकरण के साथ आएगी',
  'wizard.identify': 'आपूर्तिकर्ता पहचानें',
  'wizard.milk': 'दूध',
  'wizard.milkType': 'दूध का प्रकार',
  'wizard.containerType': 'कंटेनर प्रकार',
  'wizard.containerId': 'कंटेनर पहचान',
  'wizard.receiveMilk': 'दूध प्राप्त करें',
  'wizard.weight': 'वज़न',
  'wizard.grossKg': 'सकल वज़न (kg)',
  'wizard.tareKg': 'खाली वज़न (kg)',
  'wizard.captureWeight': 'वज़न दर्ज करें',
  'wizard.mockScale': 'मॉक तराज़ू उपयोग करें',
  'wizard.quality': 'गुणवत्ता',
  'wizard.fatLabel': 'FAT %',
  'wizard.snfLabel': 'SNF %',
  'wizard.clrLabel': 'CLR',
  'wizard.captureQuality': 'गुणवत्ता दर्ज करें',
  'wizard.mockAnalyzer': 'मॉक विश्लेषक उपयोग करें',
  'wizard.review': 'समीक्षा',
  'wizard.netWeightLine': 'शुद्ध वज़न: {kg} kg',
  'wizard.qualityLine': 'FAT {fat} · SNF {snf} · CLR {clr}',
  'wizard.pricingLine': 'मूल्य निर्धारण: {status}',
  'wizard.acceptComplete': 'स्वीकारें और पूरा करें',
  'wizard.reject': 'अस्वीकार…',
  'wizard.rejectReason': 'अस्वीकृति का कारण',
  'wizard.rejectReasonHelp':
      'किसान इसे पर्ची पर पढ़ेगा — जो वास्तव में गलत था वही लिखें '
      '(खट्टा, मिलावट, गंध…)',
  'wizard.rejectComplete': 'अस्वीकार कर पूरा करें',
  'wizard.keepReviewing': 'समीक्षा जारी रखें',
  'wizard.rejectWhy': 'बताएँ दूध क्यों अस्वीकृत है — यह पर्ची पर छपता है',
  'wizard.savedQueued': 'इस फ़ोन में सहेजा गया — सिंक के लिए कतार में',
  'wizard.txState': 'लेन-देन {state}',
  'wizard.netLine': 'शुद्ध {kg} kg',
  'wizard.rejectedLine': 'अस्वीकृत: {reason}',
  'wizard.payable': 'देय: {amount} {currency}',
  // TO CONFIRM (P1-LOCALE-I18N-001): settlement wording is financial — kept
  // English verbatim until the dairy's own words are confirmed.
  'wizard.nextSettlement': 'Will appear in the next supplier settlement.',
  'wizard.parchiQueued':
      'पर्ची इस फ़ोन के सिंक होने पर जारी होती है — पर्ची संख्या प्लेटफ़ॉर्म '
      'देता है, यह डिवाइस उसे नहीं गढ़ेगा।',
  'wizard.parchi': 'पर्ची {number}',
  'wizard.copyParchi': 'पर्ची पाठ कॉपी करें',
  'wizard.getParchi': 'पर्ची प्राप्त करें',
  'wizard.fetchingParchi': 'पर्ची लाई जा रही है…',
  'wizard.parchiCopied': 'पर्ची कॉपी हुई',

  'center.listTitle': 'संग्रह केंद्र',
  'center.new': 'नया केंद्र',
  'center.searchHint': 'नाम या कोड से खोजें',
  'center.noneMatch': 'कोई केंद्र मेल नहीं खाता।',
  'center.rateCards': 'दर कार्ड',
  'center.settlements': 'निपटान',
  'center.payments': 'भुगतान',
  'center.receipts': 'रसीदें',
  'center.notifications': 'सूचनाएँ',
  'center.editTitle': '{code} संपादित करें',
  'center.newTitle': 'नया संग्रह केंद्र',
  'center.branch': 'शाखा',
  'center.selectBranch': 'शाखा चुनें',
  'center.name': 'नाम',
  'center.code': 'कोड',
  'center.codeHelp': 'आपके संगठन में अद्वितीय, जैसे KH-C1',
  'center.codeRequired': 'कोड आवश्यक है',
  'center.timezone': 'समय क्षेत्र',
  'center.fallback': 'केंद्र',
  'center.collections': 'संग्रह',
  'center.closeSession': 'सत्र बंद करें',
  'center.collectMilk': 'दूध संग्रह करें',
  'center.todaySummary': 'आज का सारांश',
  'center.pricingTest': 'मूल्य निर्धारण परीक्षण',
  'center.noOpenSession': 'इस केंद्र पर कोई खुला सत्र नहीं',
  'center.closeSessionTitle': 'सत्र बंद करें?',
  'center.closeSessionBody':
      '"{label}" बंद करने से केंद्र की यह पाली समाप्त होती है। पहले दर्ज '
      'संग्रह प्रभावित नहीं होते; नई पाली नया सत्र खोलती है।',
  'center.keepOpen': 'खुला रखें',
  'center.sessionClosed': 'सत्र बंद हुआ',
  'center.deactivate': 'निष्क्रिय करें',
  'center.maintenance': 'रखरखाव',
  'center.hours': 'संचालन समय',
  'center.noHours':
      'संचालन समय निर्धारित नहीं — केंद्र अभी सक्रिय नहीं किया जा सकता।',
  'center.calendar': 'व्यावसायिक कैलेंडर',
  'center.noEntries': 'कोई प्रविष्टि नहीं।',
  'center.orgTimezone': 'संगठन का समय क्षेत्र',

  'readiness.title': 'परिचालन तैयारी',
  'readiness.checksPassing': '{total} में से {passed} जाँच सफल',

  'history.title': 'संग्रह — {center}',
  'history.empty': 'इस केंद्र पर अभी कोई संग्रह दर्ज नहीं।',
  'history.loadMore': 'और देखें ({total} में से {n})',
  'history.fallback': 'संग्रह',
  'history.state': 'स्थिति: {state}',
  'history.milk': 'दूध: {milk}',
  'history.net': 'शुद्ध: {kg} kg',
  'history.amount': 'राशि: {amount} {currency}',

  'today.title': 'आज का संग्रह',
  'today.milkCollected': 'दूध एकत्र',
  'today.payable': 'देय',
  'today.acceptedRejected': 'स्वीकृत / अस्वीकृत',
  'today.suppliersServed': 'आपूर्तिकर्ता सेवित',
  'today.avgFat': 'औसत FAT',
  'today.avgSnf': 'औसत SNF',
  'today.unpriced': '{n} बिना मूल्य निर्धारण के स्वीकृत',
  'today.checkRateCard': 'इस केंद्र का दर कार्ड जाँचें।',
  'today.footer': 'ताज़ा करने के लिए खींचें · पूर्ण रिपोर्ट एडमिन पोर्टल में',

  'sync.title': 'सिंक',
  'sync.offlineSaved':
      'ऑफ़लाइन — संग्रह इस डिवाइस में सहेजे जा रहे हैं ({count} प्रतीक्षा में)',
  'sync.needAttention': '{count} मद पर ध्यान चाहिए',
  'sync.syncingItems': '{count} मद सिंक हो रहे हैं…',
  'sync.now': 'अभी सिंक करें',
  'sync.online': 'ऑनलाइन',
  'sync.offline': 'ऑफ़लाइन',
  'sync.lastSuccess': 'अंतिम सफल सिंक: {ago}',
  'sync.never': 'कभी नहीं',
  'sync.justNow': 'अभी-अभी',
  'sync.minAgo': '{n} मिनट पहले',
  'sync.hAgo': '{n} घंटे पहले',
  'sync.dAgo': '{n} दिन पहले',
  'sync.pending': 'लंबित',
  'sync.synced': 'सिंक हुआ',
  'sync.failed': 'विफल',
  'sync.conflicts': 'टकराव',
  'sync.lastRun':
      'अंतिम रन: {applied} लागू, {duplicates} पहले से मौजूद, '
      '{conflicts} टकराव, {failed} विफल',
  'sync.cancelledSafe': 'रद्द — कुछ भी नहीं खोया',
  'sync.retryFailed': 'विफल पुनः भेजें',
  'sync.cancel': 'रद्द करें',
  'sync.needsAttention': 'ध्यान चाहिए ({n})',
  'sync.queue': 'कतार ({n})',
  'sync.nothingCaptured': 'अभी कुछ दर्ज नहीं।',
  'sync.attempt': ' · प्रयास {n}',
  'sync.captured': 'दर्ज किया गया',
  'sync.operation': 'ऑपरेशन',
  'sync.recordedAs': 'प्लेटफ़ॉर्म पर इस रूप में दर्ज',
  'sync.resolveWithSupervisor':
      'यह मद चुपचाप लागू नहीं हुआ। इसे अपने पर्यवेक्षक के साथ पोर्टल में '
      'सुलझाएँ — दर्ज डेटा तब तक इस डिवाइस में रहेगा।',

  'queue.kind.open_session': 'संग्रह सत्र खोलें',
  'queue.kind.close_session': 'संग्रह सत्र बंद करें',
  'queue.kind.create_transaction': 'संग्रह शुरू करें',
  'queue.kind.identify_supplier': 'आपूर्तिकर्ता पहचानें',
  'queue.kind.receive_milk': 'दूध प्राप्त करें',
  'queue.kind.capture_weight': 'वज़न दर्ज करें',
  'queue.kind.capture_quality': 'गुणवत्ता दर्ज करें',
  'queue.kind.accept': 'दूध स्वीकारें',
  'queue.kind.reject': 'दूध अस्वीकारें',
  'queue.kind.complete': 'संग्रह पूरा करें',
  'queue.kind.cancel': 'संग्रह रद्द करें',

  'conflict.already_accepted': 'प्लेटफ़ॉर्म पर पहले से दर्ज',
  'conflict.supplier_unavailable': 'आपूर्तिकर्ता अब सक्रिय नहीं',
  'conflict.session_closed': 'संग्रह सत्र बंद हो चुका था',
  'conflict.rate_card_changed':
      'दरें बदल गईं — संग्रह रखा गया, राशि भिन्न है',
  'conflict.unresolved_reference': 'पहले के चरण के सिंक की प्रतीक्षा',
  'conflict.invalid_state': 'प्लेटफ़ॉर्म ने यह चरण अस्वीकार किया',
  'conflict.other': 'ध्यान चाहिए',

  'supplier.title': 'आपूर्तिकर्ता',
  'supplier.new': 'नया आपूर्तिकर्ता',
  'supplier.searchHint': 'नाम, कोड या फ़ोन से खोजें',
  'supplier.noneMatch': 'कोई आपूर्तिकर्ता मेल नहीं खाता।',
  'supplier.editTitle': '{code} संपादित करें',
  'supplier.fullName': 'पूरा नाम',
  'supplier.phone': 'फ़ोन',
  'supplier.village': 'गाँव',
  'supplier.fallback': 'आपूर्तिकर्ता',
  'supplier.suspend': 'निलंबित करें',
  'supplier.centersAssigned': '{n} संग्रह केंद्र आवंटित',

  'home.nothingDetail':
      '{email} के रूप में साइन इन। यह ऐप दूध संग्रह, वितरण राउंड और ग्राहक के '
      'अपने खाते के लिए है। बाकी सब वेब पोर्टल में है।',
  'home.sessionUnclear':
      'साइन इन हुआ, पर प्लेटफ़ॉर्म यह नहीं बता सका कि आप क्या कर सकते हैं। '
      'कनेक्शन जाँचें और पुनः प्रयास करें।',

  'customer.myDairy': 'मेरी डेयरी',
  'customer.couldNotReachDairy':
      'डेयरी से संपर्क नहीं हो सका। पुराना कुछ दिखाने की बजाय कुछ नहीं '
      'दिखाया जा रहा।',
  'customer.noBill': 'अभी कोई बिल जारी नहीं हुआ।',
  'customer.noDeliveries': 'अभी कोई वितरण दर्ज नहीं।',
  'customer.unbilled': '{n} वितरण अभी किसी बिल में नहीं ({amount})',
  'customer.deliveriesLabel': 'वितरण',
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
  'auth.forgotPassword': 'هل نسيت كلمة المرور؟',
  'auth.resetTitle': 'إعادة تعيين كلمة المرور',
  'auth.resetSendCode': 'إرسال رمز إعادة التعيين',
  'auth.resetSent':
      'إذا كان هناك حساب لـ {email}، فقد تم إرسال رمز إعادة التعيين.',
  'auth.resetCode': 'رمز إعادة التعيين',
  'auth.resetNewPassword': 'كلمة المرور الجديدة',
  'auth.resetMinLength': 'عشرة أحرف على الأقل.',
  'auth.resetSubmit': 'تعيين كلمة المرور الجديدة',
  'auth.resetTooMany': 'محاولات كثيرة — حاول لاحقًا.',
  'auth.resetDone': 'تم تحديث كلمة المرور — سجّل الدخول للمتابعة.',

  'common.retry': 'إعادة المحاولة',
  'common.loading': 'جارٍ التحميل…',
  'common.offline': 'لا توجد شبكة',
  'common.nothingHere': 'لا يوجد شيء لهذا الحساب على الجوال',
  'common.signOut': 'تسجيل الخروج',

  // P1-LOCALE-I18N-001 — the operator surfaces.
  'common.couldNotReach': 'تعذّر الوصول إلى المنصّة',
  'common.previous': 'السابق',
  'common.next': 'التالي',
  'common.save': 'حفظ',
  'common.saving': 'جارٍ الحفظ…',
  'common.done': 'تم',
  'common.edit': 'تعديل',
  'common.required': 'مطلوب',
  'common.nameTooShort': 'يحتاج الاسم إلى حرفين على الأقل',
  'common.activate': 'تفعيل',

  'milk.cow': 'بقر',
  'milk.buffalo': 'جاموس',
  'milk.goat': 'ماعز',
  'milk.mixed': 'مخلوط',

  'login.queuedSafe':
      '{count} سجلات ملتقطة محفوظة على هذا الهاتف وستُزامَن بعد تسجيل الدخول.',

  'wizard.stepTitle': 'الاستلام — الخطوة {n} من 6',
  'wizard.supplier': 'المورّد',
  'wizard.supplierCode': 'رمز المورّد',
  'wizard.supplierCodeHelp': 'مسح QR يأتي مع تكامل الأجهزة',
  'wizard.identify': 'تحديد المورّد',
  'wizard.milk': 'الحليب',
  'wizard.milkType': 'نوع الحليب',
  'wizard.containerType': 'نوع الوعاء',
  'wizard.containerId': 'معرّف الوعاء',
  'wizard.receiveMilk': 'استلام الحليب',
  'wizard.weight': 'الوزن',
  'wizard.grossKg': 'الوزن الإجمالي (kg)',
  'wizard.tareKg': 'وزن الفارغ (kg)',
  'wizard.captureWeight': 'تسجيل الوزن',
  'wizard.mockScale': 'استخدام ميزان تجريبي',
  'wizard.quality': 'الجودة',
  'wizard.fatLabel': 'FAT %',
  'wizard.snfLabel': 'SNF %',
  'wizard.clrLabel': 'CLR',
  'wizard.captureQuality': 'تسجيل الجودة',
  'wizard.mockAnalyzer': 'استخدام محلّل تجريبي',
  'wizard.review': 'مراجعة',
  'wizard.netWeightLine': 'الوزن الصافي: {kg} kg',
  'wizard.qualityLine': 'FAT {fat} · SNF {snf} · CLR {clr}',
  'wizard.pricingLine': 'التسعير: {status}',
  'wizard.acceptComplete': 'قبول وإتمام',
  'wizard.reject': 'رفض…',
  'wizard.rejectReason': 'سبب الرفض',
  'wizard.rejectReasonHelp':
      'يقرأ المزارع هذا على القسيمة — اذكر ما كان خاطئًا فعلاً '
      '(حموضة، غش، رائحة…)',
  'wizard.rejectComplete': 'رفض وإتمام',
  'wizard.keepReviewing': 'متابعة المراجعة',
  'wizard.rejectWhy': 'اذكر سبب رفض الحليب — يُطبع على القسيمة',
  'wizard.savedQueued': 'حُفظ على هذا الهاتف — في قائمة انتظار المزامنة',
  'wizard.txState': 'المعاملة {state}',
  'wizard.netLine': 'الصافي {kg} kg',
  'wizard.rejectedLine': 'مرفوض: {reason}',
  'wizard.payable': 'المستحق: {amount} {currency}',
  // TO CONFIRM (P1-LOCALE-I18N-001): settlement wording is financial — kept
  // English verbatim until the dairy's own words are confirmed.
  'wizard.nextSettlement': 'Will appear in the next supplier settlement.',
  'wizard.parchiQueued':
      'تصدر القسيمة عند مزامنة هذا الهاتف — رقم القسيمة يأتي من المنصّة، '
      'ولن يخترعه هذا الجهاز.',
  'wizard.parchi': 'قسيمة {number}',
  'wizard.copyParchi': 'نسخ نص القسيمة',
  'wizard.getParchi': 'جلب القسيمة',
  'wizard.fetchingParchi': 'جارٍ جلب القسيمة…',
  'wizard.parchiCopied': 'تم نسخ القسيمة',

  'center.listTitle': 'مراكز الاستلام',
  'center.new': 'مركز جديد',
  'center.searchHint': 'ابحث بالاسم أو الرمز',
  'center.noneMatch': 'لا توجد مراكز مطابقة.',
  'center.rateCards': 'بطاقات الأسعار',
  'center.settlements': 'التسويات',
  'center.payments': 'المدفوعات',
  'center.receipts': 'الإيصالات',
  'center.notifications': 'الإشعارات',
  'center.editTitle': 'تعديل {code}',
  'center.newTitle': 'مركز استلام جديد',
  'center.branch': 'الفرع',
  'center.selectBranch': 'اختر فرعًا',
  'center.name': 'الاسم',
  'center.code': 'الرمز',
  'center.codeHelp': 'فريد داخل مؤسستك، مثل KH-C1',
  'center.codeRequired': 'الرمز مطلوب',
  'center.timezone': 'المنطقة الزمنية',
  'center.fallback': 'المركز',
  'center.collections': 'عمليات الاستلام',
  'center.closeSession': 'إغلاق الجلسة',
  'center.collectMilk': 'استلام الحليب',
  'center.todaySummary': 'ملخص اليوم',
  'center.pricingTest': 'اختبار حساب التسعير',
  'center.noOpenSession': 'لا توجد جلسة مفتوحة في هذا المركز',
  'center.closeSessionTitle': 'إغلاق الجلسة؟',
  'center.closeSessionBody':
      'إغلاق "{label}" ينهي هذه المناوبة في المركز. عمليات الاستلام الملتقطة '
      'لا تتأثر؛ المناوبة الجديدة تفتح جلسة جديدة.',
  'center.keepOpen': 'إبقاؤها مفتوحة',
  'center.sessionClosed': 'أُغلقت الجلسة',
  'center.deactivate': 'إلغاء التفعيل',
  'center.maintenance': 'صيانة',
  'center.hours': 'ساعات العمل',
  'center.noHours': 'لم تُحدَّد ساعات عمل — لا يمكن تفعيل المركز بعد.',
  'center.calendar': 'تقويم العمل',
  'center.noEntries': 'لا توجد إدخالات.',
  'center.orgTimezone': 'المنطقة الزمنية للمؤسسة',

  'readiness.title': 'الجاهزية التشغيلية',
  'readiness.checksPassing': '{passed} من {total} فحوصات ناجحة',

  'history.title': 'عمليات الاستلام — {center}',
  'history.empty': 'لم تُسجَّل عمليات استلام في هذا المركز بعد.',
  'history.loadMore': 'تحميل المزيد ({n} من {total})',
  'history.fallback': 'استلام',
  'history.state': 'الحالة: {state}',
  'history.milk': 'الحليب: {milk}',
  'history.net': 'الصافي: {kg} kg',
  'history.amount': 'المبلغ: {amount} {currency}',

  'today.title': 'استلام اليوم',
  'today.milkCollected': 'الحليب المستلم',
  'today.payable': 'المستحق',
  'today.acceptedRejected': 'مقبول / مرفوض',
  'today.suppliersServed': 'المورّدون المخدومون',
  'today.avgFat': 'متوسط FAT',
  'today.avgSnf': 'متوسط SNF',
  'today.unpriced': '{n} مقبولة دون تسعير',
  'today.checkRateCard': 'تحقق من بطاقة الأسعار لهذا المركز.',
  'today.footer': 'اسحب للتحديث · التقارير الكاملة في بوابة الإدارة',

  'sync.title': 'المزامنة',
  'sync.offlineSaved':
      'دون اتصال — عمليات الاستلام تُحفظ على هذا الجهاز ({count} بالانتظار)',
  'sync.needAttention': '{count} عناصر تحتاج انتباهًا',
  'sync.syncingItems': 'مزامنة {count} عناصر…',
  'sync.now': 'مزامنة الآن',
  'sync.online': 'متصل',
  'sync.offline': 'غير متصل',
  'sync.lastSuccess': 'آخر مزامنة ناجحة: {ago}',
  'sync.never': 'أبدًا',
  'sync.justNow': 'الآن',
  'sync.minAgo': 'قبل {n} دقيقة',
  'sync.hAgo': 'قبل {n} ساعة',
  'sync.dAgo': 'قبل {n} يوم',
  'sync.pending': 'قيد الانتظار',
  'sync.synced': 'مُزامَن',
  'sync.failed': 'فشل',
  'sync.conflicts': 'تعارضات',
  'sync.lastRun':
      'آخر تشغيل: {applied} مطبّقة، {duplicates} موجودة مسبقًا، '
      '{conflicts} تعارض، {failed} فشلت',
  'sync.cancelledSafe': 'أُلغي — لم يُفقد شيء',
  'sync.retryFailed': 'إعادة محاولة الفاشلة',
  'sync.cancel': 'إلغاء',
  'sync.needsAttention': 'يحتاج انتباهًا ({n})',
  'sync.queue': 'قائمة الانتظار ({n})',
  'sync.nothingCaptured': 'لم يُلتقط شيء بعد.',
  'sync.attempt': ' · محاولة {n}',
  'sync.captured': 'وقت الالتقاط',
  'sync.operation': 'العملية',
  'sync.recordedAs': 'مسجَّل على المنصّة باسم',
  'sync.resolveWithSupervisor':
      'لم يُطبَّق هذا العنصر بصمت. قم بحلّه مع مشرفك في البوابة — تبقى '
      'البيانات الملتقطة على هذا الجهاز حتى ذلك الحين.',

  'queue.kind.open_session': 'فتح جلسة استلام',
  'queue.kind.close_session': 'إغلاق جلسة الاستلام',
  'queue.kind.create_transaction': 'بدء الاستلام',
  'queue.kind.identify_supplier': 'تحديد المورّد',
  'queue.kind.receive_milk': 'استلام الحليب',
  'queue.kind.capture_weight': 'تسجيل الوزن',
  'queue.kind.capture_quality': 'تسجيل الجودة',
  'queue.kind.accept': 'قبول الحليب',
  'queue.kind.reject': 'رفض الحليب',
  'queue.kind.complete': 'إتمام الاستلام',
  'queue.kind.cancel': 'إلغاء الاستلام',

  'conflict.already_accepted': 'مسجَّل على المنصّة مسبقًا',
  'conflict.supplier_unavailable': 'المورّد لم يعد نشطًا',
  'conflict.session_closed': 'أُغلقت جلسة الاستلام',
  'conflict.rate_card_changed':
      'تغيّرت الأسعار — احتُفظ بالاستلام والمبلغ مختلف',
  'conflict.unresolved_reference': 'بانتظار مزامنة خطوة سابقة',
  'conflict.invalid_state': 'رفضت المنصّة هذه الخطوة',
  'conflict.other': 'يحتاج انتباهًا',

  'supplier.title': 'المورّدون',
  'supplier.new': 'مورّد جديد',
  'supplier.searchHint': 'ابحث بالاسم أو الرمز أو الهاتف',
  'supplier.noneMatch': 'لا يوجد مورّدون مطابقون.',
  'supplier.editTitle': 'تعديل {code}',
  'supplier.fullName': 'الاسم الكامل',
  'supplier.phone': 'الهاتف',
  'supplier.village': 'القرية',
  'supplier.fallback': 'المورّد',
  'supplier.suspend': 'تعليق',
  'supplier.centersAssigned': '{n} مراكز استلام مخصصة',

  'home.nothingDetail':
      'سجّلت الدخول باسم {email}. يغطي هذا التطبيق استلام الحليب وجولة '
      'التوصيل وحساب العميل الخاص. كل ما عدا ذلك في بوابة الويب.',
  'home.sessionUnclear':
      'تم تسجيل الدخول، لكن المنصّة لم تستطع تحديد ما يمكنك فعله. '
      'تحقق من الاتصال وحاول مجددًا.',

  'customer.myDairy': 'الألبان',
  'customer.couldNotReachDairy':
      'تعذّر الوصول إلى الألبان. لا نعرض شيئًا بدلاً من عرض شيء قديم.',
  'customer.noBill': 'لم تصدر أي فاتورة بعد.',
  'customer.noDeliveries': 'لم تُسجَّل توصيلات بعد.',
  'customer.unbilled': '{n} توصيلات ليست على فاتورة بعد ({amount})',
  'customer.deliveriesLabel': 'التوصيلات',
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
