# Changelog

## 2.2.10 - 2026-11-17（本地维护版本）

- 自有代码和自有文档采用 MIT 许可证；补充算法平台、CPH 兼容功能、素材权利及本地测试边界声明。第三方软件、商标和插画保留各自权利。
- 保存后的比赛/算法关联计数与后端平台统计改为单次遍历；跨窗口刷新保留当前筛选、焦点和滚动位置。
- 将重复的 v2.2.1 修复文档合并到测试报告，移除不再引用的旧版 AcWing 截图，保留有用途的脚本、测试及第三方许可证。当前跟踪文件的名称及多编码文本检查未发现内部测试个人姓名；未改写历史提交。

- 平台工作区题目拥有独立、持久化的移动顺序，支持拖动和键盘操作；与全部题目、比赛、算法的顺序相互独立。新题稳定追加，冲突和成员变化有版本校验。
- 状态读取在写入共享状态前校验请求代次，保存成功但列表刷新失败时保留已保存结果并提供明确重试；跨窗口更新保留编辑草稿。
- 侧栏插画独立读取偏好，保留加载中的上一张图，提供失败反馈和重试；调整短窗口布局，保留设置入口。三张缩略图缩至约 47–52 KB，原始 PNG 仍用于放大预览。
- 精确隐藏插画偏好 PUT 成功访问日志，保留失败及其他操作日志；版本化静态资源可缓存，HTML 与业务 API 保持不缓存。
- 新增题目与比赛表单关闭历史自动填充建议，保留十个平台固定选择、自定义平台输入及当前关联预填；平台旁增加手动输入提示。
- 算法卡片内置树节点、分支树、代码、搜索、网格、图层六种 SVG，依次对应蓝、青、绿、琥珀、玫红、紫；改名、筛选、拖动和重启不改变对应关系。
- 数据库 schema 保持 10，新增排序写入现有 settings；备份恢复保留顺序并使旧窗口排序版本失效。本版本未推送、未发布 Release、未部署在线演示。

## 2.2.9 - 2026-11-15

- 力扣、POJ 增加本地打包的官网图标和填写建议，仅标识题目与比赛来源，不增加固定工作空间、首页统计或模块。
- 题目与比赛的所属平台统一为可搜索、可点击和键盘选择的十平台下拉；仍可自由输入自定义平台，同平台重复选择保留原比赛关联。
- 侧栏插画增加调试报错、优化思路、通过庆祝三张内置图，左右箭头手动循环，不自动轮播，点击查看完整原图。
- 设置增加侧栏插画选择、隐藏和恢复默认；默认庆祝图，本地重启及完整备份恢复保留偏好，隐藏释放空间，不提供自定义插画上传。
- 插画设置读写使用同一事务锁，旧异步设置响应不能覆盖新选择；保存失败恢复上次已保存的选项。窄屏也保留设置入口。
- 在线演示同步交互但仍只在当前页面保存，刷新重置；保持原有插画融合处理、固定五平台导航及源码换行规则。

## 2.2.8 - 2026-11-15

- 同版本重打包：Python、JS/CJS/MJS、CSS、HTML 统一 LF，Windows 批处理与 PowerShell 脚本使用 CRLF；安装器与 ZIP 使用同一规范化目录，发布检查增加换行门禁。核心源码与原 v2.2.8 标签逐字节一致，标签和版本号不变。
- 算法和比赛模块分别按蓝、青、绿、琥珀、玫红、紫六色循环分配，新建时确定颜色；名称、分类、筛选、拖动顺序、刷新及重启不改变已分配颜色。
- 存量模块按当前顺序补齐颜色，颜色和轮换进度随完整备份恢复；删除模块不会让其他模块变色，也不会回退轮换进度。
- 统一算法与比赛卡片的背景、图标强调色、边框和装饰配色，保留平台图标与平台徽标自身颜色；题目中的算法关联标识使用对应算法颜色。
- 在线演示同步六色分配规则，刷新仍重置演示改动；更新 README 的桌面和移动预览。
- 中文路径测试统一使用泛用的“测试用户 小林”，不再使用个人姓名；新增颜色持久化、旧数据兼容、备份恢复及真实浏览器回归。

