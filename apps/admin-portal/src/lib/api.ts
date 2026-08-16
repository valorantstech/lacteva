// Minimal typed API client for platform-core.
// TODO(M2): replace hand-written types with generation from /openapi.json.
//
// PORTAL-001 / F-11: this client holds NO credential.
//
// It used to read a bearer token out of `localStorage` and put it on every
// request, which meant any script running on the page — an XSS, a compromised
// dependency, a browser extension — could read a live session token. There is
// no way to store a token in the browser that script cannot reach, so the
// token is not in the browser any more: it lives in an HttpOnly cookie that
// only the portal's own server can see, and every call goes same-origin to
// `/api/proxy`, which attaches it (see `src/app/api/proxy`).
//
// Consequences worth knowing:
//   * `API_URL` is gone. The browser does not know where the platform is.
//   * requests carry the session cookie automatically, so nothing here has to
//     remember to attach anything.
//   * CSRF is handled by `SameSite=Strict` plus an Origin check in the route
//     handlers, so the backend stays bearer-only and CSRF-free (divergence
//     #22 still holds — it never sees a cookie).

/** Same-origin. The platform's address is a server-side secret. */
const PROXY_PREFIX = "/api/proxy";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    /** Structured problem-detail payload (e.g. pricing resolution stage info). */
    public extra?: unknown,
    /**
     * The problem document's `title` — the platform's machine-readable code
     * (DEMO-010). `detail` is prose for a person and is translated; a caller
     * that needs to BEHAVE differently for one failure has to match on this.
     */
    public title?: string,
  ) {
    super(detail);
  }
}

/** Options that change how a call BEHAVES, as opposed to what it sends. */
export type ApiOptions = {
  /**
   * Send the browser to /login on a 401. Default true.
   *
   * A session PROBE must set this false: a 401 is a valid answer to "am I
   * signed in?", not a failure to recover from. See the loop described in
   * `api()` below.
   */
  redirectOn401?: boolean;
};

