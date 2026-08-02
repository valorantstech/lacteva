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
    try {
      const body = (await res.json()) as { detail?: string; title?: string };
      detail = body.detail ?? body.title ?? detail;
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(res.status, detail);
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
