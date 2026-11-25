# 当前交付验证记录

## v2.5.0（2026-11-25，Windows x64）

基线提交 `85ffad7`；以下记录针对由此生成的 2.5.0 候选版本，归属发布标签 `v2.5.0`。

- `python -X utf8 scripts/run_backend_tests.py`：220 项通过（178.146 秒），包括缺少手册脚本的 ZIP 必须被拒绝。
- 设置 `ALGOARCHIVE_FULL_LAYOUT=1` 运行 `scripts/run_browser_tests.ps1`：16 组 Edge 回归通过；Node 演示 17 项、统计 5 项通过。Edge 158.0.4370.33。
- `node tests/test_settings_navigation.cjs`：本机随机端口下，四个手册入口打开预期设置；相同四个入口在静态演示子路径上均未发出 API 网络请求。另测刷新、浏览历史、键盘焦点、未保存编辑、慢响应与离线提示。
- `scripts/check-docs.ps1` 检查 10 个 HTML 页面的本地资源与章节锚点。便携包与安装器构建后核对版本，使用包内 Python 启动隔离服务，核验健康接口、题目增查改删及正常退出。
- 在临时目录实际创建 Windows .lnk，确认目标、工作目录和空参数。为启动测试副本添加隔离参数后，实际打开 2.5.0 并正常退出。浏览器中的创建请求使用模拟响应，未在真实用户桌面或开始菜单写入快捷方式。

未覆盖：全新 Windows 系统上的交互式安装与卸载、不同 Windows 版本及安全软件组合。

历史验证记录（截至 v2.4.0）：[docs/history/TEST_REPORT-through-2.4.0.md](docs/history/TEST_REPORT-through-2.4.0.md)。其中较早记录中的未完成项、许可状态和发布状态仅描述各自版本及测试当时的状态；项目目前自有代码的许可见根目录 [LICENSE](LICENSE)。
