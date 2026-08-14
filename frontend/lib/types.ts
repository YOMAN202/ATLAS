// Hand-typed to mirror backend/app/api/v1/*.py's Pydantic response models
// exactly (docs/phase6-dashboard-proposal.md §4 notes this as a
// deliberate simplification — no OpenAPI codegen step — for this
// phase's scope; a future pass could generate these instead of
// hand-maintaining them).

export interface AsOf {
  etl_run_id: number;
  date_from: string | null;
  date_to: string | null;
}

export interface PageEnvelope<T> {
  data: T[];
  page: number;
  page_size: number;
  total: number;
}

// --- Executive ---

export interface DailyRevenuePoint {
  full_date: string;
  total_revenue: number;
  total_gross_margin: number;
}

export interface ExecutiveSummary {
  as_of: AsOf;
  total_revenue: number;
  total_gross_margin: number;
  total_orders: number;
  total_order_lines: number;
  order_fulfillment_rate: number | null;
  cost_to_serve: null;
  cost_to_serve_note: string;
  daily_trend: DailyRevenuePoint[];
}

// --- Sales ---

export interface SalesSummary {
  as_of: AsOf;
  total_order_lines: number;
  distinct_orders: number;
  ordered_quantity: number;
  allocated_quantity: number;
  backordered_quantity: number;
  fulfillment_rate: number | null;
  average_order_value: number | null;
}

export interface OrderLineRow {
  source_order_line_id: number;
  order_number: string;
  order_line_number: number;
  product_key: number;
  customer_key: number;
  ordered_quantity: number;
  allocated_quantity: number;
  backordered_quantity: number;
  unit_price: number;
  extended_revenue: number;
  gross_margin: number;
}

// --- Inventory ---

export interface InventorySummary {
  as_of: AsOf;
  latest_snapshot_date: string | null;
  total_quantity_on_hand: number;
  total_inventory_value: number;
  stockout_rate: number | null;
  inventory_turnover: number | null;
  days_of_supply: number | null;
  overstock_value: null;
  overstock_value_note: string;
}

export interface InventoryRow {
  product_key: number;
  warehouse_key: number;
  snapshot_date: string;
  quantity_on_hand: number;
  quantity_available: number;
  inventory_value: number;
  is_stockout: boolean;
}

// --- Procurement ---

export interface ProcurementSummary {
  as_of: AsOf;
  total_po_lines: number;
  total_spend: number;
  average_unit_cost: number | null;
  ordered_quantity: number;
  received_quantity: number;
  receipt_rate: number | null;
  quality_rejected_quantity: number;
  quality_rejection_rate: number | null;
}

export interface ProcurementRow {
  source_po_line_id: number;
  po_number: string;
  po_status_code: string;
  supplier_key: number;
  product_key: number;
  warehouse_key: number;
  ordered_quantity: number;
  unit_cost: number;
  extended_cost: number;
  received_quantity: number;
  quality_rejected_quantity: number;
}

// --- Supplier ---

export interface SupplierSummary {
  as_of: AsOf;
  total_deliveries: number;
  on_time_delivery_rate: number | null;
  average_lead_time_variance_days: number | null;
  quality_rejection_rate: number | null;
  risk_score: null;
  risk_score_note: string;
}

export interface SupplierDeliveryRow {
  source_po_line_id: number;
  po_number: string;
  supplier_key: number;
  product_key: number;
  warehouse_key: number;
  received_quantity: number;
  quality_rejected_quantity: number;
  is_on_time: boolean;
  lead_time_variance_days: number;
}

// --- Operational ---

export interface WarehouseCapacityRow {
  warehouse_key: number;
  warehouse_name: string;
  total_capacity_units: number;
  quantity_on_hand: number;
  capacity_utilization: number | null;
}

export interface OperationalSummary {
  as_of: AsOf;
  total_shipments: number;
  on_time_delivery_rate: number | null;
  on_time_delivery_rate_note: string | null;
  average_cost_per_mile: number | null;
  average_cost_per_shipment: number | null;
  average_transit_days: number | null;
  pick_accuracy: null;
  pick_accuracy_note: string;
  zone_throughput: null;
  zone_throughput_note: string;
  warehouse_capacity: WarehouseCapacityRow[];
}

