# Linux arm64依赖锁闭环

Planned-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档，依赖与平台差异独立审查
Parent-Plan: .cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md
Plan-Id: 2026-10-29-finnews-linux-dependency-lock
Status: Completed / Linux 锁已生成；Linux/Docker 安装、pip check 与应用验证仍由 S01 gate 负责
Base-Commit: fb8bee993cf0c426a5456b43449820192acb8f0c
Author: Damon Li

证据：任务linux-locked-build-final.log第二次构建实际ERROR：require-hashes模式缺失py-mini-racer>=0.6.0（akshare==1.20.2在Linux的传递依赖），原锁151项按aarch64-apple-darwin解析。此前空wheel被hash正确阻止；不能把真实平台问题继续写作网络阻塞。

FR-1：在任务隔离目录使用现有uv0.9.26，对相同requirements.txt与requirements-dev.txt采用现有lock作为constraints，目标aarch64-unknown-linux-gnu/CPython3.12生成带完整hash的backend/requirements-research-linux.lock。保留原backend/requirements-research.lock作为已验证macOS锁，禁止覆写或升级原151项版本，禁止删掉akshare/第三方依赖让它过门。Linux新传递依赖只能来自公开发布物的resolver输出；若py-mini-racer source不可用，如实阻塞，不虚构运行可用。

FR-2：选择Linux专属锁的实际消费点在S01 Dockerfile.celery和研究启动前置计划，父agent统一装配；本S00子任务只产Linux锁、兼容文档及plan。报告缺失依赖为何仅Linux需要，所有原包交集版本对照，Linux新增项/删除项及platform markers，记录命令/生成可重复性、文件sha256。不得安装全局包、修改用户镜像源、去hash或忽略deps。

AC：精确同输入重复生成payload一致；所有原交集版本不变，SDK0.6.5和MCP1.30.0不变，C1产物不变；Linux实际docker pip --require-hashes安装、pip check及真实SDK/应用验证由父agent执行，不能本地宣称已通过。旧mac锁的安装验证与tests不回归。

写入白名单：backend/requirements-research-linux.lock、docs/compatibility/agx-research-baseline.md新增Linux说明、本计划。日志/下载/临时script仅任务.work/merge-review/linux-lock。不得改其他依赖输入、源、S01/AGX/用户目录。不commit/push。执行前计划移至plans根；中文结果写任务.work/merge-review/linux-lock/result.md，含父agent消费的正确安装路径与SHA256。

## 实施记录（2026-10-29）

- 使用现有 `/Users/damon/.local/bin/uv` 0.9.26 和 CPython 3.12.12，以 `backend/requirements-research.lock` 为 constraint，对 `aarch64-unknown-linux-gnu` 连续两次编译原始 requirements 与 dev requirements。两次完整 payload 字节一致。
- 输出 `backend/requirements-research-linux.lock`：152 项，每项至少一个 SHA-256；与 macOS 锁的 150 项交集版本全部相同（含 `agenticx==0.6.5`、`mcp==1.30.0`）。Linux 新增 `akracer==0.0.14`、`py-mini-racer==0.6.0`；仅移除 macOS 路径的 `mini-racer==0.14.1`。
- 最终 SHA-256：`0ef9efd4cafa08ec46c20e79d16c4100d5381c380c27b126382df3db0b0c7203`。父 agent 的 Linux 消费路径为 `backend/requirements-research-linux.lock`，且仍必须在 S01 Docker 中执行实际 `pip --require-hashes` 安装、`pip check` 与应用验证。
- `py-mini-racer==0.6.0` 无 Linux aarch64 预编译 wheel，锁保留其 sdist hash；本任务未安装或运行 Linux/Docker，未将解析成功表述为 Linux 运行成功。
