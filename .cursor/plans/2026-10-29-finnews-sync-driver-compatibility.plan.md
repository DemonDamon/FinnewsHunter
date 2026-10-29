# 同步数据库驱动兼容性修复

Planned-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档，兼容性独立Reviewer
Parent-Plan: .cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md
Plan-Id: 2026-10-29-finnews-sync-driver-compatibility
Status: Ready / 等待并行质量修复完成后实施
Base-Commit: f236baf0ac2903374e77c43a6115d2817d6f019f
Author: Damon Li

根因：core/config.py::Settings.SYNC_DATABASE_URL返回postgresql://。原依赖已经声明psycopg2-binary，但新精确锁内SQLAlchemy2.1.6的默认dialect为psycopg，未安装该driver。无网探针确认旧URL在create_engine阶段ModuleNotFoundError(psy­copg)，显式postgresql+psycopg2可构造engine且无连接。不得通过忽略导入失败或安装另一个浮动driver掩盖。

唯一代码改动：Settings.SYNC_DATABASE_URL把scheme明确为postgresql+psycopg2，保留host/port/db/user/password构造及异步asyncpg URL。无迁移、无连接、无依赖lock/SDK版本变化。S01上游合流接收同一修复，不另写重复driver逻辑。

新增backend/tests/research/test_sync_driver_compatibility.py：在临时cwd/HOME、无真实key的子进程阻断socket；真实导入Settings、默认同步URLdriver验证和engine构造/dispose；断言未网络连接，异步URL不变。若真实app.core导入仍因该driver失败必须红，不能stub数据库制造通过。

AC：先保留旧scheme失败证据，再新测试通过；S00全research测试与S01合流全research测试通过；22个实际旧SDK符号均可导入；所有新代码88字符检查。禁止读用户.env、启动库、连接服务、改旧模型/API/DDL、改变默认研究关闭。修复提交使用Manus2.0模型元数据，由父agent在审查通过后处理。