## 2.2.7 - 2026-11-14

- 修复已有题目和模板在代码尚未保存时直接锁定，导致后续保存返回 code_locked 的问题；现在先保存修改，成功后再锁定。校验、保存或版本冲突失败时保留可编辑草稿。
- 锁定请求期间同步冻结代码与语言选择，避免慢请求中修改语言后再次触发锁定冲突。
- 编译器发现改为优先使用用户配置，其次查找系统 PATH，移除作者电脑的固定 D 盘路径；设置说明同步更新。
- 修复 Windows 中只在设置里指定 MinGW、未把工具链加入 PATH 时编译或运行失败的问题；仅为试跑子进程补充所选工具链的 DLL 搜索路径，不修改系统环境变量。
- 修复英文 Windows 环境中 MinGW 无法写入中文临时目录的问题：源码、输出程序和编译中间文件均使用隔离工作目录内的相对路径。
- 新增真实浏览器锁定回归，覆盖题目、模板、请求失败、版本冲突、重试和移动布局，并纳入 Windows 发布检查。
- 补充 Windows 中文及空格临时目录下的实际 C++ 编译运行回归。

## 2.2.6 - 2026-11-14

- 比赛内题目支持拖动和键盘上下调整顺序，刷新及重启后保留；与全部题目、算法题目顺序独立。旧数据库升级前自动备份，原有显示次序保持不变。
- 在线演示的下载和重置操作移至右上角顶栏，移除独立固定提示栏和侧栏高度偏移；演示说明保留在状态提示中。
- 明确 WebP 资源的 HTTP 图片类型，避免 Windows 类型关联缺失时侧栏图片无法显示。
- 更换侧栏庆祝插图；保留原图比例与完整文字，同步更新 README 界面预览，不改变版本号。
- 蓝桥杯、HDU、码蹄集在题目和比赛平台标识中使用本地打包的官网图标，不新增侧栏工作空间。
- 主操作改为蓝紫色，平台、算法和操作标识采用不同配色。
- 每道题目和每份模板新增默认关闭的代码锁定，锁定状态保存在本地数据库中并随备份恢复。
- 锁定后仍可全选、复制和试跑，修改源码或语言前需解锁。
- 代码预览新增全选和复制操作，预览中的 Ctrl+A 只选择当前代码。
- 侧栏插图支持等比缩放、柔化边缘和点击放大。
- 新增与真实数据隔离的 GitHub Pages 在线演示，支持会话内编辑、保存、锁定和复制；刷新重置，不执行本机系统操作。
- 更新 README 桌面及移动预览，使用 13 场比赛或选编、104 道题、12 类算法和 21 份模板；蓝桥杯省赛、国赛正确归入蓝桥杯，ICPC 横滨赛归入 Codeforces。

## 2.2.5 - 2026-11-01

- 修复代码选区终点位于文件末尾时漏掉最后一个字符的问题，末行背景只覆盖实际选择范围。
- 修复选择包含换行、横向滚动及调整窗口大小后出现的选区边界错误。
- 语法高亮层统一使用输入层的滚动偏移，避免滚到底部和滚动条占位时错位。
- 统一编辑器内注释与输入层的字体样式，改善中文、Tab 和页面缩放时的选区对齐。
- 在代码试跑、题目编辑和模板编辑页验证上述修复，覆盖全屏、小窗口和 100%～200% 页面缩放。

## 2.2.4 - 2026-11-01

- 将原生 `AlgoArchive.exe` 改为完整静态链接，移除对未随包分发的 MinGW GCC、libstdc++ 和 pthread DLL 的依赖。
- 新增启动器 PE 导入表校验，发布构建会拒绝重新引入上述运行库依赖。
- 修复 `start.bat` 未向应用透传 `--port`、`--data-dir`、`--config-path` 和 `--no-browser` 的问题；首个 `--create-shortcut` 仍只用于显式创建快捷方式。
- 安装器会规范化数据目录、拒绝相对路径，并在配置目录创建或写入失败时明确终止安装。
- 新增包含中文和空格路径的命令行参数回归测试。
- JSON 批量导入支持题目内的 `tests` 数组，并在返回结果中列出未识别的顶层字段。

