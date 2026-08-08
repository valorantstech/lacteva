// Minimal typed API client for platform-core.
// TODO(M2): replace hand-written types with generation from /openapi.json.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "lacteva.access_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token === null) window.localStorage.removeItem(TOKEN_KEY);
  else window.localStorage.setItem(TOKEN_KEY, token);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    /** Structured problem-detail payload (e.g. pricing resolution stage info). */
    public extra?: unknown,
  ) {
    super(detail);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (res.status === 401 && typeof window !== "undefined") {
    setToken(null);
    window.location.href = "/login";
  }
  if (!res.ok) {
    let detail = res.statusText;
    let extra: unknown;
    try {
      const body = (await res.json()) as { detail?: string; title?: string; extra?: unknown };
      detail = body.detail ?? body.title ?? detail;
      extra = body.extra;
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(res.status, detail, extra);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- Types (subset of the OpenAPI schema used by the portal) ---------------

export type Center = {
  id: string;
  branch_id: string;
  name: string;
  code: string;
  status: "active" | "inactive" | "maintenance" | "archived";
  timezone: string;
};

export type CenterPage = {
  items: Center[];
  total: number;
  limit: number;
  offset: number;
};

export type Branch = {
  id: string;
  workspace_id: string;
  name: string;
  code: string;
  status: string;
};

export async function login(email: string, password: string, tenantId?: string) {
  const body: Record<string, string> = { email, password };
  if (tenantId) body.tenant_id = tenantId;
  const pair = await api<{ access_token: string }>("/v1/auth/token", {
    method: "POST",
    body: JSON.stringify(body),
  });
  setToken(pair.access_token);
}

export function listCenters(params: {
  q?: string;
  status?: string;
  limit: number;
  offset: number;
}): Promise<CenterPage> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<CenterPage>(`/v1/collection-centers?${search.toString()}`);
}

export const listBranches = () => api<Branch[]>("/v1/branches");

export const createCenter = (body: { branch_id: string; name: string; code: string }) =>
  api<Center>("/v1/collection-centers", { method: "POST", body: JSON.stringify(body) });

export const updateCenter = (id: string, body: { name: string; timezone: string }) =>
  api<Center>(`/v1/collection-centers/${id}`, { method: "PUT", body: JSON.stringify(body) });

export type ReadinessCheck = {
  rule: string;
  severity: "blocking" | "warning";
  passed: boolean;
  detail: string;
};

export type ReadinessResult = {
  center_id: string;
  status: "READY" | "NOT_READY" | "WARNING";
  evaluated_at: string;
  checks: ReadinessCheck[];
};

export type Device = {
  id: string;
  center_id: string | null;
  category: string;
  name: string;
  serial_number: string;
  status: string;
};

export const getReadiness = (centerId: string) =>
  api<ReadinessResult>(`/v1/collection-centers/${centerId}/readiness`);

export const listCenterDevices = (centerId: string) =>
  api<{ items: Device[]; total: number }>(
    `/v1/devices?center_id=${centerId}&limit=100&offset=0`,
  );

export const setCenterStatus = (id: string, status: string) =>
  api<Center>(`/v1/collection-centers/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });

// --- Suppliers -------------------------------------------------------------

export type Supplier = {
  id: string;
  code: string;
  status: "draft" | "active" | "suspended" | "archived";
  branch_id: string | null;
  full_name: string;
  phone: string;
};

export type SupplierPage = {
  items: Supplier[];
  total: number;
  limit: number;
  offset: number;
};

export type SupplierDetail = {
  supplier: Supplier;
  profile: { full_name: string; phone: string; village: string; national_id: string };
  center_ids: string[];
  bank_accounts: {
    id: string;
    account_name: string;
    account_number_masked: string;
    bank_code: string;
    is_primary: boolean;
  }[];
  documents: { id: string; kind: string; file_name: string }[];
};

export function listSuppliers(params: {
  q?: string;
  status?: string;
  limit: number;
  offset: number;
}): Promise<SupplierPage> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<SupplierPage>(`/v1/suppliers?${search.toString()}`);
}

export const createSupplier = (body: {
  full_name: string;
  phone: string;
  village?: string;
  branch_id?: string;
}) => api<Supplier>("/v1/suppliers", { method: "POST", body: JSON.stringify(body) });

export const updateSupplier = (
  id: string,
  body: { full_name: string; phone: string; village?: string },
) => api(`/v1/suppliers/${id}`, { method: "PUT", body: JSON.stringify(body) });

export const setSupplierStatus = (id: string, status: string) =>
  api<Supplier>(`/v1/suppliers/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });

export const getSupplierDetail = (id: string) => api<SupplierDetail>(`/v1/suppliers/${id}`);

export const assignSupplierCenter = (id: string, centerId: string) =>
  api(`/v1/suppliers/${id}/centers`, {
    method: "POST",
    body: JSON.stringify({ center_id: centerId }),
  });

export const getSupplierQr = (id: string) =>
  api<{ payload: string; code: string }>(`/v1/suppliers/${id}/qr`);

// --- Rate cards (Pricing Platform — lifecycle only) -------------------------

export type RateCardStatus = "draft" | "under_review" | "approved" | "published" | "archived";

export type RateCard = {
  id: string;
  code: string;
  name: string;
  description: string;
  currency: string;
  effective_from: string;
  effective_until: string | null;
  status: RateCardStatus;
  version: number;
  branch_id: string | null;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  archived_at: string | null;
};

export type RateCardPage = {
  items: RateCard[];
  total: number;
  limit: number;
  offset: number;
};

export type RateCardDetail = {
  card: RateCard;
  center_ids: string[];
  products: { product_code: string; product_name: string }[];
  pricing_rules: unknown[];
};

export type RateCardInput = {
  name: string;
  description?: string;
  currency: string;
  effective_from: string;
  effective_until?: string | null;
  branch_id?: string | null;
};

export function listRateCards(params: {
  q?: string;
  status?: string;
  currency?: string;
  limit: number;
  offset: number;
}): Promise<RateCardPage> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  if (params.currency) search.set("currency", params.currency);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<RateCardPage>(`/v1/rate-cards?${search.toString()}`);
}

