-- backend 业务运行数据（应用缓存，不参与数仓 ODS/DWD/DWS 分层）
CREATE TABLE IF NOT EXISTS backend_evaluations (
  evaluated_on TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  score DOUBLE PRECISION NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (evaluated_on, market, symbol)
);

CREATE TABLE IF NOT EXISTS backend_market_snapshots (
  date TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT NOT NULL,
  turnover DOUBLE PRECISION,
  market_cap DOUBLE PRECISION,
  rank INTEGER NOT NULL,
  PRIMARY KEY (date, market, symbol)
);