export async function api<T>(
  path: string,
  init?: RequestInit,
  options: ApiOptions = {},
): Promise<T> {
  const res = await fetch(`${PROXY_PREFIX}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    // The session cookie rides along automatically; there is no token to add.
    credentials: "same-origin",
    cache: "no-store",
  });
  if (res.status === 401 && typeof window !== "undefined") {
    // The cookie is gone or the platform rejected it. Nothing to clear on
    // this side — that is the point of it being HttpOnly.
    //
    // LOOP-001: two guards, and both are load-bearing.
    //
    // `SessionControls` lives in the root layout, so it mounts on EVERY page
    // — including /login — and asks `getMe()` who is signed in. Unconditional
    // redirection turned that into an infinite hard reload for anyone not
    // signed in: /login mounts, probes, gets 401, navigates to /login, mounts,
    // probes... Observed in production as 768 consecutive 401s from one
    // browser in an hour, until nginx's rate limiter started refusing it.
    //
    // `redirectOn401: false` is how a probe opts out. The pathname check is
    // the backstop: navigating to the page you are already on can only ever
    // be a loop, whoever asked for it.
    const alreadyThere = window.location.pathname === "/login";
    if (options.redirectOn401 !== false && !alreadyThere) {
      window.location.href = "/login";
    }
  }
  if (!res.ok) {
    let detail = res.statusText;
    let extra: unknown;
    let title: string | undefined;
    try {
      const body = (await res.json()) as {
        detail?: string;
        title?: string;
        extra?: unknown;
      };
      detail = body.detail ?? body.title ?? detail;
      extra = body.extra;
      title = body.title;
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(res.status, detail, extra, title);
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

/**
 * Sign in. The token never comes back to this code — the route handler puts
 * it in an HttpOnly cookie and answers 204.
 */
export async function login(
  email: string,
  password: string,
  tenantId?: string,
) {
  const body: Record<string, string> = { email, password };
  if (tenantId) body.tenant_id = tenantId;
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    let title: string | undefined;
    try {
      const problem = (await res.json()) as { detail?: string; title?: string };
      detail = problem.detail ?? problem.title ?? detail;
      title = problem.title;
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(res.status, detail, undefined, title);
  }
}

/** Sign out here AND on the platform, so a captured refresh token dies too. */
export async function logout() {
  await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
  });
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

export const createCenter = (body: {
  branch_id: string;
  name: string;
  code: string;
}) =>
  api<Center>("/v1/collection-centers", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const updateCenter = (
  id: string,
  body: { name: string; timezone: string },
) =>
  api<Center>(`/v1/collection-centers/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

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

export type OperatingWindow = {
  day_of_week: number;
  opens: string;
  closes: string;
};

export type CenterDetail = {
  center: Center;
  settings: Record<string, unknown>;
  operating_windows: OperatingWindow[];
  calendar: { date: string; is_open: boolean; note?: string }[];
};

export const getCenterDetail = (id: string) =>
  api<CenterDetail>(`/v1/collection-centers/${id}`);

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
  profile: {
    full_name: string;
    phone: string;
    village: string;
    national_id: string;
  };
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
  // DEMO-003: the platform already filters by centre server-side; the portal
  // simply had no way to ask.
  center_id?: string;
  limit: number;
  offset: number;
}): Promise<SupplierPage> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.center_id) search.set("center_id", params.center_id);
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
}) =>
  api<Supplier>("/v1/suppliers", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const updateSupplier = (
  id: string,
  body: { full_name: string; phone: string; village?: string },
) => api(`/v1/suppliers/${id}`, { method: "PUT", body: JSON.stringify(body) });

export const setSupplierStatus = (id: string, status: string) =>
  api<Supplier>(`/v1/suppliers/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });

export const getSupplierDetail = (id: string) =>
  api<SupplierDetail>(`/v1/suppliers/${id}`);

export const assignSupplierCenter = (id: string, centerId: string) =>
  api(`/v1/suppliers/${id}/centers`, {
    method: "POST",
    body: JSON.stringify({ center_id: centerId }),
  });

export const getSupplierQr = (id: string) =>
  api<{ payload: string; code: string }>(`/v1/suppliers/${id}/qr`);

// --- Rate cards (Pricing Platform — lifecycle only) -------------------------

export type RateCardStatus =
  "draft" | "under_review" | "approved" | "published" | "archived";

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
  api<RateCard>("/v1/rate-cards", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const updateRateCard = (id: string, body: RateCardInput) =>
  api<RateCard>(`/v1/rate-cards/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const getRateCardDetail = (id: string) =>
  api<RateCardDetail>(`/v1/rate-cards/${id}`);

/** Workflow actions: submit | approve | publish | archive | versions (new draft version). */
export const rateCardAction = (id: string, action: string) =>
  api<RateCard>(`/v1/rate-cards/${id}/${action}`, {
    method: "POST",
    body: "{}",
  });

export const assignRateCardCenter = (id: string, centerId: string) =>
  api(`/v1/rate-cards/${id}/centers`, {
    method: "POST",
    body: JSON.stringify({ center_id: centerId }),
  });

export const assignRateCardProduct = (
  id: string,
  productCode: string,
  productName = "",
) =>
  api(`/v1/rate-cards/${id}/products`, {
    method: "POST",
    body: JSON.stringify({
      product_code: productCode,
      product_name: productName,
    }),
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
}) =>
  api<PricingMatrix>("/v1/pricing-matrices", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const updateMatrix = (
  id: string,
  body: {
    name: string;
    product_code: string;
    product_name?: string;
    dimension_code: string;
  },
) =>
  api<PricingMatrix>(`/v1/pricing-matrices/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const deleteMatrix = (id: string) =>
  api(`/v1/pricing-matrices/${id}`, { method: "DELETE" });

export const getMatrixDetail = (id: string) =>
  api<MatrixDetail>(`/v1/pricing-matrices/${id}`);

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

export const updateMatrixRow = (
  matrixId: string,
  rowId: string,
  body: MatrixRowInput,
) =>
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
  unit_price: {
    amount: string | number;
    currency: string;
    rounding_policy: string;
  };
  quantity: { value: number; unit: string };
  gross_amount: {
    amount: string | number;
    currency: string;
    rounding_policy: string;
  };
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

export type SettlementStatus =
  "draft" | "calculated" | "finalized" | "cancelled";

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
  // DEMO-006: the platform already filters by centre; the portal had no way
  // to ask.
  center_id?: string;
  limit: number;
  offset: number;
}): Promise<SettlementPageResult> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  if (params.supplier_id) search.set("supplier_id", params.supplier_id);
  if (params.center_id) search.set("center_id", params.center_id);
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
}) =>
  api<Settlement>("/v1/settlements", {
    method: "POST",
    body: JSON.stringify(body),
  });

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
/**
 * The settlement lifecycle: `calculate` sums the lines, `finalize` freezes the
 * result (BR-0010 — irreversible), `cancel` abandons an open one.
 * DEMO-006 added the body so `cancel` can carry its reason.
 */
export const settlementAction = (
  id: string,
  action: "calculate" | "finalize" | "cancel",
  body: Record<string, string> = {},
) =>
  api<Settlement>(`/v1/settlements/${id}/${action}`, {
    method: "POST",
    body: JSON.stringify(body),
  });

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
  last_collection_at: string | null;
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
  last_collection_at: string | null;
};

export type ReportPage<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

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

/**
 * DEMO-002 aggregates. Money arrives as an exact decimal STRING; these types
 * say `string | number` because JSON allows either, and every one of them is
 * handed to `<Money>` rather than to arithmetic.
 */
export type PaymentStatusRow = {
  status: string;
  count: number;
  amount: string | number;
  currency: string | null;
};

export type PaymentReport = {
  by_status: PaymentStatusRow[];
  total_payments: number;
  completed_count: number;
  processing_count: number;
  pending_count: number;
  failed_count: number;
  completed_amount: string | number;
  outstanding_amount: string | number;
  failed_amount: string | number;
  total_by_currency: Record<string, string | number>;
};

export type TrendPoint = {
  day: string;
  transactions: number;
  accepted: number;
  total_net_weight_kg: number;
  payable_amount: string | number;
  currency: string | null;
};

export type CollectionTrend = {
  date_from: string;
  date_to: string;
  points: TrendPoint[];
};

export type RateBandRow = {
  unit_price: string | number;
  currency: string | null;
  transactions: number;
  total_net_weight_kg: number;
  payable_amount: string | number;
};

export type AttentionItem = {
  key: string;
  label: string;
  count: number;
  severity: string;
  href: string | null;
};

// DEMO-010 — the sales side of the same block. Amounts are strings for the
// same reason they are everywhere else in this file: they are `Decimal` on the
// platform and must not become a JavaScript binary float on the way in.
export type InvoiceStatusRow = {
  status: string;
  count: number;
  total: string;
};

export type SalesSummary = {
  date_from: string;
  date_to: string;
  currency: string | null;
  deliveries_in_period: number;
  delivered_quantity_in_period: string;
  quantity_unit: string;
  sales_value_in_period: string;
  customers_served_in_period: number;
  active_customers: number;
  total_customers: number;
  /** Balances, as at now — deliberately NOT narrowed by the date range. */
  invoiced: string;
  received: string;
  receivable: string;
  by_status: InvoiceStatusRow[];
  open_invoices: number;
  customers_owing: number;
  unbilled_deliveries: number;
  unbilled_amount: string;
  receipts_issued: number;
};

export type ReceivableRow = {
  customer_id: string;
  code: string;
  name: string;
  phone: string;
  status: string;
  currency: string;
  invoiced: string;
  paid: string;
  outstanding: string;
  open_invoices: number;
  last_payment_at: string | null;
  oldest_unpaid_from: string | null;
};

export type ReceivablesPage = {
  items: ReceivableRow[];
  total: number;
  limit: number;
  offset: number;
  /** Across every match, not the page. Never sum `items` in a component. */
  total_outstanding: string;
  currency: string | null;
};

export type DashboardReport = {
  date_from: string;
  date_to: string;
  collection: DailyCollectionSummary;
  settlements: SettlementReport;
  payments: PaymentReport;
  sales: SalesSummary;
  rate_bands: RateBandRow[];
  active_suppliers: number;
  active_centers: number;
  inactive_centers: number;
  attention: AttentionItem[];
};

const reportQuery = (params: Record<string, string | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params))
    if (value) search.set(key, value);
  return search.toString();
};

export const getDailyReport = (params: Record<string, string | undefined>) =>
  api<DailyCollectionSummary>(
    `/v1/reports/collection/daily?${reportQuery(params)}`,
  );

export const getCenterReport = (params: Record<string, string | undefined>) =>
  api<ReportPage<CenterSummaryRow>>(
    `/v1/reports/collection/by-center?${reportQuery(params)}`,
  );

export const getSupplierReport = (params: Record<string, string | undefined>) =>
  api<ReportPage<SupplierSummaryRow>>(
    `/v1/reports/collection/by-supplier?${reportQuery(params)}`,
  );

export const getSettlementReport = (
  params: Record<string, string | undefined>,
) => api<SettlementReport>(`/v1/reports/settlements?${reportQuery(params)}`);

export const getPricingReport = (params: Record<string, string | undefined>) =>
  api<PricingReport>(`/v1/reports/pricing?${reportQuery(params)}`);

export const getDashboardReport = (
  params: Record<string, string | undefined>,
) => api<DashboardReport>(`/v1/reports/dashboard?${reportQuery(params)}`);

export const getPaymentReport = (params: Record<string, string | undefined>) =>
  api<PaymentReport>(`/v1/reports/payments?${reportQuery(params)}`);

export const getCollectionTrend = (
  params: Record<string, string | undefined>,
) =>
  api<CollectionTrend>(`/v1/reports/collection/trend?${reportQuery(params)}`);

export const getSalesSummary = (params: Record<string, string | undefined>) =>
  api<SalesSummary>(`/v1/reports/sales/summary?${reportQuery(params)}`);

export const getReceivables = (params: Record<string, string | undefined>) =>
  api<ReceivablesPage>(`/v1/reports/receivables?${reportQuery(params)}`);

// --- Milk transactions ------------------------------------------------------

export type MilkTransaction = {
  id: string;
  session_id: string;
  center_id: string;
  supplier_id: string | null;
  operator_id: string;
  state: string;
  milk_type: string | null;
  milk_type_custom: string | null;
  // DEMO-004: the platform has always returned these; the portal type simply
  // did not name them, so the detail page could not show a gross/tare split.
  container_type: string | null;
  container_identifier: string | null;
  arrival_temperature_c: number | null;
  arrived_at: string | null;
  weight_unit: string | null;
  gross_weight: number | null;
  tare_weight: number | null;
  net_weight: number | null;
  // DEMO-007: how the reading was obtained. "manual" is the domain's own name
  // for an operator entering it; the alternative is an instrument. Showing a
  // number without its source is how a hand-typed weight comes to look
  // certified.
  weight_source: string | null;
  fat: number | null;
  snf: number | null;
  clr: number | null;
  density: number | null;
  quality_temperature_c: number | null;
  quality_remarks: string | null;
  quality_source: string | null;
  pricing_status: string | null;
  unit_price: string | number | null;
  gross_amount: string | number | null;
  currency: string | null;
  calculation_id: string | null;
  pricing_detail: string | null;
  rejected_reason: string | null;
  decided_by: string | null;
  decided_at: string | null;
  cancelled_reason: string | null;
  created_at: string;
  completed_at: string | null;
};

/**
 * DEMO-007: where a page of collections has reached, financially.
 *
 * One call per page, never per row. `/v1/reports/collection/{id}/chain`
 * answers this for a single collection; asking it fifty times to draw one
 * table is the N+1 this endpoint exists to avoid.
 */
export type OperationalStatus = {
  transaction_id: string;
  last_event_type: string | null;
  last_event_at: string | null;
  settlement_id: string | null;
  settlement_number: string | null;
  settlement_status: string | null;
  settled_amount: string | number | null;
  payment_id: string | null;
  payment_number: string | null;
  payment_status: string | null;
  receipt_id: string | null;
  receipt_number: string | null;
  receipt_status: string | null;
};

export function getOperationalStatus(transactionIds: string[]): Promise<{
  items: OperationalStatus[];
}> {
  if (transactionIds.length === 0) return Promise.resolve({ items: [] });
  const search = new URLSearchParams();
  for (const id of transactionIds) search.append("transaction_ids", id);
  return api<{ items: OperationalStatus[] }>(
    `/v1/reports/collection/operational-status?${search.toString()}`,
  );
}

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
  /** DEMO-007: the platform has always recorded who; the type omitted it. */
  actor_id: string | null;
  created_at: string;
};

export function listMilkTransactions(params: {
  state?: string;
  center_id?: string;
  supplier_id?: string;
  // DEMO-004: the window the DATABASE filters on.
  date_from?: string;
  date_to?: string;
  limit: number;
  offset: number;
}): Promise<MilkTransactionPage> {
  const search = new URLSearchParams();
  if (params.state) search.set("state", params.state);
  if (params.center_id) search.set("center_id", params.center_id);
  if (params.supplier_id) search.set("supplier_id", params.supplier_id);
  if (params.date_from) search.set("date_from", params.date_from);
  if (params.date_to) search.set("date_to", params.date_to);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<MilkTransactionPage>(`/v1/milk-transactions?${search.toString()}`);
}

/** DEMO-005: the collection state machine, driven step by step. */
export type CollectionSession = {
  id: string;
  center_id: string;
  status: string;
  label?: string;
  opened_at?: string;
};

export const listCollectionSessions = (params: {
  center_id?: string;
  status?: string;
}) => {
  const search = new URLSearchParams();
  if (params.center_id) search.set("center_id", params.center_id);
  if (params.status) search.set("status", params.status);
  search.set("limit", "20");
  return api<{ items: CollectionSession[]; total: number }>(
    `/v1/collection-sessions?${search.toString()}`,
  );
};

export const openCollectionSession = (centerId: string, label: string) =>
  api<CollectionSession>("/v1/collection-sessions", {
    method: "POST",
    body: JSON.stringify({ center_id: centerId, label }),
  });

export const createMilkTransaction = (sessionId: string) =>
  api<MilkTransaction>("/v1/milk-transactions", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });

/** Every step is one real call against the platform's own state machine. */
const step = (id: string, name: string, body: unknown) =>
  api<MilkTransaction>(`/v1/milk-transactions/${id}/${name}`, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });

export const identifySupplier = (id: string, supplierId: string) =>
  step(id, "identify", { method: "manual", supplier_id: supplierId });

export const captureMilk = (
  id: string,
  body: {
    milk_type: string;
    container_type: string;
    container_identifier: string;
    temperature_c?: number;
  },
) => step(id, "milk", body);

export const captureWeight = (
  id: string,
  body: { gross: number; tare: number },
) =>
  // `source: "manual"` is the domain's own name for an operator-entered
  // reading. The mock scale is refused outright in this environment.
  step(id, "weight", { source: "manual", unit: "kg", ...body });

export const captureQuality = (
  id: string,
  body: {
    fat: number;
    snf: number;
    clr: number;
    temperature_c?: number;
    remarks?: string;
  },
) => step(id, "quality", { source: "manual", ...body });

export const acceptTransaction = (id: string) => step(id, "accept", {});
export const rejectTransaction = (id: string, reason: string) =>
  step(id, "reject", { reason });
export const completeTransaction = (id: string) => step(id, "complete", {});

export const getMilkTransaction = (id: string) =>
  api<MilkTransaction>(`/v1/milk-transactions/${id}`);

/** DEMO-004: where one collection's money went. Stages are null until they happen. */
export type CollectionChain = {
  transaction_id: string;
  settlement: {
    id: string;
    settlement_number: string;
    status: string;
    period_from: string;
    period_to: string;
    currency: string;
    gross_amount: string | number;
    adjustments_amount: string | number;
    net_amount: string | number;
    line_amount: string | number;
    finalized_at: string | null;
  } | null;
  payment: {
    id: string;
    payment_number: string;
    status: string;
    method: string;
    currency: string;
    amount: string | number;
    allocated_amount: string | number;
    reference: string | null;
    paid_at: string | null;
  } | null;
  receipt: {
    id: string;
    receipt_number: string;
    status: string;
    net_amount: string | number;
    currency: string;
    generated_at: string;
  } | null;
};

export const getCollectionChain = (transactionId: string) =>
  api<CollectionChain>(`/v1/reports/collection/${transactionId}/chain`);

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
  /** What LACTEVA did: pending | sent | failed | dead. `sent` means the
   *  provider accepted the request — never that anything arrived. */
  status: string;
  provider: string | null;
  provider_reference: string | null;
  /** DEMO-028. What the PROVIDER said: accepted | sent | delivered | unknown.
   *  Null until a successful attempt, and `accepted` for every adapter this
   *  platform has today — none receives a delivery receipt. */
  provider_status: string | null;
  /** DEMO-028. The business record this message is about. */
  source_type: string | null;
  source_id: string | null;
  attempt_count: number;
  /** DEMO-029. When a verified provider receipt said it arrived. */
  delivered_at?: string | null;
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

export const getNotificationStats = () =>
  api<NotificationStats>("/v1/notifications/stats");

export const getNotification = (id: string) =>
  api<Notification>(`/v1/notifications/${id}`);

export const retryNotification = (id: string) =>
  api<Notification>(`/v1/notifications/${id}/retry`, { method: "POST" });

export const retryPendingNotifications = () =>
  api<{ retried: number; sent: number; failed: number }>(
    "/v1/notifications/retry-pending",
    {
      method: "POST",
    },
  );

// --- Recipient reachability (DEMO-029) -------------------------------------
//
// Who can be contacted before a communication run, and who cannot. It blocks
// nothing: a farmer with no phone number is still settled and still paid, and
// this exists so somebody can see them rather than a message going nowhere.

export type ReachabilityEntry = {
  subject_id: string;
  subject_type: string;
  name: string;
  channel: string;
  status: "reachable" | "unreachable" | "unknown";
  reason: string | null;
  /** Masked. The report must not become a list of farmers' phone numbers. */
  contact: string | null;
};

export type ReachabilitySummary = {
  template_key: string;
  channel: string;
  total: number;
  reachable: number;
  unreachable: number;
  unknown: number;
  reasons: Record<string, number>;
  affected: ReachabilityEntry[];
  affected_truncated: boolean;
};

export const getSettlementPeriodReachability = (from: string, to: string) =>
  api<ReachabilitySummary>(
    `/v1/notifications/reachability/settlement-period?period_from=${from}&period_to=${to}`,
  );

/**
 * Repair how a farmer is reached (DEMO-030).
 *
 * A PATCH of contact fields only. The full-profile PUT still exists; making an
 * operator resend `national_id` and `village` to fix a phone number is how a
 * forgotten field silently blanks a record.
 */
export const repairSupplierContact = (
  supplierId: string,
  body: { phone: string; locale?: string; reason?: string },
) =>
  api<{ full_name: string; phone: string }>(
    `/v1/suppliers/${supplierId}/contact`,
    { method: "PATCH", body: JSON.stringify(body) },
  );

export const getReachability = (templateKey: string, subjectType: string) =>
  api<ReachabilitySummary>(
    `/v1/notifications/reachability?template_key=${encodeURIComponent(templateKey)}` +
      `&subject_type=${encodeURIComponent(subjectType)}`,
  );

export const listNotificationTemplates = () =>
  api<NotificationTemplate[]>("/v1/notification-templates");

export const previewNotificationTemplate = (
  key: string,
  body: {
    channel: string;
    language?: string;
    variables: Record<string, string>;
  },
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

export const PAYMENT_METHODS = [
  "BANK_TRANSFER",
  "CASH",
  "CHEQUE",
  "MOBILE_MONEY",
] as const;

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
  if (params.outstanding_only === false)
    search.set("outstanding_only", "false");
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<BalancePageResult>(`/v1/payments/balances?${search.toString()}`);
}

export const getPaymentDetail = (id: string) =>
  api<PaymentDetail>(`/v1/payments/${id}`);

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
  return api<Payment>("/v1/payments", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export const paymentAction = (
  id: string,
  action: "submit" | "execute" | "retry" | "complete" | "fail" | "cancel",
  body: Record<string, string> = {},
) =>
  api<Payment>(`/v1/payments/${id}/${action}`, {
    method: "POST",
    body: JSON.stringify(body),
  });

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

export const getReceiptDetail = (id: string) =>
  api<ReceiptDetail>(`/v1/receipts/${id}`);

export const renderReceipt = (id: string, format: string) =>
  api<RenderedReceipt>(`/v1/receipts/${id}/render?format=${format}`);

export const receiptAction = (id: string, action: "deliver" | "archive") =>
  api<Receipt>(`/v1/receipts/${id}/${action}`, { method: "POST" });

/** Download URL for the artifact — served through the proxy, which streams
 *  `application/pdf` and its `Content-Disposition` through untouched. */
export const receiptDownloadUrl = (id: string, format: string) =>
  `${PROXY_PREFIX}/v1/receipts/${id}/download?format=${format}`;

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
  api<SyncOperation>(`/v1/sync/operations/${operationId}/retry`, {
    method: "POST",
  });

// --- Administration (PORTAL-001 / F-10) -------------------------------------
//
// The platform's administrative half had no portal surface at all: users,
// roles, organizations, the audit trail, configuration and backup status were
// reachable only by hand-crafting HTTP requests. Everything below uses the
// existing contracts — no backend endpoint was added for the portal.

export type User = {
  id: string;
  email: string;
  full_name: string;
  locale: string;
  /** DEMO-014: display timezone, or null for the organization's. */
  timezone?: string | null;
  is_active: boolean;
  /** DEMO-008 §9 — null means the account has never signed in. */
  last_login_at?: string | null;
  created_at?: string;
};

/** DEMO-013: the organization's locale context travels with the session, so
 *  no screen has to ask separately what money or clock it is rendering in. */
export type MeOrganization = {
  id: string;
  name: string;
  slug: string;
  country_code: string;
  currency_code: string;
  currency_symbol: string;
  timezone: string;
  default_language: string;
  supported_languages: string[];
  languages: { tag: string; name: string; endonym: string; rtl: boolean }[];
};
export type MeMembership = { status: string; joined_at: string };
export type MeRole = {
  name: string;
  description: string;
  center_id: string | null;
};

/**
 * The authorization context (DEMO-008 §13).
 *
 * The portal renders from this and from nothing else — there is no role string
 * compiled into the bundle. Hiding a control the backend would refuse is a
 * courtesy to the operator, not a security boundary: every one of these
 * permissions is re-checked server-side on the request the control would send.
 */
export type Me = {
  user: User;
  tenant_id: string | null;
  organization: MeOrganization | null;
  membership: MeMembership | null;
  roles: MeRole[];
  /** Centres this principal may act at; null means the whole organization. */
  center_scope: string[] | null;
  permissions: string[];
};

/** Who am I? A 401 means "nobody" — an answer, not an error to escape from,
 *  so this never triggers the redirect (LOOP-001). Prefer `getSession()` for
 *  a plain "am I signed in?": it answers 200 either way and leaves nothing in
 *  the browser console. */
export const getMe = () =>
  api<Me>("/v1/auth/me", undefined, { redirectOn401: false });

/** DEMO-013 — organization locale settings. */
export type LocaleSettings = {
  country_code: string;
  country_name: string;
  currency_code: string;
  currency_symbol: string;
  timezone: string;
  default_language: string;
  supported_languages: string[];
  languages: { tag: string; name: string; endonym: string; rtl: boolean }[];
};

export const getLocaleSettings = () =>
  api<LocaleSettings>("/v1/organizations/settings/locale");

export const updateLocaleSettings = (body: {
  currency_code?: string;
  timezone?: string;
  default_language?: string;
  supported_languages?: string[];
}) =>
  api<LocaleSettings>("/v1/organizations/settings/locale", {
    method: "PUT",
    body: JSON.stringify(body),
  });

/** A person's own display timezone, or null for the organization's.
 *  DEMO-014: display only — it cannot move a business date. */
export const setMyTimezone = (timezone: string | null) =>
  api<User>("/v1/auth/me/timezone", {
    method: "PUT",
    body: JSON.stringify({ timezone }),
  });

/** A person's own language. Not an administrative act — see the route. */
export const setMyLanguage = (language: string) =>
  api<User>("/v1/auth/me/language", {
    method: "PUT",
    body: JSON.stringify({ language }),
  });

export type CountryChoice = {
  code: string;
  name: string;
  currency_code: string;
  currency_symbol: string;
  timezone: string;
  default_language: string;
  supported_languages: string[];
};

export const listCountries = () =>
  api<{ countries: CountryChoice[] }>("/v1/locales/countries");

export type Session =
  | { authenticated: false; unreachable?: boolean }
  | ({ authenticated: true; acting_tenant_id: string | null } & Me);

/** Does this session hold `permission`? `*` is the platform wildcard. */
export function can(session: Session | null, permission: string): boolean {
  if (!session?.authenticated) return false;
  return (
    session.permissions.includes("*") ||
    session.permissions.includes(permission)
  );
}

/** The organization every request will be scoped to, whether it came from the
 *  token (a tenant user) or from the selection a platform admin made. */
export function actingTenant(session: Session | null): string | null {
  if (!session?.authenticated) return null;
  return session.tenant_id ?? session.acting_tenant_id ?? null;
}

/** TENANT-001: act inside an organization (platform-level sessions only). */
export async function setActingTenant(tenantId: string): Promise<void> {
  const res = await fetch("/api/auth/tenant", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_id: tenantId }),
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail;
    } catch {
      // keep statusText
    }
    throw new ApiError(res.status, detail);
  }
}

export async function clearActingTenant(): Promise<void> {
  await fetch("/api/auth/tenant", {
    method: "DELETE",
    credentials: "same-origin",
    cache: "no-store",
  });
}

/**
 * SESSION-001: the signed-in question, asked so that "no" is an answer.
 *
 * Same-origin, always 200, so the login page does not log a failed request
 * for being in its normal state.
 */
export async function getSession(): Promise<Session> {
  const res = await fetch("/api/auth/session", {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!res.ok) return { authenticated: false, unreachable: true };
  return (await res.json()) as Session;
}

export type MemberRole = { name: string; center_id: string | null };

export type Member = {
  user_id: string;
  status: string;
  joined_at: string;
  /** DEMO-008 §9 — the grants this person holds, from the same rows the
   *  permission engine reads. */
  roles?: MemberRole[];
};

export const listMembers = () => api<Member[]>("/v1/members");

export const getUser = (id: string) => api<User>(`/v1/identity/users/${id}`);

/**
 * The tenant's people, joined to their accounts.
 *
 * `/v1/members` carries membership only — user id, status, joined date — so
 * the names and addresses come from `/v1/identity/users/{id}`. One request per
 * member: honest for a cooperative's staff list, and the alternative is a new
 * backend endpoint that this work order is explicitly not to invent. A member
 * whose account cannot be read is kept in the list rather than dropped — a row
 * that says "unavailable" is information; a silently shorter list is not.
 */
export async function listPeople(): Promise<
  Array<Member & { user: User | null }>
> {
  const members = await listMembers();
  return Promise.all(
    members.map(async (m) => ({
      ...m,
      user: await getUser(m.user_id).catch(() => null),
    })),
  );
}

/** SEC-003 / F-02: deactivate or reactivate. An end state, not a verb. */
export const setUserActive = (id: string, isActive: boolean, reason?: string) =>
  api<User>(`/v1/identity/users/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ is_active: isActive, reason: reason || null }),
  });