export const createRateCard = (body: RateCardInput & { code?: string }) =>
  api<RateCard>("/v1/rate-cards", { method: "POST", body: JSON.stringify(body) });

export const updateRateCard = (id: string, body: RateCardInput) =>
  api<RateCard>(`/v1/rate-cards/${id}`, { method: "PUT", body: JSON.stringify(body) });

export const getRateCardDetail = (id: string) => api<RateCardDetail>(`/v1/rate-cards/${id}`);

/** Workflow actions: submit | approve | publish | archive | versions (new draft version). */
export const rateCardAction = (id: string, action: string) =>
  api<RateCard>(`/v1/rate-cards/${id}/${action}`, { method: "POST", body: "{}" });

export const assignRateCardCenter = (id: string, centerId: string) =>
  api(`/v1/rate-cards/${id}/centers`, {
    method: "POST",
    body: JSON.stringify({ center_id: centerId }),
  });

export const assignRateCardProduct = (id: string, productCode: string, productName = "") =>
  api(`/v1/rate-cards/${id}/products`, {
    method: "POST",
    body: JSON.stringify({ product_code: productCode, product_name: productName }),
  });

// --- Pricing matrices (pricing data only — no calculation) ------------------

export type QualityDimension = {
  id: string;
  code: string;
  name: string;
  unit: string;
  min_value: number | null;
  max_value: number | null;
  active: boolean;
};

export type PricingMatrix = {
  id: string;
  rate_card_id: string;
  rate_card_code: string;
  name: string;
  product_code: string;
  product_name: string;
  dimension_code: string;
  status: "draft" | "active" | "archived";
  version: number;
  row_count: number;
  created_at: string;
  updated_at: string;
};

export type MatrixRow = {
  id: string;
  sequence: number;
  from_value: number;
  to_value: number;
  // DEPLOY-001: `unit_price` is stored as NUMERIC and serialises as a STRING,
  // like every other money field on this API (payment.amount,
  // settlement.net_amount). `from_value`/`to_value` are band boundaries, not
  // money, and remain numbers.
  unit_price: string | number;
  active: boolean;
};

export type MatrixDetail = {
  matrix: PricingMatrix;
  dimension: QualityDimension;
  rows: MatrixRow[];
  gaps: { from_value: number; to_value: number }[];
  editable: boolean;
};

export type MatrixPage = {
  items: PricingMatrix[];
  total: number;
  limit: number;
  offset: number;
};

