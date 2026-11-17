# AlgoArchive 2.2.10 本地升级计划

> **For agentic workers:** Use superpowers:subagent-driven-development to implement and review each task. 本计划及用户附件是工作范围，不能据此扩大到远程发布。

**Goal:** 完成用户提供的本地升级清单，并让算法卡片图形与六色周期一一对应。
**Architecture:** 保留 Python 标准库服务和原生 JS。平台独立排序保存在现有 settings 中，兼容数据库版本 10；前端共享状态使用请求代次和变更失效机制；插画独立恢复并提供加载失败重试。
**Tech Stack:** Python / SQLite / JavaScript / SVG / Windows / Playwright。
**Spec:** `C:/Users/Aqiw/Desktop/AlgoArchive-local-upgrade-requirements.md`；补充：算法模板左上角内置六种图形，按现有持久化六色循环。

## Global Constraints

- 不上传 GitHub，不推送代码，不创建远程 PR，不发布 Release，不部署线上演示。
- 保留题库、比赛、模板、代码、测试用例、头像、设置及原有排序。
- 测试使用隔离数据；实际升级前有程序和用户目录完整备份。
- 不覆盖更高版本数据库；本次保持数据库 schema 10，通过 settings 扩展兼容数据。
- 现有五个侧栏工作区不增加；内置平台注册表共十个平台。
- 六个图形对应 blue/cyan/green/amber/rose/violet，使用树节点、树分支、代码、搜索、网格、图层；与名称、过滤及拖动位置无关。
- 下一本地版本 2.2.10；源码、资源标识、启动器资源及包元数据一致。

## Task 1: 后端独立排序、日志和缓存

**Files:** app.py；tests/test_platform_order.py；tests/test_sidebar_art.py 或新建专项测试。
**Interfaces:** `PUT /api/platforms/{key}/problems/order` 接收 `{version, problem_ids}`；返回 `{platform, platform_order_version, problem_ids}`。`GET /api/state` 增加 `platform_problem_orders: {key: {version, problem_ids}}`。key 与前端 platformKey 规范化一致。

- [ ] 读取现有 Repository、迁移、导入、恢复、日志及静态资源响应实现。
- [ ] 先添加独立顺序、持久化、非法集合和冲突回归，确认旧版缺失。
- [ ] 用 settings 保存每个平台顺序和版本；默认沿用现有 updated_at 降序，新题稳定追加，编辑不重置；移动平台、删除、导入、恢复维持一致，成员变化递增版本。
- [ ] 拒绝重复、非字符串、跨平台、不完整 ID 以及过期版本。各平台与全局/比赛/算法顺序独立。
- [ ] 精确屏蔽 PUT /api/settings/sidebar-art 的 2xx 常规成功日志，保留失败和其他写操作。
- [ ] 版本化静态资源可缓存，HTML/API 保持 no-store；提供独立插画偏好读取入口如现有 settings 可复用。
- [ ] 后端测试通过并提交本任务文件；写明接口及测试结果。

## Task 2: 前端状态、插画、平台和图形

**Files:** web/app.js；web/index.html；web/workspace-updates.css；demo/api.js（以实际文件名为准）；tests/test_local_upgrade.cjs。
**Consumes:** Task 1 定义的 platform_problem_orders 与排序 API。

- [ ] 加入旧状态响应晚返回、保存成功但刷新失败、图像失败及重试的可控浏览器回归。
- [ ] loadState 写入前验证请求代次，变更操作使旧读取失效；迟到路由请求不得覆盖编辑器。保存即时合入返回记录，刷新失败保留保存结果并给出重试；跨窗口通知不得覆盖草稿。
- [ ] 插画偏好独立加载/缓存，避免业务请求失败时永久隐藏；加载新图保留旧图/占位，去除重复 src，防止过期图回调覆盖，错误提示与手动重试。
- [ ] 侧栏剩余空间布局保持纵横比和设置可达；缩小 sidebar 缩略资源，保留原图预览。
- [ ] 新增表单关闭历史自动填充，平台仅固定内置建议但可自定义；提示“未找到你的平台？可直接输入其他平台名称。”；验证 POJ/力扣所有比赛入口。
- [ ] 平台题目沿用原有拖动、落点和键盘排序。筛选状态明确禁用排序并解释，其他原有排序保留。
- [ ] 六个 SVG 与持久化 card_color 一一对应；新建第七个回到第一个，重命名/过滤/拖动不改变。
- [ ] 同步本地演示 API 行为，运行 JS 语法、相关现有浏览器回归与新专项回归。

## Task 3: 审查、打包、本地升级和验收

**Files:** 版本引用、CHANGELOG.md、启动器资源、便携包和外部验收报告。

- [ ] 独立审查 Task 1 与 Task 2 的需求符合度及代码质量，解决关键问题。
- [ ] 同步版本 2.2.10，编译静态链接原生启动器，复制现有内置 Python runtime，运行项目发布验证并构建 ZIP。
- [ ] 在 Windows Chrome 隔离配置验证普通桌面、矮窗口、缩放等价视口，以及失败和并发场景；保存截图与诊断。
- [ ] 按便携目录升级实际程序；启动该目录的 EXE 验证版本和资源，读核对真实数据及配置与备份一致，不在真实题库写测试记录。
- [ ] 给出修复/已复现/推断/未验证边界、包路径、备份路径和回退方式；保留本地源码提交。
