# S00 远端质量闭环

Planned-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档，独立Reviewer确认契约不变
Parent-Plan: .cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md
Plan-Id: 2026-10-29-finnews-s00-quality-fix
Status: Ready / 用户授权排查、修复并在门禁通过后合并
Base-Commit: f236baf0ac2903374e77c43a6115d2817d6f019f
Author: Damon Li

远端报告100 introduced，首15项明确为FLK-E501/88字符行宽。本机Ruff原配置未覆盖该行宽，所以本地通过不足。输入证据 `.work/merge-review/remote-findings.md` 位于任务根目录；报告URL见该文件。

FR-1：对本批6个Python文件实施88字符兼容格式：research/{__init__,contracts}.py、scripts/generate_research_contracts.py、tests/research/{__init__,test_agx_compatibility,test_contract_schema}.py。保留validator、枚举、状态、权限、时点、数值和所有公开参数。长字符串用等价拼接，尽量保留docstrings文本；不得用忽略E501或禁用分析规则过门。

FR-2：格式后重新生成C1产物，记录旧/新digest与语义差异；manifest/hash改变必须诚实更新docs/contracts、docs/architecture、docs/compatibility及本仓Master/S00/S02计划引用。schema_version不因纯格式升级，字段、required、pattern、数值上界须逐项不变。若有业务差异停止，不能当格式修。

AC：保留修前E501失败日志；31项单测、生成check、Ruff含88行宽、pip check全通过；schemas除描述文案等价变化外结构相同。无依赖版本/锁/新服务/真实数据变动。最后父agent独立合流并检查远端，不由实现agentcommit/push/merge。

写入白名单上述6文件、生成C1目录及明确的本仓引用文档/本计划。不得改.deepsource.toml、S01源、AGX或旧业务。修复日志与总结写任务 `.work/merge-review/s00-quality-result.md`。执行前将本计划从pending移至plans根目录。

## 实施记录

Implemented-with: Manus 2.0

88列格式已实施；contracts、generator和contract_schema的AST与修前完全相同，32个schemas、25个fixtures和manifest逐字节不变，digest仍为591d9cdbfc3dbc639cc0859639e11e910ff86a73fdb34c9697ba63af1534a59e。保留所有业务校验、依赖与规则。

同类PTC-W0043修复：scripted provider仅把局部del参数改为无副作用的未使用绑定；同步空流用yield from ()，异步流包装同一个空同步流，保持真实生成器契约，不用恒假分支。negative fixture真正删除字典字段的del保留。

本机32项研究测试通过（含另计划新增的同步驱动回归），生成check、Ruff88列、pip check通过；独立审查与远端更新由父agent执行。未在此记录尚未完成的Linux或远端检查为通过。
