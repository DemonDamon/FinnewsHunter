# S01 远端质量闭环

Planned-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档，导入/生命周期独立Reviewer
Parent-Plan: .cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md
Plan-Id: 2026-10-29-finnews-s01-quality-fix
Status: Ready / 用户授权排查、修复并在门禁通过后合并
Base-Commit: d99acfd379f9b024d77661bb2ffdcc9775973d1e
Author: Damon Li

确切6项：core/__init__.py的4个PYL-E0603未定义__all__成员；main.py::_research_readiness_payload签名E501；composition.py::build_research_components的del settings为PTC-W0043。PEP562 runtime已有实测，但需要让静态分析看到真实类型绑定，而非删除公开exports或恢复无条件DB导入。

FR-1：__init__可用TYPE_CHECKING下的真实导入提供静态绑定，runtime仍__getattr__按需加载；保持原__all__顺序及settings/get_settings/get_db/init_database符号，不能stub数据库。

FR-2：签名换行；删除多余del settings，保留build_research_components(settings)可按原关键字调用及无副作用、四项not-ready。如需表达保留参数，使用明确无副作用的意图表示，不用fake readiness逻辑或宽泛忽略规则。

AC：新增/加强TYPE_CHECKING绑定不触runtime旧DB、公开export访问仍真导入、kwargs兼容的测试。S01本地29项与合流60项通过；88行宽与静态检查通过，__all__原顺序不可为格式更改。源白名单：core/__init__.py、main.py、research/composition.py、现有3个相关research test和本计划。不得修改C1、依赖、锁、.deepsource.toml、旧router业务或另一worktree。

父agent接上游新digest并合流后才commit/push/复查远端；子agent不提交、不启动服务、不调用真实源/模型。日志/结果写任务 `.work/merge-review/s01-quality-result.md`。执行前将本计划从pending移至plans根目录。
