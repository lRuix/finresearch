# Warehouse

数仓子项目，用于把本地市场数据抽取到 PostgreSQL，并构建 ODS、DWD、DWS 分层数据。

## 准备运行环境

以下命令默认在 `warehouse/` 目录内执行：

```bash
cd warehouse
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

也可以复用项目已有的 `backend/.venv`，只要其中已安装 `psycopg` 与 `pytest`。

## 启动 PostgreSQL

```bash
docker compose up -d db
```

## 初始化 DDL

按依赖顺序执行：

```bash
export WAREHOUSE_DSN="postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse"
psql "$WAREHOUSE_DSN" -f models/01_dim.sql
psql "$WAREHOUSE_DSN" -f models/02_ods.sql
psql "$WAREHOUSE_DSN" -f models/03_dwd.sql
psql "$WAREHOUSE_DSN" -f models/04_dws.sql
```

## 运行初始迁移

```bash
cd warehouse
python -m etl.migrate_seed
```

默认读取 `backend/data/research.db`，写入 K 线 ODS/DWD、装载新闻并刷新 DWS。
可通过环境变量覆盖连接与数据文件：

```bash
WAREHOUSE_DSN="$WAREHOUSE_DSN" WAREHOUSE_DB_PATH="/path/to/research.db" python -m etl.migrate_seed
```

新闻默认只装载 `macro_data.NEWS_ITEMS` 缓存；需要额外抓取 RSS 时设置：

```bash
WAREHOUSE_LIVE_NEWS=1 python -m etl.migrate_seed
```

## 运行每日增量更新

增量装载以 `backend/data/research.db` 为增量源，按 `etl_watermarks` 水位线
只处理每个 (market, symbol, period) 新增的 K 线；新闻按发布时间增量装载
（`WAREHOUSE_LIVE_NEWS=1` 时额外抓取 RSS）。ODS / DWD / 新闻与水位线推进在
同一事务内完成，失败回滚且不推进水位线；事务提交后刷新 DWS 物化视图。

```bash
cd warehouse
python -m etl.sync_incremental
```

首次运行（水位线为空）等价于全量装载；之后每次只处理新增数据。可用 cron 实现每日更新：

```cron
0 9 * * * cd /path/to/finresearch/warehouse && WAREHOUSE_DSN="$WAREHOUSE_DSN" .venv/bin/python -m etl.sync_incremental
```

## 运行测试

```bash
cd warehouse
python -m pytest tests -q
```

测试假定数仓为空库或只包含测试自身数据；迁移后再运行测试前，建议先清空 ODS/DWD/DWS 数据，避免断言受种子数据影响。
