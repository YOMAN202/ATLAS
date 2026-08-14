import type { AtlasRole } from "./roles";
import type {
  CalibrationResult,
  DataQualitySummary,
  ExecutiveSummary,
  ExperimentRow,
  ForecastRow,
  ForecastSummary,
  InventoryPolicyRow,
  InventoryPolicySummary,
  InventoryRow,
  InventorySummary,
  OperationalSummary,
  OrderLineRow,
  PageEnvelope,
  ProcurementRow,
  ProcurementSummary,
  QuarantineRow,
  SalesSummary,
  SensitivityScenario,
  ServiceLevelRow,
  ServiceLevelSummary,
  ShipmentRow,
  SupplierDeliveryRow,
  SupplierRiskRow,
  SupplierRiskSummary,
  SupplierSummary,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

type QueryParams = Record<string, string | number | boolean | null | undefined>;

function buildQuery(params?: QueryParams): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

async function apiGet<T>(path: string, role: AtlasRole, params?: QueryParams): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}${buildQuery(params)}`, {
    headers: { "X-Atlas-Role": role },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export interface DateRangeFilter {
  date_from?: string;
  date_to?: string;
}

export interface PageFilter {
  page?: number;
  page_size?: number;
}

export const api = {
  executive: {
    summary: (role: AtlasRole, params?: DateRangeFilter & { region_key?: number }) =>
      apiGet<ExecutiveSummary>("/api/v1/dashboards/executive", role, params),
  },
  sales: {
    summary: (role: AtlasRole, params?: DateRangeFilter & { product_key?: number; customer_key?: number }) =>
      apiGet<SalesSummary>("/api/v1/dashboards/sales", role, params),
    detail: (role: AtlasRole, params?: DateRangeFilter & PageFilter & { product_key?: number; customer_key?: number }) =>
      apiGet<PageEnvelope<OrderLineRow>>("/api/v1/dashboards/sales/detail", role, params),
  },
  inventory: {
    summary: (role: AtlasRole, params?: DateRangeFilter & { product_key?: number; warehouse_key?: number }) =>
      apiGet<InventorySummary>("/api/v1/dashboards/inventory", role, params),
    detail: (
      role: AtlasRole,
      params?: DateRangeFilter & PageFilter & { product_key?: number; warehouse_key?: number }
    ) => apiGet<PageEnvelope<InventoryRow>>("/api/v1/dashboards/inventory/detail", role, params),
  },
  procurement: {
    summary: (
      role: AtlasRole,
      params?: DateRangeFilter & { supplier_key?: number; product_key?: number; warehouse_key?: number }
    ) => apiGet<ProcurementSummary>("/api/v1/dashboards/procurement", role, params),
    detail: (
      role: AtlasRole,
      params?: DateRangeFilter & PageFilter & { supplier_key?: number; product_key?: number; warehouse_key?: number }
    ) => apiGet<PageEnvelope<ProcurementRow>>("/api/v1/dashboards/procurement/detail", role, params),
  },
  supplier: {
    summary: (role: AtlasRole, params?: DateRangeFilter & { supplier_key?: number; product_key?: number }) =>
      apiGet<SupplierSummary>("/api/v1/dashboards/supplier", role, params),
    detail: (role: AtlasRole, params?: DateRangeFilter & PageFilter & { supplier_key?: number; product_key?: number }) =>
      apiGet<PageEnvelope<SupplierDeliveryRow>>("/api/v1/dashboards/supplier/detail", role, params),
  },
  operational: {
    summary: (role: AtlasRole, params?: DateRangeFilter & { carrier_key?: number; warehouse_key?: number }) =>
      apiGet<OperationalSummary>("/api/v1/dashboards/operational", role, params),
    detail: (
      role: AtlasRole,
      params?: DateRangeFilter & PageFilter & { carrier_key?: number; warehouse_key?: number }
    ) => apiGet<PageEnvelope<ShipmentRow>>("/api/v1/dashboards/operational/detail", role, params),
  },
  dataQuality: {
    summary: (role: AtlasRole) => apiGet<DataQualitySummary>("/api/v1/dashboards/data-quality", role),
    quarantine: (
      role: AtlasRole,
      params?: PageFilter & { etl_run_id?: number; source_table?: string; rule_violated?: string }
    ) => apiGet<PageEnvelope<QuarantineRow>>("/api/v1/dashboards/data-quality/quarantine", role, params),
  },
  planning: {
    summary: (role: AtlasRole) => apiGet<ForecastSummary>("/api/v1/dashboards/planning/forecast/summary", role),
    detail: (
      role: AtlasRole,
      params?: PageFilter & {
        grain_type?: "sku_warehouse" | "category" | "region";
        product_key?: number;
        warehouse_key?: number;
        category?: string;
        region_key?: number;
        date_from?: string;
        date_to?: string;
      }
    ) => apiGet<PageEnvelope<ForecastRow>>("/api/v1/dashboards/planning/forecast/detail", role, params),
    experiments: (role: AtlasRole) =>
      apiGet<ExperimentRow[]>("/api/v1/dashboards/planning/forecast/experiments", role),
  },
  supplierRisk: {
    summary: (role: AtlasRole) =>
      apiGet<SupplierRiskSummary>("/api/v1/dashboards/planning/supplier-risk/summary", role),
    detail: (
      role: AtlasRole,
      params?: PageFilter & { risk_classification?: "Low" | "Medium" | "High" }
    ) =>
      apiGet<PageEnvelope<SupplierRiskRow>>(
        "/api/v1/dashboards/planning/supplier-risk/detail",
        role,
        params
      ),
  },
  serviceLevel: {
    summary: (role: AtlasRole) =>
      apiGet<ServiceLevelSummary>("/api/v1/dashboards/planning/service-level/summary", role),
    calibration: (role: AtlasRole) =>
      apiGet<CalibrationResult[]>("/api/v1/dashboards/planning/service-level/calibration", role),
    detail: (
      role: AtlasRole,
      params?: PageFilter & { min_stockout?: number; min_backorder?: number; min_delay?: number }
    ) =>
      apiGet<PageEnvelope<ServiceLevelRow>>(
        "/api/v1/dashboards/planning/service-level/detail",
        role,
        params
      ),
  },
  inventoryPolicy: {
    summary: (role: AtlasRole) =>
      apiGet<InventoryPolicySummary>("/api/v1/dashboards/planning/inventory-policy/summary", role),
    sensitivity: (role: AtlasRole) =>
      apiGet<SensitivityScenario[]>(
        "/api/v1/dashboards/planning/inventory-policy/sensitivity",
        role
      ),
    detail: (
      role: AtlasRole,
      params?: PageFilter & {
        balancing_recommendation?: "reorder_now" | "adequate" | "excess_inventory";
      }
    ) =>
      apiGet<PageEnvelope<InventoryPolicyRow>>(
        "/api/v1/dashboards/planning/inventory-policy/detail",
        role,
        params
      ),
  },
};
