# RA2 / YR macOS ARM64 原生可行性实验

目标：将原版游戏逻辑静态转换、编译为 ARM64，使用本地运行时提供系统接口。

**状态：第一批源码审计与合成实验完成；没有运行真实 RA2/YR 游戏函数，没有启动游戏，没有可玩的 .app。任务书要求的真实游戏函数 PoC 尚未通过。**

2026-10-18，在本机 macOS ARM64 上实测：

| 验证 | 结果 |
| --- | --- |
| 上游完整工程 ARM64 配置 | 被 32 位宿主检查拒绝 |
| 上游 371 个语义用例 | `-O0`、`-O2` 各 370 个一致；各 1 个 NaN 符号位差异 |
| 自编 x86 合成函数经上游工具转换后运行 | 12/12 与 Unicorn x86 参考结果一致 |
| 上述本地测试可执行文件 | Mach-O 64-bit arm64 |
| 选取的 5 个 HLE 文件语法编译 | 4 个通过，1 个因 Darwin `struct stat` 字段不同失败 |

Unicorn 仅用来产生 x86 对照结果。被验证的 C 程序由 Apple Clang 编译，直接作为 ARM64 程序运行。合成函数覆盖对象虚表、thiscall、stdcall、返回栈平衡、本地 shim 和回调；没有用合成结果代替原版游戏验证。

## 阅读入口

- [决策与下一步](docs/ROADMAP.md)
- [ARM64 证据与边界](docs/ARM64_FEASIBILITY.md)
- [仓库审计](docs/REPO_AUDIT.md)
- [授权范围记录](docs/LICENSE_AUDIT.md)
- [架构选项](docs/ARCHITECTURE_OPTIONS.md)
- [构建与复现](docs/BUILD_LOG.md)
- [机器可读结果](logs/native-results.json)

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

上游仓库固定在 `repos.lock.json` 的提交；`vendor/` 保持原样，不纳入本工程 Git。生成物和游戏文件也不纳入 Git。实验不执行原始 x86 游戏程序，不安装 Wine、Rosetta 或虚拟机。

这是本地研究工程，尚未发布到社区或创建远程仓库。
