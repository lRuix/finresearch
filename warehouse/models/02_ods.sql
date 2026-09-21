CREATE TABLE IF NOT EXISTS ods_klines_a_share (
  provider TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  ts TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume REAL,
  amount REAL,
  change_pct REAL,
  turnover_rate REAL,
  amplitude REAL,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  UNIQUE (provider, market, symbol, interval, ts)
);

CREATE TABLE IF NOT EXISTS ods_klines_fund (
  provider TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  ts TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume REAL,
  nav REAL,
  accum_nav REAL,
  daily_growth_pct REAL,
  purchase_status TEXT,
  redeem_status TEXT,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  UNIQUE (provider, market, symbol, interval, ts)
);

CREATE TABLE IF NOT EXISTS ods_klines_us (
  provider TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  ts TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume REAL,
  adj_close REAL,
  dividends REAL,
  stock_splits REAL,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  UNIQUE (provider, market, symbol, interval, ts)
);

CREATE TABLE IF NOT EXISTS ods_klines_kr (
  provider TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  ts TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume REAL,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  UNIQUE (provider, market, symbol, interval, ts)
);

CREATE TABLE IF NOT EXISTS ods_klines_hk (
  provider TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  ts TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume REAL,
  corporate_events JSONB,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  UNIQUE (provider, market, symbol, interval, ts)
);

CREATE TABLE IF NOT EXISTS ods_klines_fx (
  provider TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  ts TEXT NOT NULL,
  base_currency TEXT,
  quote_currency TEXT,
  close_rate REAL,
  prev_rate REAL,
  open_rate REAL,
  high_rate REAL,
  low_rate REAL,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  UNIQUE (provider, market, symbol, interval, ts)
);

CREATE TABLE IF NOT EXISTS ods_klines_crypto (
  provider TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  ts TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume REAL,
  quote_volume REAL,
  trades_count REAL,
  funding_rate REAL,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  UNIQUE (provider, market, symbol, interval, ts)
);

CREATE TABLE IF NOT EXISTS ods_news (
  provider TEXT NOT NULL,
  market TEXT NOT NULL,
  ts TEXT NOT NULL,
  title TEXT NOT NULL,
  source TEXT NOT NULL,
  tags JSONB,
  sentiment REAL,
  published_at TIMESTAMPTZ NOT NULL,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  UNIQUE (source, published_at, title)
);

-- ============ 外部数据源 ODS ============
CREATE TABLE IF NOT EXISTS ods_sec_submissions (
  cik TEXT NOT NULL,
  ticker TEXT,
  company_name TEXT NOT NULL,
  exchange TEXT,
  sic TEXT,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (cik)
);

CREATE TABLE IF NOT EXISTS ods_sec_facts (
  cik TEXT NOT NULL,
  concept TEXT NOT NULL,
  unit TEXT NOT NULL,
  period_end DATE NOT NULL,
  value DOUBLE PRECISION,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (cik, concept, unit, period_end)
);

CREATE TABLE IF NOT EXISTS ods_crypto_meta (
  coin_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT NOT NULL,
  snapshot_date DATE NOT NULL,
  current_price DOUBLE PRECISION,
  market_cap DOUBLE PRECISION,
  total_volume DOUBLE PRECISION,
  high_24h DOUBLE PRECISION,
  low_24h DOUBLE PRECISION,
  market_cap_rank INTEGER,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (coin_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS ods_macro_indicators (
  country_code TEXT NOT NULL,
  indicator_code TEXT NOT NULL,
  indicator_name TEXT NOT NULL,
  date TEXT NOT NULL,
  value DOUBLE PRECISION,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (country_code, indicator_code, date)
);

CREATE TABLE IF NOT EXISTS ods_cn_financials (
  symbol TEXT NOT NULL,
  report_date TEXT NOT NULL,
  indicator_name TEXT NOT NULL,
  indicator_value DOUBLE PRECISION,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (symbol, report_date, indicator_name)
);

CREATE TABLE IF NOT EXISTS ods_cn_lhb (
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  close_price DOUBLE PRECISION,
  change_pct DOUBLE PRECISION,
  reason TEXT NOT NULL DEFAULT '',
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (trade_date, code, reason)
);

CREATE TABLE IF NOT EXISTS ods_cn_balance (
  symbol TEXT NOT NULL,
  report_date TEXT NOT NULL,
  indicator_name TEXT NOT NULL,
  indicator_value DOUBLE PRECISION,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (symbol, report_date, indicator_name)
);

CREATE TABLE IF NOT EXISTS ods_cn_share_structure (
  symbol TEXT NOT NULL,
  change_date TEXT NOT NULL,
  total_shares DOUBLE PRECISION,
  float_shares DOUBLE PRECISION,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (symbol, change_date)
);

CREATE TABLE IF NOT EXISTS ods_cn_daily_metrics (
  symbol TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  close_price DOUBLE PRECISION,
  turnover_rate DOUBLE PRECISION,
  market_cap DOUBLE PRECISION,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (symbol, trade_date)
);
