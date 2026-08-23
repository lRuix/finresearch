CREATE TABLE IF NOT EXISTS fact_kline (
  market_id TEXT NOT NULL,
  instrument_id BIGINT NOT NULL,
  provider_id TEXT NOT NULL,
  date_key DATE NOT NULL,
  period TEXT NOT NULL,
  time TIMESTAMPTZ NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume REAL NOT NULL,
  PRIMARY KEY (market_id, instrument_id, period, time)
) PARTITION BY RANGE (time);

CREATE TABLE IF NOT EXISTS fact_kline_default PARTITION OF fact_kline DEFAULT;

CREATE TABLE IF NOT EXISTS fact_news (
  news_id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  published_at TIMESTAMPTZ NOT NULL,
  title TEXT NOT NULL,
  sentiment REAL,
  tags JSONB NOT NULL DEFAULT '[]',
  UNIQUE (source, published_at, title)
);
