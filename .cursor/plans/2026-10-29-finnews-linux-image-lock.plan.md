# Linux镜像选择平台专属锁

Planned-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档，Linux运行独立验收
Parent-Plan: .cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md
Plan-Id: 2026-10-29-finnews-linux-image-lock
Status: Verified / 已完成本机、Linux、独立复审和远端门禁；随S01合流
Author: Damon Li

根因：deploy/Dockerfile.celery原research分支安装macOS解析的requirements-research.lock，在Linux实际安装时缺失akshare的py-mini-racer传递依赖，hash策略正确阻断。上游新增requirements-research-linux.lock保留旧版本和mac锁，必须让镜像实际消费新Linux锁，不能只在文档宣布Linux通过。

FR-1：Dockerfile.celery把research锁COPY和pip --require-hashes路径改为requirements-research-linux.lock；保留旧默认legacy、Pythonbase参数、legacy requirements与entrypoint绝不runtime重装。

FR-2：test_research_compose.py::test_research_dockerfile_installs_only_the_hashed_lock_and_entrypoint_never_reinstalls断言Linux专用COPY/安装路径，拒绝research分支安装mac锁。dockerignore同时不得排除两份锁。docs/operations/research-bootstrap.md补mac宿主/linux镜像各用何锁、SHA256和真实验收记录。

AC：先原断言改为期望Linux路径在旧Dockerfile红，再改Dockerfile绿；合流至少61项研究tests+generator+Ruff通过。真实Linux/arm64 Python3.12 hash安装、pip check、scripted Flow/ReAct、TestClient health200/ready503/debug404及禁止旧模块，均在--network none且源码read-only mount的容器完成。不得把host通过或旧镜像证据冒作最终源码通过。若缺包或平台artifact无法用则停止合并，不删依赖或关hash。

白名单：上述Dockerfile、compose测试、启动操作文档、本计划，父agent可同步S01/Master状态但不得新加功能。禁止服务启停、用户镜像源改动、真实数据库/源/模型、生产部署。执行前计划从pending移至plans根。日志仅任务.work/merge-review/linux。
