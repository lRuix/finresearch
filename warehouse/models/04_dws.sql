CREATE MATERIALIZED VIEW IF NOT EXISTS dws_instrument_daily AS
SELECT market_id, instrument_id, date_key,
       count(*) AS rows_count,
       (max(high) - min(low)) / NULLIF(min(low), 0) AS amplitude,
       max(close) AS last_close,
       sum(volume) AS total_volume
FROM fact_kline
WHERE period = 'd'
GROUP BY market_id, instrument_id, date_key;

CREATE MATERIALIZED VIEW IF NOT EXISTS dws_market_daily AS
SELECT market_id, date_key,
       avg((close - open) / NULLIF(open, 0)) AS avg_daily_return,
       sum(volume) AS total_volume,
       count(DISTINCT instrument_id) AS instrument_count
FROM fact_kline
WHERE period = 'd'
GROUP BY market_id, date_key;