export interface ShipmentRow {
  source_shipment_id: number;
  shipment_number: string;
  status_code: string;
  carrier_key: number;
  origin_warehouse_key: number;
  distance_miles: number | null;
  shipping_cost: number | null;
  is_on_time: boolean | null;
  transit_days: number | null;
}

// --- Data Quality ---

export interface TableQualityRow {
  source_table: string;
  extracted_count: number;
  quarantined_count: number;
  rejected_count: number;
  dq_score: number | null;
}

export interface RunTrendPoint {
  etl_run_id: number;
  started_at: string;
  stage: string;
  overall_dq_score: number | null;
  total_extracted: number;
  total_quarantined: number;
}

export interface DataQualitySummary {
  etl_run_id: number;
  overall_dq_score: number | null;
  quarantine_rate: number | null;
  referential_integrity_failure_rate: number | null;
  duration_seconds: number;
  per_table: TableQualityRow[];
  run_trend: RunTrendPoint[];
}

export interface QuarantineRow {
  id: number;
  etl_run_id: number;
  source_table: string;
  source_id: number | null;
  rule_violated: string;
  rule_detail: string;
  quarantined_at: string;
}

// --- Planning (Phase 7 Module A: Demand Forecasting) ---

export interface ActiveModelInfo {
  model_id: number;
  model_name: string;
  parameters: Record<string, number>;
  weighted_avg_mape: number | null;
  baseline_mape: number | null;
}

export interface ForecastSummary {
  etl_run_id: number;
  active_model: ActiveModelInfo | null;
  forecast_horizon_days: number;
  total_predicted_demand_next_30d: number;
  forecast_generated_at: string | null;
  n_sku_warehouse_series: number;
  n_category_series: number;
  n_region_series: number;
}

export interface ForecastRow {
  grain_type: string;
  product_key: number | null;
  warehouse_key: number | null;
  category: string | null;
  region_key: number | null;
  forecast_date: string;
  predicted_quantity: number;
  confidence_interval_low: number | null;
  confidence_interval_high: number | null;
  model_name: string;
}

export interface ExperimentRow {
  model_name: string;
  series_scope: string;
  metric_value: number | null;
  baseline_metric_value: number | null;
  n_observations: number;
  test_start_date: string;
  test_end_date: string;
}

// --- Planning (Phase 7 Module C: Supplier Intelligence) ---

export interface ClassificationBreakdown {
  low: number;
  medium: number;
  high: number;
}

export interface SupplierRiskSummary {
  etl_run_id: number;
  model_id: number | null;
  model_name: string | null;
  scoring_weights: Record<string, number> | null;
  generated_at: string | null;
  n_suppliers: number;
  avg_risk_score: number | null;
  classification_breakdown: ClassificationBreakdown;
}

export interface SupplierRiskRow {
  supplier_key: number;
  risk_score: number;
  risk_classification: "Low" | "Medium" | "High";
  on_time_rate: number;
  quality_rejection_rate: number;
  fill_rate: number;
  lead_time_stddev_days: number;
  on_time_rate_trend_delta: number;
  trend_direction: "improving" | "stable" | "degrading";
  total_spend: number;
  share_of_total_spend: number;
  distinct_products_supplied: number;
  distinct_warehouses_served: number;
  n_deliveries: number;
  triggering_metrics: string[];
}

// --- Planning (Phase 7 Module D: Service-Level Prediction) ---

export interface ServiceLevelSummary {
  etl_run_id: number;
  model_id: number | null;
  model_name: string | null;
  source_forecast_model_id: number | null;
  source_supplier_model_id: number | null;
  generated_at: string | null;
  n_predictions: number;
  n_with_delay_prediction: number;
  avg_stockout_probability: number | null;
  avg_backorder_probability: number | null;
  avg_fulfillment_delay_probability: number | null;
  n_high_stockout_risk: number;
}

export interface CalibrationBucketRow {
  bucket_index: number;
  predicted_probability_mean: number;
  actual_outcome_rate: number;
  n_observations: number;
}

export interface CalibrationResult {
  prediction_type: string;
  brier_score: number;
  baseline_brier_score: number;
  n_observations: number;
  test_start_date: string;
  test_end_date: string;
  buckets: CalibrationBucketRow[];
}