export const listPermissions = () =>
  api<Record<string, string>>("/v1/authz/permissions");

export const createRole = (name: string, permissionKeys: string[]) =>
  api<{ id: string; name: string }>("/v1/authz/roles", {
    method: "POST",
    body: JSON.stringify({ name, permission_keys: permissionKeys }),
  });

export type Role = {
  id: string;
  name: string;
  description: string;
  tenant_id: string | null;
  system: boolean;
  permissions: string[];
  assignments: number;
};

/** The roles that actually exist. DEMO-008 — the page used to hard-code three
 *  names, one of which the backend had never had. */
export const listRoles = () => api<Role[]>("/v1/authz/roles");

export const assignRole = (
  userId: string,
  roleName: string,
  centerId?: string | null,
) =>
  api<{ id: string }>("/v1/authz/assignments", {
    method: "POST",
    body: JSON.stringify({
      user_id: userId,
      role_name: roleName,
      ...(centerId ? { center_id: centerId } : {}),
    }),
  });

/** Suspend or reinstate a member. Takes effect on their next request. */
export const setMemberStatus = (
  userId: string,
  status: "active" | "suspended",
) =>
  api<{ user_id: string; status: string }>(`/v1/members/${userId}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });

/** SEC-003 / F-02. Query parameters, not a body — see the route's comment. */
export const revokeRole = (userId: string, roleName: string) =>
  api<void>(
    `/v1/authz/assignments?user_id=${encodeURIComponent(userId)}&role_name=${encodeURIComponent(roleName)}`,
    { method: "DELETE" },
  );

export type Organization = {
  id: string;
  name: string;
  slug: string;
  country_code: string;
  status?: string;
};

export const getOrganization = (id: string) =>
  api<Organization>(`/v1/organizations/${id}`);

export type AuditRecord = {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  actor_id: string | null;
  request_id: string | null;
  created_at: string;
  detail: Record<string, unknown> | null;
};

export type AuditPageResult = {
  items: AuditRecord[];
  total: number;
  limit: number;
  offset: number;
};

/**
 * DEMO-007: `/v1/audit` was the one list on this platform that was not a page.
 * It returned the newest hundred records and nothing else, so the screen could
 * not answer "what did this operator do to that settlement" — and filtering
 * the rest in the browser would have been wrong from the 101st record on.
 */
export function listAudit(params: {
  q?: string;
  action?: string;
  resource_type?: string;
  actor_id?: string;
  date_from?: string;
  date_to?: string;
  limit: number;
  offset: number;
}): Promise<AuditPageResult> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.action) search.set("action", params.action);
  if (params.resource_type) search.set("resource_type", params.resource_type);
  if (params.actor_id) search.set("actor_id", params.actor_id);
  if (params.date_from) search.set("date_from", params.date_from);
  if (params.date_to) search.set("date_to", params.date_to);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<AuditPageResult>(`/v1/audit?${search.toString()}`);
}

export const listAuditActions = () => api<string[]>("/v1/audit/actions");

export const getConfig = (key: string) =>
  api<{ key: string; value: unknown }>(`/v1/config/${encodeURIComponent(key)}`);

export const setConfig = (
  key: string,
  value: unknown,
  scope: "tenant" | "global" = "tenant",
) =>
  api<{ key: string; scope: string; status: string }>(
    `/v1/config/${encodeURIComponent(key)}`,
    {
      method: "PUT",
      body: JSON.stringify({ value, scope }),
    },
  );

export type BackupStatus = {
  healthy: boolean;
  last_backup_at: string | null;
  last_verified_at: string | null;
  detail?: string;
  [key: string]: unknown;
};

export type BackupRun = {
  id: string;
  kind: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  error: string | null;
  [key: string]: unknown;
};

export const getBackupStatus = () =>
  api<BackupStatus>("/v1/_ops/backups/status");

export const listBackupRuns = (limit = 20) =>
  api<BackupRun[]>(`/v1/_ops/backups?limit=${limit}`);

// --- Sales: customers, deliveries, billing (DEMO-009) -----------------------
//
// The receivable side. Deliberately its own vocabulary: a customer is not a
// supplier, and an invoice is not a settlement.

export type Customer = {
  id: string;
  code: string;
  name: string;
  customer_type: string;
  phone: string;
  alternate_phone: string;
  address: string;
  notes: string;
  status: string;
  billing_mode: string;
  billing_day: number;
  currency: string;
  created_at: string;
  updated_at: string;
};

export type DeliveryPlan = {
  id: string;
  customer_id: string;
  product: string;
  default_quantity: string | number;
  quantity_unit: string;
  unit_price: string | number;
  currency: string;
  effective_from: string;
  active: boolean;

  // --- the standing order (DEMO-016) ---------------------------------------
  effective_to?: string | null;
  /** Seven characters, Monday first: "1111111" is every day. */
  weekdays?: string;
  slot?: string;
  center_id?: string | null;
  quantity_overrides?: Record<string, string> | null;
  paused_from?: string | null;
  paused_to?: string | null;
  /** A translation KEY — `schedule.daily`, `schedule.mon_sat`, … The platform
   *  never sends a sentence; the catalog decides what the reader sees. */
  schedule_key?: string;
  /** When this plan next delivers, or null if not within the year. */
  next_delivery?: string | null;
};

export type CustomerPageResult = {
  items: Customer[];
  total: number;
  limit: number;
  offset: number;
};

export type CustomerDetail = { customer: Customer; plans: DeliveryPlan[] };

export function listCustomers(params: {
  q?: string;
  status?: string;
  customer_type?: string;
  limit: number;
  offset: number;
}): Promise<CustomerPageResult> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  if (params.customer_type) search.set("customer_type", params.customer_type);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<CustomerPageResult>(`/v1/customers?${search.toString()}`);
}

export const getCustomer = (id: string) =>
  api<CustomerDetail>(`/v1/customers/${id}`);

export const createCustomer = (body: Record<string, unknown>) =>
  api<Customer>("/v1/customers", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const updateCustomer = (id: string, body: Record<string, unknown>) =>
  api<Customer>(`/v1/customers/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const setCustomerStatus = (id: string, status: string) =>
  api<Customer>(`/v1/customers/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });

/** Agree (or re-agree) what a customer takes, at what rate, and on which days.
 *  Supersedes the previous plan rather than editing it, so history keeps
 *  pointing at the plan that priced it (DEMO-016 §8). */
export const setDeliveryPlan = (
  id: string,
  body: {
    product?: string;
    default_quantity: string;
    quantity_unit?: string;
    unit_price: string;
    effective_from?: string;
    effective_to?: string | null;
    weekdays?: string;
    slot?: string;
    quantity_overrides?: Record<string, string> | null;
  },
) =>
  api<DeliveryPlan>(`/v1/customers/${id}/plan`, {
    method: "POST",
    body: JSON.stringify(body),
  });

/** Send a standing order on holiday. Generates nothing inside the window;
 *  touches no delivery that has already happened. */
export const pauseDeliveryPlan = (
  planId: string,
  body: { paused_from: string; paused_to?: string | null },
) =>
  api<DeliveryPlan>(`/v1/customers/plans/${planId}/pause`, {
    method: "POST",
    body: JSON.stringify(body),
  });

/** Back from holiday. Does NOT backfill the days that were paused. */
export const resumeDeliveryPlan = (planId: string) =>
  api<DeliveryPlan>(`/v1/customers/plans/${planId}/resume`, {
    method: "POST",
    body: JSON.stringify({}),
  });

export type GenerationRun = {
  id: string;
  business_date: string;
  status: "running" | "success" | "failed" | "holiday";
  trigger: "scheduler" | "manual";
  plans_due: number;
  created: number;
  already_present: number;
  not_due: number;
  inactive_customers: number;
  /** Due plans the calendar suppressed — the dairy, or the plan's centre, does
   *  not work on this business date (DEMO-022). */
  skipped_holiday: number;
  attempts: number;
  error: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number;
};

/** What the scheduler has been doing (DEMO-017 §10). Newest first. */
export const listGenerationRuns = (limit = 14) =>
  api<GenerationRun[]>(`/v1/deliveries/generation-runs?limit=${limit}`);

export type GenerationResult = {
  business_date: string;
  due: number;
  created: number;
  already_present: number;
  not_due: number;
  inactive_customers: number;
  /** Always 0 for a manual run: manual generation is not calendar-suppressed. */
  skipped_holiday: number;
};

/** Turn today's standing orders into the day's round. Safe to run twice —
 *  idempotency is a database constraint, so a second call returns
 *  `created: 0` rather than a duplicated round. */
export const generateDeliveries = (body: { for_date?: string } = {}) =>
  api<GenerationResult>("/v1/deliveries/generate", {
    method: "POST",
    body: JSON.stringify(body),
  });

export type Delivery = {
  id: string;
  customer_id: string;
  delivery_date: string;
  slot: string;
  product: string;
  quantity: string | number;
  quantity_unit: string;
  unit_price: string | number;
  currency: string;
  amount: string | number;
  status: string;
  notes: string;
  invoice_id: string | null;
  plan_id: string | null;
  created_at: string;
};

export type DeliveryPageResult = {
  items: Delivery[];
  total: number;
  limit: number;
  offset: number;
  /** Totals for the WHOLE filtered set, computed by the database. */
  total_quantity: string | number;
  total_amount: string | number;
};

export function listDeliveries(params: {
  customer_id?: string;
  date_from?: string;
  date_to?: string;
  status?: string;
  invoiced?: boolean;
  limit: number;
  offset: number;
}): Promise<DeliveryPageResult> {
  const search = new URLSearchParams();
  if (params.customer_id) search.set("customer_id", params.customer_id);
  if (params.date_from) search.set("date_from", params.date_from);
  if (params.date_to) search.set("date_to", params.date_to);
  if (params.status) search.set("status", params.status);
  if (params.invoiced !== undefined)
    search.set("invoiced", String(params.invoiced));
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<DeliveryPageResult>(`/v1/deliveries?${search.toString()}`);
}

export const recordDelivery = (body: {
  customer_id: string;
  delivery_date: string;
  slot?: string;
  quantity?: string;
  status?: string;
  notes?: string;
}) =>
  api<Delivery>("/v1/deliveries", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const amendDelivery = (
  id: string,
  body: { quantity?: string; status?: string; notes?: string },
) =>
  api<Delivery>(`/v1/deliveries/${id}/amend`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export type DeliveryDayRow = {
  delivery_date: string;
  deliveries: number;
  customers: number;
  quantity: string | number;
  amount: string | number;
};

export type DeliveryCustomerRow = {
  customer_id: string;
  code: string;
  name: string;
  product: string;
  deliveries: number;
  quantity: string | number;
  /** Null when this customer's deliveries in the window disagree about the
   *  rate — the platform declines to average two rates into one. */
  unit_price: string | number | null;
  amount: string | number;
  skipped: number;
};

export type DeliveryReport = {
  date_from: string;
  date_to: string;
  /** The organization's own currency (DEMO-015). No screen decides this. */
  currency: string;
  quantity_unit: string;
  deliveries: number;
  customers_served: number;
  total_quantity: string | number;
  total_amount: string | number;
  skipped: number;
  /** Generated and not yet acted on — the operator's "how many are left?" */
  scheduled?: number;
  /** The size of the day's round: completed + skipped + still scheduled. */
  planned?: number;
  /** How much milk the round INTENDED, in litres (DEMO-019 §5). Compared with
   *  `total_quantity` this is the shortfall, which is the question a dairy
   *  manager actually asks at the end of a day. */
  planned_quantity?: string | number;
  returned?: number;
  cancelled?: number;
  by_day: DeliveryDayRow[];
  by_customer: DeliveryCustomerRow[];
};

export function getDeliveryReport(params: {
  date_from: string;
  date_to: string;
  customer_id?: string;
}): Promise<DeliveryReport> {
  const search = new URLSearchParams({
    date_from: params.date_from,
    date_to: params.date_to,
  });
  if (params.customer_id) search.set("customer_id", params.customer_id);
  return api<DeliveryReport>(`/v1/deliveries/report?${search.toString()}`);
}

/** The report as a file, streamed through the proxy with its
 *  `Content-Disposition` intact — the browser saves it, nothing is built in
 *  JavaScript, and the totals are the platform's own. */
export function deliveryReportCsvUrl(params: {
  date_from: string;
  date_to: string;
  customer_id?: string;
  status?: string;
}): string {
  const search = new URLSearchParams({
    date_from: params.date_from,
    date_to: params.date_to,
  });
  if (params.customer_id) search.set("customer_id", params.customer_id);
  if (params.status) search.set("status", params.status);
  return `${PROXY_PREFIX}/v1/deliveries/report.csv?${search.toString()}`;
}

export type Invoice = {
  id: string;
  customer_id: string;
  invoice_number: string;
  period_from: string;
  period_to: string;
  currency: string;
  subtotal: string | number;
  adjustments: string | number;
  total: string | number;
  previous_balance: string | number;
  amount_due: string | number;
  status: string;
  line_count: number;
  issued_at: string | null;
  created_at: string;
};

export type InvoiceLine = {
  id: string;
  delivery_id: string;
  delivery_date: string;
  slot: string;
  product: string;
  quantity: string | number;
  quantity_unit: string;
  unit_price: string | number;
  amount: string | number;
};

export type InvoicePageResult = {
  items: Invoice[];
  total: number;
  limit: number;
  offset: number;
};

export type InvoiceDetail = {
  invoice: Invoice;
  lines: InvoiceLine[];
  paid: string | number;
  outstanding: string | number;
  totals_match_lines: boolean;
};

export function listInvoices(params: {
  customer_id?: string;
  status?: string;
  q?: string;
  limit: number;
  offset: number;
}): Promise<InvoicePageResult> {
  const search = new URLSearchParams();
  if (params.customer_id) search.set("customer_id", params.customer_id);
  if (params.status) search.set("status", params.status);
  if (params.q) search.set("q", params.q);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<InvoicePageResult>(`/v1/invoices?${search.toString()}`);
}

export const getInvoice = (id: string) =>
  api<InvoiceDetail>(`/v1/invoices/${id}`);

export const generateInvoice = (body: {
  customer_id: string;
  period_from: string;
  period_to: string;
}) =>
  api<Invoice>("/v1/invoices", { method: "POST", body: JSON.stringify(body) });

export const issueInvoice = (id: string) =>
  api<Invoice>(`/v1/invoices/${id}/issue`, { method: "POST", body: "{}" });

export const cancelInvoice = (id: string, reason: string) =>
  api<Invoice>(`/v1/invoices/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export type CustomerPayment = {
  id: string;
  customer_id: string;
  payment_number: string;
  amount: string | number;
  currency: string;
  method: string;
  reference: string;
  status: string;
  notes: string;
  received_at: string;
  created_at: string;
};

export type CustomerPaymentPageResult = {
  items: CustomerPayment[];
  total: number;
  limit: number;
  offset: number;
};

export type CustomerPaymentDetail = {
  payment: CustomerPayment;
  allocations: {
    invoice_id: string;
    invoice_number: string;
    amount: string | number;
  }[];
  receipt_number: string | null;
};

export const CUSTOMER_PAYMENT_METHODS = [
  "CASH",
  "MOBILE_MONEY",
  "BANK_TRANSFER",
  "CHEQUE",
] as const;

export function listCustomerPayments(params: {
  customer_id?: string;
  method?: string;
  q?: string;
  limit: number;
  offset: number;
}): Promise<CustomerPaymentPageResult> {
  const search = new URLSearchParams();
  if (params.customer_id) search.set("customer_id", params.customer_id);
  if (params.method) search.set("method", params.method);
  if (params.q) search.set("q", params.q);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<CustomerPaymentPageResult>(
    `/v1/customer-payments?${search.toString()}`,
  );
}

export const getCustomerPayment = (id: string) =>
  api<CustomerPaymentDetail>(`/v1/customer-payments/${id}`);

export const recordCustomerPayment = (body: {
  customer_id: string;
  amount: string;
  method: string;
  reference?: string;
  notes?: string;
  invoice_ids?: string[];
}) =>
  api<CustomerPayment>("/v1/customer-payments", {
    method: "POST",
    body: JSON.stringify(body),
  });

export type CustomerBalance = {
  customer_id: string;
  currency: string;
  invoiced: string | number;
  paid: string | number;
  outstanding: string | number;
  unbilled_amount: string | number;
  unbilled_deliveries: number;
  open_invoices: number;
};

export const getCustomerBalance = (id: string) =>
  api<CustomerBalance>(`/v1/customers/${id}/balance`);

export type StatementEntry = {
  entry_date: string;
  kind: "invoice" | "payment";
  reference: string;
  detail: string;
  debit: string | number;
  credit: string | number;
  balance: string | number;
};

export type CustomerStatement = {
  customer_id: string;
  code: string;
  name: string;
  currency: string;
  date_from: string;
  date_to: string;
  opening_balance: string | number;
  billed: string | number;
  paid: string | number;
  closing_balance: string | number;
  /** How much milk the money is for (DEMO-019 §7). */
  delivered_quantity?: string | number;
  quantity_unit?: string;
  entries: StatementEntry[];
};

/** How a balance came about (DEMO-015 §13). Dates are OPTIONAL: omit them and
 *  the platform answers for the dairy's own current month, which is the only
 *  way a browser can ask for "this month" without a timezone database. */
export function getCustomerStatement(
  id: string,
  params?: { date_from?: string; date_to?: string },
): Promise<CustomerStatement> {
  const search = new URLSearchParams();
  if (params?.date_from) search.set("date_from", params.date_from);
  if (params?.date_to) search.set("date_to", params.date_to);
  const query = search.toString();
  return api<CustomerStatement>(
    `/v1/customers/${id}/statement${query ? `?${query}` : ""}`,
  );
}

export type CustomerReceipt = {
  id: string;
  receipt_number: string;
  payment_id: string;
  payment_number: string;
  customer_id: string;
  customer_name: string;
  customer_code: string;
  amount: string | number;
  currency: string;
  method: string;
  reference: string;
  applied_to: string;
  generated_at: string;
};

export function listCustomerReceipts(params: {
  customer_id?: string;
  q?: string;
  limit: number;
  offset: number;
}): Promise<{
  items: CustomerReceipt[];
  total: number;
  limit: number;
  offset: number;
}> {
  const search = new URLSearchParams();
  if (params.customer_id) search.set("customer_id", params.customer_id);
  if (params.q) search.set("q", params.q);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  return api<{
    items: CustomerReceipt[];
    total: number;
    limit: number;
    offset: number;
  }>(`/v1/customer-receipts?${search.toString()}`);
}

// --- Business calendar and financial periods (DEMO-020) --------------------

export type FinancialPeriodView = {
  id: string;
  period_start: string;
  period_end: string;
  status: string;
  label: string;
  closed_at: string | null;
};

/** What the PLATFORM says the organization's calendar is.
 *
 * Every field here is computed on the server from the organization's own
 * timezone. The portal deliberately does not derive any of it: a browser that
 * decided which month it was would be a second implementation of the rule
 * DEMO-019 spent a milestone consolidating.
 */
export type OrganizationCalendar = {
  timezone: string;
  business_date: string;
  is_working_day: boolean;
  month_start: string;
  month_end: string;
  previous_month_start: string;
  previous_month_end: string;
  current_period: FinancialPeriodView | null;
};

export const getOrganizationCalendar = () =>
  api<OrganizationCalendar>("/v1/organization/calendar");

export const getFinancialPeriods = () =>
  api<FinancialPeriodView[]>("/v1/organization/financial-periods");

export type CalendarDayView = {
  id: string;
  day: string;
  working: boolean;
  kind: string;
  name: string;
};

export const getCalendarDays = (from: string, to: string) =>
  api<CalendarDayView[]>(
    `/v1/organization/calendar/days?date_from=${from}&date_to=${to}`,
  );

export const openFinancialPeriod = (body: {
  period_start: string;
  period_end: string;
  label?: string;
}) =>
  api<FinancialPeriodView>("/v1/organization/financial-periods", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const closeFinancialPeriod = (id: string) =>
  api<FinancialPeriodView>(`/v1/organization/financial-periods/${id}/close`, {
    method: "POST",
  });

export const reopenFinancialPeriod = (id: string) =>
  api<FinancialPeriodView>(`/v1/organization/financial-periods/${id}/reopen`, {
    method: "POST",
  });

// --- Subscription, trial and entitlement (DEMO-026) ------------------------

export type SubscriptionView = {
  plan_code: string;
  plan_name: string;
  status: "trialing" | "active" | "past_due" | "cancelled" | "expired";
  trial_started_on: string | null;
  trial_ends_on: string | null;
  started_on: string | null;
  current_period_end: string | null;
  subscribed_centres: number;
  billing_period: string;
  currency_code: string;
  /** Null until a deployment has decided what this plan costs. */
  price: string | null;
};

export type EntitlementView = {
  status: string;
  business_date: string;
  trial_days_remaining: number | null;
  can_operate: boolean;
  can_read: boolean;
  active_centres: number;
  subscribed_centres: number;
  centre_allowance: number | null;
  within_centre_allowance: boolean;
  /** DEMO-027. When a past_due subscription stops operating. */
  grace_ends_on: string | null;
  current_period_end: string | null;
};

export const getSubscription = () =>
  api<SubscriptionView>("/v1/organization/subscription");

export const getEntitlement = () =>
  api<EntitlementView>("/v1/organization/entitlement");

// --- Subscription payment (DEMO-027) ---------------------------------------
//
// Note what the client may SEND: a plan code and a number of collection
// centres. Never an amount, never a currency, never a status. Those are the
// server's, and a type that could express them here would be the first step to
// a browser naming its own price.

export type QuoteView = {
  plan_code: string;
  plan_name: string;
  currency_code: string;
  /** Per collection centre, per period. Null until a price is published. */
  unit_price: string | null;
  quantity: number;
  amount: string | null;
  billing_period: string;
  active_centres: number;
  /** Whether this deployment can take money at all. */
  payable: boolean;
  payable_reason: string | null;
};

export type SubscriptionPaymentView = {
  id: string;
  plan_code: string;
  unit_price: string;
  quantity: number;
  amount: string;
  currency_code: string;
  status: "pending" | "succeeded" | "failed" | "cancelled";
  provider: string;
  provider_reference: string | null;
  checkout_url: string | null;
  failure_code: string | null;
  failure_message: string | null;
  created_at: string;
  completed_at: string | null;
};

export const getSubscriptionQuote = (planCode: string, centres: number) =>
  api<QuoteView>(
    `/v1/organization/subscription/quote?plan_code=${encodeURIComponent(planCode)}` +
      `&subscribed_centres=${centres}`,
  );

export const startSubscriptionCheckout = (planCode: string, centres: number) =>
  api<SubscriptionPaymentView>("/v1/organization/subscription/checkout", {
    method: "POST",
    body: JSON.stringify({
      plan_code: planCode,
      subscribed_centres: centres,
    }),
  });

/**
 * Ask the SERVER to ask the provider. Takes no arguments deliberately — a
 * browser back from a hosted checkout knows only that something may have
 * changed, never what.
 */
export const refreshSubscriptionCheckout = () =>
  api<SubscriptionPaymentView>("/v1/organization/subscription/checkout/refresh", {
    method: "POST",
  });

export const cancelSubscriptionCheckout = () =>
  api<SubscriptionPaymentView>("/v1/organization/subscription/checkout/cancel", {
    method: "POST",
  });

export const getSubscriptionPayments = () =>
  api<SubscriptionPaymentView[]>("/v1/organization/subscription/payments");
