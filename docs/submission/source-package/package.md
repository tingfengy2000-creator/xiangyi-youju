# 评审源码包（乡艺有据-源码与程序）

- 交付位置：`E:\竞赛\交接\提交材料\乡艺有据-源码与程序\` 与同名 `.zip`（192 个文件，约 1.5 MB，SHA-256 `8384d69c0b95a4f72a4b487de7bc96f7af60799c31bf4e9bbcf6b2daf3ac32f6`）。
- 源码：`git archive` 自 main `47277c1`，只保留 backend、frontend、data、运行与测试脚本、tests/backend、tests/e2e 中 4 个界面与实机脚本、tests/acceptance 两份留出集；去掉 test_data_versions.py（依赖仓库历史）。
- 清理：测试中机器代号改为中性名称（如 `DRAFT_REAL_RUN`），外部地址改为 `example.invalid`；package.json 只留 test、test:live、test:modules。
- 新增：`README.md` 与三个启动脚本；仓库中存为 `deploy.bat`→`部署.bat`、`start.bat`→`启动.bat`、`prototype.bat`→`界面原型.bat`，包内为 UTF-8、CRLF。
- 运行记录与样例：5 条真实运行记录（宣传片素材 v2）、两份手册预览稿、24 项内部对照实验协议、结果与首次运行原始记录；说明见 `evidence-readme.md`。
- 运行说明：`node scripts/submission/build-source-guide.cjs 源码运行说明.docx`，再用 LibreOffice 转 PDF（12 页）。
- 检查：包内 `pytest tests/backend` 271 passed；界面原型 e2e 通过；`--api-only` 健康检查通过；敏感字符串扫描无命中。