export const listQualityDimensions = () =>
  api<QualityDimension[]>("/v1/quality-dimensions");

export function listMatrices(params: {
  q?: string;
  status?: string;
  rate_card_id?: string;
  limit: number;
  offset: number;
}): Promise<MatrixPage> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  if (params.rate_card_id) search.set("rate_card_id", params.rate_card_id);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<MatrixPage>(`/v1/pricing-matrices?${search.toString()}`);
}

export const createMatrix = (body: {
  rate_card_id: string;
  name: string;
  product_code: string;
  product_name?: string;
  dimension_code: string;
}) => api<PricingMatrix>("/v1/pricing-matrices", { method: "POST", body: JSON.stringify(body) });

export const updateMatrix = (
  id: string,
  body: { name: string; product_code: string; product_name?: string; dimension_code: string },
) => api<PricingMatrix>(`/v1/pricing-matrices/${id}`, { method: "PUT", body: JSON.stringify(body) });

export const deleteMatrix = (id: string) =>
  api(`/v1/pricing-matrices/${id}`, { method: "DELETE" });

export const getMatrixDetail = (id: string) => api<MatrixDetail>(`/v1/pricing-matrices/${id}`);

export type MatrixRowInput = {
  from_value: number;
  to_value: number;
  // Accepts a JSON number or a numeric string; both are parsed into Decimal
  // server-side, and a string is the exact form. Typed to match the response
  // so a row read from the API can be written straight back.
  unit_price: string | number;
  active?: boolean;
};

