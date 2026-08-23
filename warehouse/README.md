# Warehouse

数仓子项目，用于把本地市场数据抽取到 PostgreSQL，并构建 ODS、DWD、DWS 分层数据。

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
python -m etl.migrate_seed
```

默认读取 `backend/data/research.db`，写入 K 线 ODS/DWD、装载新闻并刷新 DWS。
可通过环境变量覆盖连接与数据文件：

```bash
WAREHOUSE_DSN="$WAREHOUSE_DSN" WAREHOUSE_DB_PATH="/path/to/research.db" python -m etl.migrate_seed
```

## 运行测试

```bash
python -m pytest tests -q
```

测试假定数仓为空库或只包含测试自身数据；迁移后再运行测试前，建议先清空 ODS/DWD/DWS 数据，避免断言受种子数据影响。
