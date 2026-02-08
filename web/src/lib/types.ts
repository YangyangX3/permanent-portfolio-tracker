export type Category = {
  id: string;
  name: string;
  target_weight: number;
  min_weight: number;
  max_weight: number;
};

export type PortfolioAsset = {
  id: string;
  kind: "cn" | "crypto" | "cash";

  code?: string;
  name?: string;
  quantity?: number;
  category_id?: string | null;
  bucket_weight?: number | null;

  chain?: string | null;
  wallet?: string | null;
  token_address?: string | null;
  coingecko_id?: string | null;
  manual_quantity?: number | null;

  cash_amount_cny?: number | null;
};

export type Portfolio = {
  base_currency: "CNY" | string;
  categories: Category[];
  assets: PortfolioAsset[];
};

export type AssetView = {
  id: string;
  kind: "cn" | "crypto" | "cash" | string;
  category_id: string | null;
  bucket_weight: number | null;
  code: string;
  name: string;
  quantity: number | null;
  price: number | null;
  change_pct: number | null;
  as_of: string | null;
  source: string;
  value: number;
  status: "ok" | "warn" | "error" | string;
  note: string;
};

export type CategoryView = {
  id: string;
  name: string;
  value: number;
  weight: number;
  target_weight: number;
  min_weight: number;
  max_weight: number;
  status: "ok" | "warn" | string;
  note: string;
  assets: AssetView[];
};

export type PortfolioView = {
  total_value: number;
  as_of: string | null;
  categories: CategoryView[];
  unassigned: AssetView[];
  rebalance_warnings: string[];
  warnings: string[];
};

export type CacheState = {
  updated_at: string | null;
  last_duration_ms: number | null;
  last_error: string | null;
};

export type UiState = {
  portfolio: Portfolio;
  view: PortfolioView | null;
  cache: CacheState;
};

export type TotalHistoryPoint = { t: number; v: number };

export type TotalHistoryPayload = {
  window: string;
  currency: "CNY" | string;
  baseline_value: number;
  current_value: number;
  change_value: number;
  change_pct: number | null;
  points: TotalHistoryPoint[];
};

export type AssetBuySuggestion = {
  asset_id: string | null;
  name: string;
  code: string;
  amount_cny: number;
  est_quantity: number | null;
  note: string;
};

export type CategorySuggestion = {
  category_id: string;
  name: string;
  current_value: number;
  current_weight: number;
  target_weight: number;
  target_value_after: number;
  allocate_amount: number;
  weight_after: number;
  assets: AssetBuySuggestion[];
};

export type ContributionSuggestion = {
  ok?: boolean;
  contribution_amount: number;
  total_before: number;
  total_after: number;
  categories: CategorySuggestion[];
  note: string;

  // present in suggest-after-crypto payload
  prefill_assets?: Record<string, number>;
  prefill_total?: number;
  slip_pct?: number;
  contribution_total?: number;
  contribution_remaining?: number;
};

export type LedgerMetricsPayload = {
  currency: "CNY" | string;
  now_ts: number;
  total: {
    principal: number;
    current_value: number;
    profit: number;
    xirr_annual: number | null;
  };
  per_asset: Array<{
    id: string;
    kind: string;
    code: string;
    name: string;
    principal: number;
    current_value: number;
    profit: number;
    xirr_annual: number | null;
  }>;
};

export type LedgerDaysPayload = {
  days: Array<{
    date: string;
    entry_count: number;
    deposit_total: number;
    withdraw_total: number;
    net_total: number;
    running_principal_end: number;
    buckets: Array<{ id: string; name: string; deposit: number; withdraw: number; net: number }>;
    other: { deposit: number; withdraw: number; net: number };
    entries?: Array<{
      id: string;
      date: string;
      direction: "deposit" | "withdraw";
      amount_cny: number;
      asset_id: string | null;
      asset_name: string;
      note: string;
    }>;
  }>;
};

export type SettingsPayload = {
  ok: boolean;
  override: {
    timezone?: string | null;
    email_enabled?: boolean | null;
    notify_cooldown_minutes?: number | null;
    daily_job_time?: string | null;
    crypto_slip_pct?: number | null;
    mail_from?: string | null;
    mail_to?: string[] | null;
    smtp_host?: string | null;
    smtp_port?: number | null;
    smtp_username?: string | null;
    smtp_use_starttls?: boolean | null;
    smtp_password_set?: boolean;
  };
  effective: Record<string, unknown>;
};