export const createMatrixRow = (matrixId: string, body: MatrixRowInput) =>
  api<MatrixRow>(`/v1/pricing-matrices/${matrixId}/rows`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const updateMatrixRow = (matrixId: string, rowId: string, body: MatrixRowInput) =>
  api<MatrixRow>(`/v1/pricing-matrices/${matrixId}/rows/${rowId}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const deleteMatrixRow = (matrixId: string, rowId: string) =>
  api(`/v1/pricing-matrices/${matrixId}/rows/${rowId}`, { method: "DELETE" });

// --- Pricing resolution (read-side selection only) --------------------------

export type ResolutionResult = {
  rate_card_id: string;
  rate_card_code: string;
  rate_card_version: number;
  matrix_id: string;
  matrix_name: string;
  row_id: string;
  row_sequence: number;
  matching_range: { from_value: number; to_value: number };
  unit_price: {
    amount: string | number;
    currency: string;
    precision: number;
    rounding_policy: string;
  };
  reading: { value: number; unit: string; precision: number };
  metadata: Record<string, unknown>;
};

export type ResolutionFailure = {
  status: number;
  title: string;
  stage?: string;
  reason?: string;
  inputs?: Record<string, unknown>;
  candidates?: string[];
};

export type ResolutionOutcome =
  | { ok: true; result: ResolutionResult }
  | { ok: false; failure: ResolutionFailure };

export async function resolvePricing(body: {
  center_id: string;
  product_code: string;
  transaction_date: string;
  dimension_code: string;
  value: number;
}): Promise<ResolutionOutcome> {
  try {
    const result = await api<ResolutionResult>("/v1/pricing/resolve", {
      method: "POST",
      body: JSON.stringify(body),
    });
    return { ok: true, result };
  } catch (err) {
    if (err instanceof ApiError && (err.status === 422 || err.status === 409)) {
      const extra = (err.extra ?? {}) as Record<string, unknown>;
      return {
        ok: false,
        failure: {
          status: err.status,
          title: err.detail,
          stage: extra.stage as string | undefined,
          reason: extra.reason as string | undefined,
          inputs: extra.inputs as Record<string, unknown> | undefined,
          candidates: extra.candidates as string[] | undefined,
        },
      };
    }
    throw err;
  }
}

// --- Pricing calculation (Decimal money math, PRC-004) ----------------------

export type TraceStep = {
  sequence: number;
  operation: string;
  detail: string;
  values: Record<string, string>;
};

export type CalculationResult = {
  calculation_id: string;
  unit_price: { amount: string | number; currency: string; rounding_policy: string };
  quantity: { value: number; unit: string };
  gross_amount: { amount: string | number; currency: string; rounding_policy: string };
  currency: string;
  rounding_policy: string;
  calculator_version: string;
  calculated_at: string;
  resolution: {
    rate_card_code: string;
    rate_card_version: number;
    matrix_name: string;
    row_id: string;
    range_from: number;
    range_to: number;
  };
  trace: TraceStep[];
};

export const calculatePricing = (body: {
  row_id: string;
  quantity: number;
  quantity_unit?: string;
  transaction_date: string;
  rounding_policy?: string;
}) =>
  api<CalculationResult>("/v1/pricing/calculate", {
    method: "POST",
    body: JSON.stringify(body),
  });

// --- Settlements (payable amounts — no payment) -----------------------------

export type SettlementStatus = "draft" | "calculated" | "finalized" | "cancelled";

export type Settlement = {
  id: string;
  settlement_number: string;
  supplier_id: string;
  center_id: string;
  period_from: string;
  period_to: string;
  currency: string;
  gross_amount: string | number;
  adjustments_amount: string | number;
  net_amount: string | number;
  status: SettlementStatus;
  line_count: number;
  created_at: string;
  finalized_at: string | null;
  cancelled_at: string | null;
};

export type SettlementLine = {
  id: string;
  calculation_id: string;
  transaction_id: string | null;
  transaction_date: string;
  quantity: string | number;
  quantity_unit: string;
  unit_price: string | number;
  gross_amount: string | number;
  trace_reference: string;
};

export type SettlementDetail = {
  settlement: Settlement;
  lines: SettlementLine[];
  totals_match_lines: boolean;
};

export type SettlementPageResult = {
  items: Settlement[];
  total: number;
  limit: number;
  offset: number;
};

export function listSettlements(params: {
  q?: string;
  status?: string;
  supplier_id?: string;
  limit: number;
  offset: number;
}): Promise<SettlementPageResult> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  if (params.supplier_id) search.set("supplier_id", params.supplier_id);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<SettlementPageResult>(`/v1/settlements?${search.toString()}`);
}

export const createSettlement = (body: {
  supplier_id: string;
  center_id: string;
  period_from: string;
  period_to: string;
  currency: string;
}) => api<Settlement>("/v1/settlements", { method: "POST", body: JSON.stringify(body) });

export const getSettlementDetail = (id: string) =>
  api<SettlementDetail>(`/v1/settlements/${id}`);

export const addSettlementCalculation = (id: string, calculationId: string) =>
  api<SettlementLine>(`/v1/settlements/${id}/calculations`, {
    method: "POST",
    body: JSON.stringify({ calculation_id: calculationId }),
  });

export const removeSettlementLine = (id: string, lineId: string) =>
  api(`/v1/settlements/${id}/lines/${lineId}`, { method: "DELETE" });

export const collectSettlementPeriod = (id: string) =>
  api<{ added: number; skipped: number }>(`/v1/settlements/${id}/collect`, {
    method: "POST",
    body: "{}",
  });

/** action: calculate | finalize | cancel */
export const settlementAction = (id: string, action: string) =>
  api<Settlement>(`/v1/settlements/${id}/${action}`, { method: "POST", body: "{}" });

// --- Reports (read-only summaries) ------------------------------------------

export type DailyCollectionSummary = {
  date_from: string;
  date_to: string;
  transactions: number;
  accepted: number;
  rejected: number;
  cancelled: number;
  in_progress: number;
  suppliers_served: number;
  total_net_weight_kg: number;
  payable_by_currency: Record<string, string | number>;
  unpriced_accepted: number;
  weighted_avg_fat: number | null;
  weighted_avg_snf: number | null;
};

export type CenterSummaryRow = {
  center_id: string;
  center_code: string;
  center_name: string;
  transactions: number;
  accepted: number;
  total_net_weight_kg: number;
  payable_amount: string | number;
  currency: string | null;
  weighted_avg_fat: number | null;
};

export type SupplierSummaryRow = {
  supplier_id: string;
  supplier_code: string;
  supplier_name: string;
  deliveries: number;
  accepted: number;
  total_net_weight_kg: number;
  payable_amount: string | number;
  currency: string | null;
  weighted_avg_fat: number | null;
};

export type ReportPage<T> = { items: T[]; total: number; limit: number; offset: number };

export type SettlementReport = {
  by_status: { status: string; count: number; net_amount: string | number }[];
  finalized_net_total: string | number;
  total_settlements: number;
  total_lines: number;
};

export type PricingReport = {
  priced_transactions: number;
  unpriced_transactions: number;
  gross_by_currency: Record<string, string | number>;
  avg_unit_price: number | null;
  min_unit_price: string | number | null;
  max_unit_price: string | number | null;
  published_rate_cards: number;
  active_matrices: number;
  active_bands: number;
};

const reportQuery = (params: Record<string, string | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) search.set(key, value);
  return search.toString();
};

export const getDailyReport = (params: Record<string, string | undefined>) =>
  api<DailyCollectionSummary>(`/v1/reports/collection/daily?${reportQuery(params)}`);

export const getCenterReport = (params: Record<string, string | undefined>) =>
  api<ReportPage<CenterSummaryRow>>(`/v1/reports/collection/by-center?${reportQuery(params)}`);

export const getSupplierReport = (params: Record<string, string | undefined>) =>
  api<ReportPage<SupplierSummaryRow>>(
    `/v1/reports/collection/by-supplier?${reportQuery(params)}`,
  );

export const getSettlementReport = (params: Record<string, string | undefined>) =>
  api<SettlementReport>(`/v1/reports/settlements?${reportQuery(params)}`);

export const getPricingReport = (params: Record<string, string | undefined>) =>
  api<PricingReport>(`/v1/reports/pricing?${reportQuery(params)}`);

// --- Milk transactions ------------------------------------------------------

export type MilkTransaction = {
  id: string;
  session_id: string;
  center_id: string;
  supplier_id: string | null;
  state: string;
  milk_type: string | null;
  net_weight: number | null;
  fat: number | null;
  snf: number | null;
  clr: number | null;
  pricing_status: string | null;
  unit_price: string | number | null;
  gross_amount: string | number | null;
  currency: string | null;
  calculation_id: string | null;
  pricing_detail: string | null;
  rejected_reason: string | null;
  created_at: string;
  completed_at: string | null;
};

export type MilkTransactionPage = {
  items: MilkTransaction[];
  total: number;
  limit: number;
  offset: number;
};

export type TransactionEvent = {
  sequence: number;
  event_type: string;
  data: Record<string, unknown>;
  created_at: string;
};

export function listMilkTransactions(params: {
  state?: string;
  center_id?: string;
  limit: number;
  offset: number;
}): Promise<MilkTransactionPage> {
  const search = new URLSearchParams();
  if (params.state) search.set("state", params.state);
  if (params.center_id) search.set("center_id", params.center_id);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<MilkTransactionPage>(`/v1/milk-transactions?${search.toString()}`);
}

export const getMilkTransaction = (id: string) =>
  api<MilkTransaction>(`/v1/milk-transactions/${id}`);

export const getMilkTransactionEvents = (id: string) =>
  api<TransactionEvent[]>(`/v1/milk-transactions/${id}/events`);

// --- Notifications (NOT-001) ------------------------------------------------

export type Notification = {
  id: string;
  event_id: string;
  event_name: string;
  template_key: string;
  channel: string;
  language: string;
  recipient: string | null;
  recipient_ref: string | null;
  title: string | null;
  rendered_text: string | null;
  status: string;
  provider: string | null;
  provider_reference: string | null;
  attempt_count: number;
  next_attempt_at: string | null;
  error: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  sent_at: string | null;
  failed_at: string | null;
};

export type NotificationPage = {
  items: Notification[];
  total: number;
  limit: number;
  offset: number;
};

export type NotificationStats = {
  total: number;
  by_status: Record<string, number>;
  by_channel: Record<string, number>;
  retryable: number;
};

export type NotificationTemplate = {
  key: string;
  channel: string;
  language: string;
  title: string;
  body: string;
  variables: string[];
};

export type RenderedPreview = {
  key: string;
  channel: string;
  language: string;
  title: string;
  body: string;
  variables_used: Record<string, unknown>;
};

export function listNotifications(params: {
  q?: string;
  status?: string;
  channel?: string;
  template_key?: string;
  limit: number;
  offset: number;
}): Promise<NotificationPage> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  if (params.channel) search.set("channel", params.channel);
  if (params.template_key) search.set("template_key", params.template_key);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<NotificationPage>(`/v1/notifications?${search.toString()}`);
}

export const getNotificationStats = () => api<NotificationStats>("/v1/notifications/stats");

export const getNotification = (id: string) => api<Notification>(`/v1/notifications/${id}`);

export const retryNotification = (id: string) =>
  api<Notification>(`/v1/notifications/${id}/retry`, { method: "POST" });

export const retryPendingNotifications = () =>
  api<{ retried: number; sent: number; failed: number }>("/v1/notifications/retry-pending", {
    method: "POST",
  });

export const listNotificationTemplates = () =>
  api<NotificationTemplate[]>("/v1/notification-templates");

export const previewNotificationTemplate = (
  key: string,
  body: { channel: string; language?: string; variables: Record<string, string> },
) =>
  api<RenderedPreview>(`/v1/notification-templates/${key}/preview`, {
    method: "POST",
    body: JSON.stringify(body),
  });

// --- Payments (PAY-001) -----------------------------------------------------

export type PaymentLine = {
  id: string;
  settlement_id: string;
  settlement_number: string;
  amount: string | number;
};

export type PaymentAttempt = {
  id: string;
  attempt_number: number;
  provider: string;
  reference: string | null;
  status: string;
  operator_id: string | null;
  failure_reason: string | null;
  started_at: string;
  completed_at: string | null;
};

export type Payment = {
  id: string;
  payment_number: string;
  supplier_id: string;
  currency: string;
  method: string;
  amount: string | number;
  reference: string | null;
  method_details: Record<string, unknown>;
  status: string;
  attempt_count: number;
  failure_reason: string | null;
  note: string | null;
  line_count: number;
  created_at: string;
  completed_at: string | null;
  failed_at: string | null;
  cancelled_at: string | null;
};

export type PaymentDetail = {
  payment: Payment;
  lines: PaymentLine[];
  attempts: PaymentAttempt[];
  totals_match_lines: boolean;
};

export type PaymentPageResult = {
  items: Payment[];
  total: number;
  limit: number;
  offset: number;
};

export type SettlementBalance = {
  settlement_id: string;
  settlement_number: string;
  supplier_id: string;
  currency: string;
  payable: string | number;
  allocated: string | number;
  paid: string | number;
  outstanding: string | number;
  fully_paid: boolean;
};

export type BalancePageResult = {
  items: SettlementBalance[];
  total: number;
  limit: number;
  offset: number;
};

export const PAYMENT_METHODS = ["BANK_TRANSFER", "CASH", "CHEQUE", "MOBILE_MONEY"] as const;

export function listPayments(params: {
  q?: string;
  supplier_id?: string;
  settlement_id?: string;
  status?: string;
  method?: string;
  limit: number;
  offset: number;
}): Promise<PaymentPageResult> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.supplier_id) search.set("supplier_id", params.supplier_id);
  if (params.settlement_id) search.set("settlement_id", params.settlement_id);
  if (params.status) search.set("status", params.status);
  if (params.method) search.set("method", params.method);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<PaymentPageResult>(`/v1/payments?${search.toString()}`);
}

export function listOutstandingBalances(params: {
  supplier_id?: string;
  outstanding_only?: boolean;
  limit: number;
  offset: number;
}): Promise<BalancePageResult> {
  const search = new URLSearchParams();
  if (params.supplier_id) search.set("supplier_id", params.supplier_id);
  if (params.outstanding_only === false) search.set("outstanding_only", "false");
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<BalancePageResult>(`/v1/payments/balances?${search.toString()}`);
}

export const getPaymentDetail = (id: string) => api<PaymentDetail>(`/v1/payments/${id}`);

export const getSettlementBalance = (settlementId: string) =>
  api<SettlementBalance>(`/v1/settlements/${settlementId}/balance`);

export function createPayment(body: {
  supplier_id: string;
  currency: string;
  method: string;
  allocations: { settlement_id: string; amount?: string }[];
  reference?: string;
  note?: string;
  idempotency_key?: string;
}): Promise<Payment> {
  return api<Payment>("/v1/payments", { method: "POST", body: JSON.stringify(body) });
}

export const paymentAction = (
  id: string,
  action: "submit" | "execute" | "retry" | "complete" | "fail" | "cancel",
  body: Record<string, string> = {},
) => api<Payment>(`/v1/payments/${id}/${action}`, { method: "POST", body: JSON.stringify(body) });

// --- Receipts (RCP-001) -----------------------------------------------------

export type ReceiptLine = {
  id: string;
  settlement_id: string;
  settlement_number: string;
  center_id: string | null;
  period_from: string | null;
  period_to: string | null;
  gross_amount: string | number;
  adjustments_amount: string | number;
  net_amount: string | number;
  amount_paid: string | number;
};

export type Receipt = {
  id: string;
  receipt_number: string;
  payment_id: string;
  payment_number: string;
  payment_reference: string | null;
  payment_method: string;
  payment_date: string | null;
  supplier_id: string;
  supplier_name: string;
  supplier_code: string;
  currency: string;
  gross_amount: string | number;
  adjustments_amount: string | number;
  net_amount: string | number;
  status: string;
  render_format: string;
  version: number;
  line_count: number;
  generated_at: string;
  delivered_at: string | null;
  archived_at: string | null;
};

export type ReceiptReference = {
  payment_id: string;
  payment_number: string;
  payment_reference: string | null;
  settlement_ids: string[];
  settlement_numbers: string[];
  center_ids: string[];
  source_event_id: string | null;
  correlation_id: string | null;
};

export type ReceiptMetadata = {
  version: number;
  render_format: string;
  available_formats: string[];
  generated_at: string;
  delivered_at: string | null;
  archived_at: string | null;
};

export type ReceiptDetail = {
  receipt: Receipt;
  lines: ReceiptLine[];
  reference: ReceiptReference;
  metadata: ReceiptMetadata;
};

export type ReceiptPageResult = {
  items: Receipt[];
  total: number;
  limit: number;
  offset: number;
};

export type RenderedReceipt = {
  receipt_id: string;
  receipt_number: string;
  format: string;
  content_type: string;
  filename: string;
  body: string;
  placeholder: boolean;
};

export function listReceipts(params: {
  q?: string;
  supplier_id?: string;
  payment_id?: string;
  status?: string;
  limit: number;
  offset: number;
}): Promise<ReceiptPageResult> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.supplier_id) search.set("supplier_id", params.supplier_id);
  if (params.payment_id) search.set("payment_id", params.payment_id);
  if (params.status) search.set("status", params.status);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<ReceiptPageResult>(`/v1/receipts?${search.toString()}`);
}

export const getReceiptDetail = (id: string) => api<ReceiptDetail>(`/v1/receipts/${id}`);

export const renderReceipt = (id: string, format: string) =>
  api<RenderedReceipt>(`/v1/receipts/${id}/render?format=${format}`);

export const receiptAction = (id: string, action: "deliver" | "archive") =>
  api<Receipt>(`/v1/receipts/${id}/${action}`, { method: "POST" });

/** Download URL for the artifact — served by the API with a filename. */
export const receiptDownloadUrl = (id: string, format: string) =>
  `${API_URL}/v1/receipts/${id}/download?format=${format}`;

// --- Offline sync monitor (OFF-001, read-only) ------------------------------

export type SyncOperation = {
  id: string;
  operation_id: string;
  device_id: string;
  kind: string;
  sequence: number;
  client_reference: string | null;
  target_ref: string | null;
  status: string;
  applied: boolean;
  server_id: string | null;
  conflict_reason: string | null;
  conflict_detail: string | null;
  error: string | null;
  attempts: number;
  recorded_at: string | null;
  created_at: string;
  applied_at: string | null;
};

export type SyncOperationPage = {
  items: SyncOperation[];
  total: number;
  limit: number;
  offset: number;
};

export type DeviceSync = {
  device_id: string;
  operations: number;
  conflicts: number;
  failed: number;
  last_sync_at: string | null;
};

export type SyncStats = {
  total: number;
  by_status: Record<string, number>;
  by_kind: Record<string, number>;
  conflicts: number;
  failed: number;
  devices: DeviceSync[];
  last_sync_at: string | null;
};

export function listSyncOperations(params: {
  status?: string;
  kind?: string;
  device_id?: string;
  limit: number;
  offset: number;
}): Promise<SyncOperationPage> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.kind) search.set("kind", params.kind);
  if (params.device_id) search.set("device_id", params.device_id);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<SyncOperationPage>(`/v1/sync/operations?${search.toString()}`);
}

export const getSyncStats = () => api<SyncStats>("/v1/sync/stats");

export const retrySyncOperation = (operationId: string) =>
  api<SyncOperation>(`/v1/sync/operations/${operationId}/retry`, { method: "POST" });
