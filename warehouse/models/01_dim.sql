CREATE TABLE IF NOT EXISTS dim_date (
  date_key DATE PRIMARY KEY,
  year SMALLINT NOT NULL,
  month SMALLINT NOT NULL,
  day SMALLINT NOT NULL,
  is_trading_day BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS dim_market (
  market_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  region TEXT NOT NULL,
  currency TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_instrument (
  instrument_id BIGSERIAL PRIMARY KEY,
  market_id TEXT NOT NULL REFERENCES dim_market(market_id),
  symbol TEXT NOT NULL,
  name TEXT NOT NULL,
  sector TEXT,
  UNIQUE (market_id, symbol)
);

CREATE TABLE IF NOT EXISTS dim_provider (
  provider_id TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

-- 数仓 ETL 增量水位线：scope 形如 "kline:{market}:{symbol}:{period}" 或 "news"。
-- 增量装载在同一事务内完成 ODS/DWD 装载后，才推进对应水位线；
-- 装载失败时水位线保持不变，下次运行会重放未完成的数据。
CREATE TABLE IF NOT EXISTS etl_watermarks (
  scope TEXT PRIMARY KEY,
  last_value TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
