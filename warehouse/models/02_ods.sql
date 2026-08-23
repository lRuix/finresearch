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