## 2.2.3 - 2026-11-01

- 普通启动不再创建或恢复快捷方式，用户删除快捷方式后不会在下次启动时被强制恢复。
- 新增“设置 → 关于与诊断 → 创建快捷方式”操作，同时刷新桌面和开始菜单入口。
- `start.bat --create-shortcut` 支持显式创建或修复桌面及开始菜单快捷方式。
- 安装程序的桌面快捷方式改为可选任务，默认不勾选；开始菜单入口继续保留。
- 新增原生 `AlgoArchive.exe` 启动器，内置应用图标并保持便携目录移动后的相对启动。
- 修复 CI 下载的嵌入式 Python 未把程序目录加入模块搜索路径、导致发布包启动时找不到 `cph_runner` 的问题。

## 2.2.2 - 2026-11-01

- 移除与 `start.bat` 内容重复的 `启动.bat`，统一使用一个启动入口，并同步发布包与安装器。
- 移除重复的 `创建桌面快捷方式.bat`，桌面快捷方式继续由 `start.bat` 自动刷新。
- 修复 Windows 启动脚本换行符和 UTF-8 参数导致的 `cmd.exe` 命令碎片，并让发布构建强制使用 CRLF。

## 2.2.1 - 2026-10-31

- 修复题目与测试用例部分保存、并发覆盖和数据迁移期间遗漏修改的问题。
- 统一备份创建与恢复容量限制，支持 10,000 个以上成员，并在创建后校验完整性。
- 修复大输入绕开运行时限、截断输出误判通过，增加输出超限提示和子进程回收。
- 修复比赛详情和平台筛选因大小写、别名导致题目不可见，修正平台统计。
- 详细范围和验证见 TEST_REPORT.md 中的历史可靠性修复记录。

## 2.2.0 - 2026-10-30

- 新增 AcWing 工作区及独立平台统计，与 Codeforces、AtCoder、洛谷和牛客保持一致。
- 本地打包五个平台的官网图标，统一平台标签和比赛关联标签宽度，并优化浅色工作区导航。
- 首页统计精简为 7 项，保留比赛、题目和五个平台，使桌面宽屏保持一行显示。
- 比赛卡片和算法卡片支持拖动排序，增加版本冲突保护，并将数据库升级到 schema 9。
- 题目界面改为稳定的顺序编号，同时保留旧题库的内部编号数据。
- `/api/state` 从逐算法查询改为固定批量查询，并新增性能回归测试。
- 清理重复图标、过期截图、QA 产物和无用前端规则，并完善本地构建产物忽略规则。

## 2.1.6 - 2026-10-29

- Accept scheme-less domain links such as `example.com/problem/1` and
  `atcoder.jp` for problems, contests, and algorithm references, storing them
  with an HTTPS scheme while leaving notes and file names unchanged.
- Hide secondary problem-table columns at small widths so long Chinese titles
  wrap by word instead of one character per line.
- Match the VS Code light editor more closely with full-row blue selections
  and compact scrollbars without native arrow buttons.

## 2.1.5 - 2026-10-29

- Accept scheme-less links beginning with `www.` for algorithm references,
  problems, and contests, storing them with an HTTPS scheme.
- Keep free-form problem and contest notes unchanged when they contain spaces
  or do not represent a `www.` URL.
- Allow older stored `www.` links to remain clickable in the frontend.
- Add a `Copy link` action next to Edit and Original for valid problem links.
- Package a lightweight `自检.bat` with the portable ZIP and installer. It
  verifies core files and a temporary database without reading user data.

## 2.1.4 - 2026-10-29

- Reduced startup-window log noise by hiding successful static-file requests
  and repeated `/api/state` polling.
- Kept startup information, failed requests, warnings, exceptions, and concise
  records for successful create, update, and delete operations.

## 2.1.3 - 2026-10-29