export interface ServiceLevelRow {
  product_key: number;
  warehouse_key: number;
  stockout_probability: number;
  stockout_confidence: string;
  stockout_contributing_factors: Record<string, unknown>;
  backorder_probability: number;
  backorder_confidence: string;
  backorder_contributing_factors: Record<string, unknown>;
  fulfillment_delay_probability: number | null;
  fulfillment_delay_confidence: string | null;
  fulfillment_delay_contributing_factors: Record<string, unknown> | null;
  primary_supplier_key: number | null;
}

// --- Planning (Phase 7 Module B: Inventory Optimization) ---

export interface BalancingBreakdown {
  reorder_now: number;
  adequate: number;
  excess_inventory: number;
}

export interface InventoryPolicySummary {
  etl_run_id: number;
  model_id: number | null;
  model_name: string | null;
  source_forecast_model_id: number | null;
  source_supplier_model_id: number | null;
  source_service_level_model_id: number | null;
  generated_at: string | null;
  n_recommendations: number;
  avg_safety_stock: number | null;
  avg_reorder_point: number | null;
  balancing_breakdown: BalancingBreakdown;
}

export interface SensitivityScenario {
  target_service_level: number;
  avg_safety_stock: number;
  avg_reorder_point: number;
  total_inventory_investment: number;
  achieved_service_level: number;
  n_pairs: number;
}

export interface InventoryPolicyRow {
  product_key: number;
  warehouse_key: number;
  safety_stock: number;
  reorder_point: number;
  service_level_inventory_target: number;
  current_available_quantity: number;
  balancing_recommendation: "reorder_now" | "adequate" | "excess_inventory";
  confidence: string;
  contributing_factors: Record<string, unknown>;
  business_rationale: string;
  primary_supplier_key: number | null;
}

// --- Planning (Phase 7.2 Module E: Scenario Simulation) ---

export interface ScenarioSummary {
  id: number;
  scenario_type: string;
  scenario_name: string;
  description: string;
  parameters: Record<string, unknown>;
  scenario_avg_stockout_probability: number;
  scenario_avg_service_level: number;
  scenario_inventory_investment: number;
  stockout_probability_delta: number;
  service_level_delta: number;
  investment_delta: number;
  confidence: string;
}

export interface ScenarioResultDetail {
  id: number;
  scenario_type: string;
  scenario_name: string;
  description: string;
  parameters: Record<string, unknown>;
  baseline_avg_stockout_probability: number;
  scenario_avg_stockout_probability: number;
  baseline_n_high_stockout_risk: number;
  scenario_n_high_stockout_risk: number;
  baseline_avg_backorder_probability: number;
  scenario_avg_backorder_probability: number;
  baseline_inventory_investment: number;
  scenario_inventory_investment: number;
  baseline_avg_service_level: number;
  scenario_avg_service_level: number;
  baseline_procurement_volume: number;
  scenario_procurement_volume: number;
  baseline_n_suppliers_utilized: number;
  scenario_n_suppliers_utilized: number;
  changed_assumptions: Record<string, unknown>;
  affected_modules: string[];
  key_drivers: string[];
  confidence: string;
  sensitivity_indicators: Record<string, number>;
  n_pairs_evaluated: number;
  source_forecast_model_id: number | null;
  source_supplier_model_id: number | null;
  source_service_level_model_id: number | null;
  source_inventory_policy_model_id: number | null;
  generated_at: string | null;
}

// --- Planning (Phase 7.2 Module F: Route & Cost Optimization) ---

export interface OptimizationSummary {
  etl_run_id: number;
  model_id: number | null;
  model_name: string | null;
  generated_at: string | null;
  analysis_window_start: string | null;
  analysis_window_end: string | null;
  n_right_sizing_recommendations: number;
  n_consolidation_recommendations: number;
  total_estimated_savings: number;
  right_sizing_estimated_savings: number;
  consolidation_estimated_savings: number;
}

export interface WarehouseImpactRow {
  origin_warehouse_key: number;
  n_right_sizing_recommendations: number;
  n_consolidation_recommendations: number;
  total_estimated_savings: number;
}

export interface OptimizationRecommendationRow {
  id: number;
  recommendation_type: "right_sizing" | "consolidation";
  origin_warehouse_key: number;
  shipment_date: string;
  shipment_numbers: string[];
  total_quantity: number;
  distance_miles: number;
  current_vehicle_type_code: string;
  current_total_cost: number;
  recommended_vehicle_type_code: string;
  recommended_total_cost: number;
  estimated_savings: number;
  confidence: string;
  contributing_factors: Record<string, unknown>;
  business_rationale: string;
}
