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