- Fixed a Windows CI race where stopping a test run could be acknowledged
  before the compiler or student process was registered. A stopped runner no
  longer starts a new child process and now returns a cancelled result
  immediately.
- Added deterministic regression tests for stop-before-run and
  stop-before-process-launch behavior.

## 2.1.2 - 2026-10-29

- Added an actionable missing-compiler banner to the standalone code
  playground and per-problem test runner.
- The prompt links directly to compiler settings and explains that a complete
  MinGW-w64 toolchain is required, not just a copied `g++.exe`.
- Invalid explicitly configured compiler paths now report as unavailable
  instead of silently falling back to another compiler.

## 2.1.1 - 2026-10-29

- Added a standalone "Code Playground" workspace below All Problems in the
  sidebar for compiling and testing temporary C++ without creating a problem.
- Playground code, test cases, and time limit persist as a browser-local draft.
- Added a generic local compiler API shared with per-problem CPH testing.

## 2.1.0 - 2026-10-29

- Added a CPH-compatible C++ test-case panel with per-case and run-all
  execution, stop control, compile diagnostics, and CPH line-trim judging.
- Added `.prob` and JSON test-case import plus CPH-compatible `.prob` export.
- Test cases are stored in SQLite with the problem and survive backups,
  restarts, deletion, and schema upgrades.
- Defaulted C++ compilation to the current VS Code MinGW g++ 8.1.0 compiler
  with GNU++14, while allowing a custom compiler path and standard.
- Declared CPH author Divyanshu Agrawal, the upstream repository, reference
  commit, and GPL-3.0-or-later license in the app, third-party notices, and
  bundled license copy.

## 2.0.5 - 2026-10-28

- Added a built-in NowCoder workspace and NowCoder summary on the home page
  while preserving arbitrary platform input and unrestricted links.
- Added a NowCoder quick selection to the contest dialog.
- Recognized Luogu, NowCoder, and common NowCoder aliases across workspace
  filtering and counting.

## 2.0.4 - 2026-10-28

- Added a built-in Luogu workspace and Luogu summary on the home page while
  keeping arbitrary platform input and unrestricted competition links.
- Reworked the contest dialog into a compact two-column form with explicit
  Codeforces, AtCoder, and Luogu quick selections.
- Removed the browser-native platform suggestion overlay from the contest
  dialog so it no longer covers the footer actions.

## 2.0.3 - 2026-10-28

- Fixed startup failure when the installer wrote `config.json` using the
  Windows ANSI code page and the user profile contained non-ASCII characters.
- Read legacy UTF-8 BOM, UTF-16 BOM, Windows ANSI, and GB18030 configuration
  files while preferring a parsed `data_dir` that exists on disk.
- New installer configuration files are written as UTF-8 without a BOM.

## 2.0.2 - 2026-10-28

- Only show the installer data-directory page for a fresh current-user install,
  so the selected directory is never ignored by all-users or existing-config
  installations.
- Create the desktop shortcut automatically for installed and portable
  distributions.
- Clarify that users must download the Setup executable or Windows x64 ZIP,
  not GitHub's automatically generated source archive.

## 2.0.1 - 2026-10-28

- Added the project GitHub repository and author Aqiw labels to the top bar and
  About diagnostics.
- Updated release, download, documentation, and repository references to
  `Aqiw-source/AlgoArchive`.

## 2.0.0 - 2026-10-28

- Added per-user configuration with a saved custom data directory and explicit
  command-line override priority.
- Added safe data-directory classification, conflict detection, migration
  validation, and schema-version checks before database writes.
- Added browser selection, custom executable support, window mode fallback, and
  browser launch diagnostics.
- Added a tabbed settings interface for profile, browser, data management, and
  diagnostics.
- Added complete ZIP backup, import, restoration, rolling retention, and
  path-traversal protection.
- Added explicit graceful shutdown through the application interface.
- Added rotating local logs without request bodies or source-code contents.
- Added an Inno Setup installer with current-user/all-users privilege selection,
  custom program and data directory selection, and portable ZIP build scripts.
- Added Windows CI, release privacy checks, SHA-256 files, and release
  documentation.
