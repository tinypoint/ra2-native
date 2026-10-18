# 构建与运行记录

## 性能、保存恢复与结算（2026-10-18）

`tools/build_native_boot.py --profile release` 构建独立 -O2 本机版本；同 GameSpeed=2 对照见 PERFORMANCE.md。新增 storage.c 与实际 fsync，124 项检查通过，见 logs/arm64-runtime-results.json。先前缺失 StgCreateDocfile 的保存尝试已修复，实际新进程读回 880640 字节保存文件，恢复帧计数 1688 并继续游戏到最终结算。见 SAVE_LOAD.md 及对应 JSON。

`tools/package_local_app.py --profile release` 生成本机优化应用。输入资源仍在外部游戏目录，不纳入应用或 Git。

日期：2026-10-18（Asia/Shanghai）；工程目录 `/Users/zz/Projects/ra2-native`。

所有代码操作在独立新目录进行。原聊天目录为另一个项目，访问持续无响应，本次没有对其写入。未运行上游自动安装脚本，未安装系统级依赖，未下载游戏整合包，未创建或发布远程仓库。

## 固定环境和来源

- 完整元数据：`logs/environment.json`。
- Clang：`logs/clang-version.log`；macOS：`logs/macos-version.log`。
- 上游提交：`repos.lock.json`；干净 checkout 校验：`logs/pins-verification.log`。
- Python 包版本：`requirements.txt`；安装记录：`logs/dependencies.log`。
- 首次依次克隆 redalert2-recomp、pcrecomp，使用 GitHub HTTPS 和 `--depth 1`；没有运行克隆内容中的 setup。

```sh
git clone --depth 1 https://github.com/sp00nznet/redalert2-recomp.git vendor/redalert2-recomp
git clone --depth 1 https://github.com/sp00nznet/pcrecomp.git vendor/pcrecomp
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python poc/bootstrap.py
```

未来复现应以 bootstrap 固定提交；当前分支 HEAD 可能变化，不能仅重跑 shallow clone 就当作同一实验。

## 实验 1：原样工程 ARM64 配置

```sh
.venv/bin/cmake -S vendor/redalert2-recomp -B poc/build-upstream-arm64 -G Ninja \
  -DCMAKE_MAKE_PROGRAM=/Users/zz/Projects/ra2-native/.venv/bin/ninja \
  -DCMAKE_OSX_ARCHITECTURES=arm64
```

结果：退出 1，`CMakeLists.txt:15` 报 `the host must be 32-bit`。日志：`logs/upstream-cmake-arm64.log`。这是配置失败，未声称开始完整编译。

## 实验 2：未修改的上游差分脚本

```sh
RECOMP_CC=/usr/bin/clang .venv/bin/python vendor/pcrecomp/tools/lift/difftest.py --keep
```

结果：退出 1，370/371 与 Unicorn 一致，`sse.sqrtps` 的一个 NaN 符号位字节不同。日志：`logs/upstream-difftest.log`。临时生成目录由上游创建，不作为交付路径；下一个实验在项目内重新生成同一组案例。

## 实验 3：固定 ARM64 构建与合成桥接

```sh
.venv/bin/python poc/run_native_checks.py
```

结果：退出 1（保留语义失败）。`logs/native-results.json` 是完整机器可读结果。

- 生成文件：`poc/generated/upstream_cases.c` 与 `synthetic_bridge.c`，可随时由脚本重建。
- 显式 `clang -arch arm64`，`-fno-strict-aliasing -fwrapv -ffp-contract=off`；上游用例分别 `-O0`、`-O2`，合成桥接为 `-O2`。
- 上游：两个优化级别均 370/371，失败均为同一 `sse.sqrtps`；未屏蔽失败、未启用 fast-math。编译有空循环体警告，完整保留。
- 桥接：global/local register 模式 × 6 个边界输入，12/12 通过。
- 精确编译命令：`logs/*-compile.log`；架构证明：`logs/*-file.log`；执行状态：`logs/*-execution.log` 及各 bridge 输入日志。
- 平台探针：`logs/platform-probe.log`；Mach-O 映射布局：`logs/platform-probe-load-commands.log`。

## 实验 4：原样 HLE 文件的 macOS 语法编译

```sh
.venv/bin/python poc/check_hle_compile.py
```

结果：退出 1；4/5 文件语法接受，kernel32_ext.c 因 Linux stat 时间字段失败。日志：`logs/hle-compile-results.json`、`logs/hle-*.log`。仅 `-fsyntax-only`，未链接或运行完整 HLE。

## 本批限制

没有真实游戏文件，因此任务书中“选取真实 lifted game function”的实验、完整游戏启动和两个平台的游戏结果对照未完成；本次成功项均限于合成或上游语义测试。未测试画面、帧率、CPU、内存峰值、音效、存档、战役、遭遇战、联机、MOD 或可安装 .app。

所有失败保持可见；本批没有为了让结果变绿修改上游代码。下一步计划见 ROADMAP。

## 后续实验 5：上传输入与真实游戏函数（同日）

用户上传 `红警1.06原版.exe` 后关闭临时上传服务，静态解包得到 game.exe 与部分资源。实际提取和输入核验见 [REAL_GAME_POC](REAL_GAME_POC.md)，此前“无文件”限制是历史状态。

```sh
.venv/bin/python vendor/pcrecomp/tools/pe/pe_analyze.py \
  game/ra2-upload-41bbcc83/game.exe --json logs/game-pe-analysis.json --hash
.venv/bin/python poc/run_real_game_checks.py --exe game/ra2-upload-41bbcc83/game.exe
```

结果：退出 0；10 个真实函数，110/110 测试一致。完整结果 `logs/real-game-results.json`；编译与架构日志 `logs/real_game_*.log`；RTTI 来源日志 `logs/real-game-rtti.log`。程序自动生成并保存来源元数据，游戏字节与生成代码仍不纳入 Git。

该成功只对应真实函数隔离测试，不改变先前 NaN 差异和 HLE 编译失败，也不证明完整游戏已可玩。原生宿主的这次运行没有执行安装包和原版 x86 程序作为 macOS 宿主代码。

## 完整 ARM64 运行时与主菜单

后续已实现统一 guest arena 和实际 HLE 移植，将 23116 个函数编译进 ARM64 Mach-O。SDL2/SDL2_ttf 的官方 framework 和 FFmpeg Bink 最小静态库仅安装到 `.local/`。100 项运行时检查通过，实际主菜单输出已目视确认。完整命令、版本、退出码和边界见 [NATIVE_RUNTIME](NATIVE_RUNTIME.md)；此前配置/编译失败记录作为历史证据保留。

本机 `.app` 打包记录：`logs/local-app-package.log`。框架 rpath 改为 bundle 相对地址，`codesign --verify --deep --strict` 通过；签名为本地 ad-hoc，未公证、未发布，原版资源目录在 bundle 外。
