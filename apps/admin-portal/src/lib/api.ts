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
  unit_price: number;
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
  unit_price: number;
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
