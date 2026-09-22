# 项目规范

## 语言

- 所有思考、交互与回复内容使用中文。
- 代码、技术术语、命令、文件名可保持原文。

## 提交规范

- Git commit message 必须使用中文。
- 格式：`<类型>: <简短描述>`
- 类型：`feat`、`fix`、`refactor`、`docs`、`chore`、`style`。
- 提交后检查 CHANGELOG、README、SOP 等文档是否需要同步更新；**提交前**也要做这一步，
  不要留到收尾。
- 涉及以下变更时，必须同步更新 `warehouse/README.md` 与 `docs/ARCHITECTURE.md`，否则
  按文档部署会与实现不一致（曾发生：新增 ETL 入口未写入 cron 模板，导致按文档部署时
  该功能永不运行）：
  - 新增 / 改名 ETL 入口（`etl.*` 模块）或调整它们的运行顺序；
  - 新增 / 删除数据源，或新增 ODS 表（须写明「既有库需重跑哪个 DDL 文件」）；
  - 新增 / 变更水位线 scope 的语义或增量策略；
  - 变更进程退出码 / 失败语义（影响 cron 告警）。

## 技术栈

- 前端：React + TypeScript + Vite + ECharts。
- 后端：FastAPI + Uvicorn。
- 数据源：优先开源数据源，缺失或失败时使用内置模拟数据兜底。

