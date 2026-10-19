# RA2 / YR：macOS ARM64 与 Web

同一工程维护 macOS 原生版本和独立浏览器版本：原生版本编译为 ARM64，Web 版本编译为 WebAssembly，在浏览器本地运行。

## 项目结构

| 位置 | 内容 |
| --- | --- |
| `runtime/arm64/`、`runtime/win32hle-arm64/` | macOS ARM64 运行时与 Win32 接口实现 |
| `runtime/web/`、`web/` | Web 运行时适配、手机交互与网页入口 |
| `tools/`、`poc/` | 两个平台的构建、转换和检查脚本 |
| `deploy/vercel/` | 网页托管配置 |
| `docs/` | 架构、构建、验证与部署说明 |
| Vercel Blob | Web 程序与资源下载，不存入源码树 |

源码仓库：https://github.com/tinypoint/ra2-native 。Vercel 项目为 `ra2-web`。
资源和生成的游戏代码、本机构建产物留在被忽略的 `.local/`、`game/` 等目录。
Web 当前程序版本为 v0.1.5；移动端摇杆、菜单与加载界面仍在迭代。

- [Web 运行与缓存](docs/WEB_RUNTIME.md)
- [Vercel 和 Blob 部署](docs/VERCEL_DEPLOYMENT.md)

## macOS 验证记录

**状态：RA2 已编译为本机 ARM64，已验证遭遇战进入、建造、战斗结算，以及保存后退出进程再读档。124/124 项运行时检查通过。优化版本同速约 31.25 个逻辑帧/秒，CPU 约 43% → 36%，峰值内存约 261 → 235 MiB。仍为本地研究构建；YR、战役与长期稳定性尚未验证。**

2026-10-18，在本机 macOS ARM64 上实测：

| 验证 | 结果 |
| --- | --- |
| 上传安装包静态解包 | 取得 game.exe 和主要 MIX；音乐、过场资源不完整 |
| 完整游戏转换 | 23116 个函数、0 转换错误；168 个 no_terminator 项保留待回归 |
| 真实启动与主菜单 | Cocoa/Metal、640×480×16；已目视检查游戏帧，输入已验证，已显示遭遇战战场；已走到实际遭遇战积分结算 |
| 实际 HLE 集成检查 | 124/124；IAT 366 个注册处理器、2 个显式缺失入口，处理器覆盖不等于完整 API 语义 |
| 真实 game.exe 函数在 ARM64 上执行 | 10 个函数，110/110 个对照用例一致 |
| 真实函数的 guest 地址空间 | 在高于 4 GiB 的地址保留 4 GiB 虚拟窗口，按页提交图像与测试状态 |
| 上游完整工程 ARM64 配置 | 被 32 位宿主检查拒绝 |
| 上游 371 个语义用例 | `-O0`、`-O2` 各 370 个一致；各 1 个 NaN 符号位差异 |
| 自编 x86 合成函数经上游工具转换后运行 | 12/12 与 Unicorn x86 参考结果一致 |
| 上述本地测试可执行文件 | Mach-O 64-bit arm64 |
| 选取的 5 个 HLE 文件语法编译 | 4 个通过，1 个因 Darwin `struct stat` 字段不同失败 |

Unicorn 仅用来产生 x86 对照结果。被验证的 C 程序由 Apple Clang 编译，直接作为 ARM64 程序运行。真实函数覆盖坐标复制与换算、字段重置、虚表调用/尾调用及 double 读取；使用受控的对象和内存状态，该隔离测试本身不模拟完整一局；后续完整启动证据单列记录。第一批合成调用测试作为独立历史证据保留。

## 阅读入口

- [完整 ARM64 运行时与启动日志](docs/NATIVE_RUNTIME.md)
- [性能对照](docs/PERFORMANCE.md)
- [存档与对局证据](docs/SAVE_LOAD.md)
- [决策与下一步](docs/ROADMAP.md)
- [ARM64 证据与边界](docs/ARM64_FEASIBILITY.md)
- [仓库审计](docs/REPO_AUDIT.md)
- [授权范围记录](docs/LICENSE_AUDIT.md)
- [架构选项](docs/ARCHITECTURE_OPTIONS.md)
- [构建与复现](docs/BUILD_LOG.md)
- [机器可读结果](logs/native-results.json)
- [真实游戏函数验证](docs/REAL_GAME_POC.md)
- [真实函数完整结果](logs/real-game-results.json)

## 复现

需要 Git、Apple Command Line Tools、Python 3.12 和 uv；所有 Python 包均安装在项目内虚拟环境。

```sh
cd /Users/zz/Projects/ra2-native
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python poc/bootstrap.py
.venv/bin/python poc/run_native_checks.py
.venv/bin/python poc/check_hle_compile.py
```

当前最后两条命令都预期返回 **1**：分别保留真实的差分失败与平台编译失败，不将其隐藏或改为成功。每条命令、编译器诊断和运行结果保存在 `logs/`。

用户上传游戏输入后新增的实验：

```sh
.venv/bin/python poc/run_real_game_checks.py --exe game/ra2-upload-41bbcc83/game.exe
```

该实验预期返回 **0**。脚本固定当前已审计输入的 SHA-256，自动恢复 RTTI，再从文件生成真实函数；生成代码和本地内存图像留在被 Git 忽略的 `poc/generated_game/`。安装包静态提取步骤见 REAL_GAME_POC。

上游仓库固定在 `repos.lock.json` 的提交；`vendor/` 保持原样，不纳入本工程 Git。生成物和游戏文件也不纳入 Git。实验不执行原始 x86 游戏程序，不安装 Wine、Rosetta 或虚拟机。

两个平台的源码集中维护在本仓库；Web 游戏资源和程序下载由 Vercel Blob 托管。

本机交互研究构建：`.venv/bin/python tools/launch_native_game.py`，或打开 `.local/Red Alert 2 ARM64 Optimized.app`。应用包由 `tools/package_local_app.py` 生成，绑定当前资源目录；遭遇战结算与跨进程存档恢复已验收；YR 待验收。
