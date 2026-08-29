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

K 线由数仓直采：按市场动态发现标的（A股/港股/场内基金/加密全市场，美股/韩股走
配置清单，外汇静态全列表），按 `etl_watermarks` 水位线只处理新增 K 线；新闻按
发布时间增量装载（`WAREHOUSE_LIVE_NEWS=1` 时额外抓取 RSS）。ODS / DWD / 新闻与
水位线推进在同一事务内完成，失败回滚且不推进水位线；事务提交后刷新 DWS 物化视图。

```bash
cd warehouse
python -m etl.sync_daily
```

首次运行（水位线为空）等价于全量装载；之后每次只处理新增数据。可用 cron 实现每日更新：

```cron
0 9 * * * cd /path/to/finresearch/warehouse && WAREHOUSE_DSN="$WAREHOUSE_DSN" .venv/bin/python -m etl.sync_daily && .venv/bin/python -m etl.sync_external
```

可用 `WAREHOUSE_MARKETS` 环境变量限制本次同步的市场（逗号分隔，如
`WAREHOUSE_MARKETS=fx,us,kr`），便于分市场运行或调试。

可用 `WAREHOUSE_SOURCE_DISABLED=gate,yfinance` 禁用指定数据源；真实数据源失败时
跳过对应标的，不写入 mock 数据。

> 注意：`backend/data/research.db` 已不再参与每日同步，仅保留为历史数据参考；
> `migrate_seed.py` 为历史迁移工具，不再作为每日入口。

## 运行外部数据源同步

接入 SEC EDGAR（美股财报/公司元数据）、CoinGecko（加密市值）、World Bank（宏观指标）
与 akshare（A股财务摘要/龙虎榜），每日增量：

```bash
cd warehouse
python -m etl.sync_external
```

各源按独立事务装载并维护 `etl_watermarks` 水位线，失败仅回滚对应源，
不影响其他源当天数据。SEC 请求带显式 User-Agent；akshare 为惰性导入。

## 运行测试

```bash
cd warehouse
python -m pytest tests -q
```

测试连接独立的 `warehouse_test` 数据库（需先执行 DDL，见下），与真实数据隔离；
真实 `warehouse` 库的数据不会影响测试。

```bash
# 首次准备测试库（容器内执行）
docker exec warehouse-db-1 psql -U warehouse -d warehouse -c "CREATE DATABASE warehouse_test"
cd warehouse
for f in models/01_dim.sql models/02_ods.sql models/03_dwd.sql models/04_dws.sql; do
  docker exec -i warehouse-db-1 psql -U warehouse -d warehouse_test -v ON_ERROR_STOP=1 -q -f - < "$f"
done
```
