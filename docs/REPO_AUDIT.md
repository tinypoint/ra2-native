# 第一批仓库审计

日期：2026-10-18（Asia/Shanghai）。范围：用户明确优先的 macOS ARM64 原生路线。证据分为源码观察、本机实测、作者声明；三者不互相替代。

后续进展：用户上传包已静态提取，真实函数隔离对照和完整 ARM64 启动均已执行。目前已目视验证主菜单、单人子菜单与遭遇战设置；尚未完成一局。见 [REAL_GAME_POC](REAL_GAME_POC.md) 与 [NATIVE_RUNTIME](NATIVE_RUNTIME.md)。以下审计记录描述各自当时的验证范围。

## redalert2-recomp

- 地址：https://github.com/sp00nznet/redalert2-recomp
- 本次 HEAD：`ffc982534951acec02211cc79f9ed1a734bddc16`。
- 提交时间：2026-10-17T04:15:03-07:00；标题：`Pause menu: no full-width flash when it opens a screen (#12)`。近期有维护，但未审计完整历史或维护承诺。
- 作用：RA2/YR 的 PE 分析、函数发现、C 提升驱动、游戏宿主和补丁；依赖同级 pcrecomp。`run_lift.py:36` 起导入共享工具，不是另一套独立提升器。
- 授权：LICENSE 前段为 MIT，后段误写 The Movies，且明确不将 MIT 延伸到转换后的游戏代码。详见 LICENSE_AUDIT。
- 平台：`CMakeLists.txt:14` 强制 `sizeof(void*) == 4`；`:45` 起是 Linux 分支，后续是 MSVC x86 分支；无本地 Darwin ARM64 构建分支。Mac 的 Wine 说明不算原生 ARM64 支持。
- 功能声明：README 声称 RA2、YR、菜单、遭遇战、战役、存档及部分局域网功能已运行。**本次没有独立验证任何游戏功能，也未验证 MOD 与联机。**
- 必要输入：用户游戏目录中的 `game.exe`（RA2）或 `gamemd.exe`（YR）、原版数据及相应 DLL；转换后的 C 不随仓库提供。`run_lift.py:61` 起默认输入为 `game/gamemd.exe`。
- 上游构建：Windows 为 `run_lift.py --all` 后 `build.cmd`；Linux 为 `setup.sh` / `build-linux.sh`，要求 i386 工具链及对应 SDL2、字体、ffmpeg 开发库。这里只阅读脚本，未执行自动安装。
- 本机复现：直接尝试 CMake ARM64 配置，按设计在 32 位检查处失败，见 `logs/upstream-cmake-arm64.log`。没有进入实际游戏源码编译。
- 可复用价值：提升驱动、地址目录生成、部分游戏接口与行为补丁；宿主内存和 ABI 假设需改造，不能直接照搬 `src/linux/main.c`。
- 额外发现：`src/linux/main.c:58` 起用 i386 栈数据构造 `va_list`；`src/linux/blowfish.c:30` 起把对象中存放的 32 位值转成宿主指针。这些路径须逐项审计。

## pcrecomp

- 地址：https://github.com/sp00nznet/pcrecomp
- 本次 HEAD：`bd26806fbd4714d670d2dee75973c5eaff64674c`。
- 提交时间：2026-10-15T22:13:38-07:00；标题：`lift32: rep movs into itself repeats the source, as the CPU does (#102)`。
- 作用：共享 x86 提升器、核心语义、PE 加载器、Win32 HLE 与测试；不是游戏引擎成品，也不自带 RA2/YR。
- 授权：LICENSE 为 MIT，并声明不包含所转换软件的授权；工具依赖 Capstone、pefile，测试参考为 Unicorn。该声明未代替逐文件来源审计。
- 模型：`runtime/recomp32/recomp_types.h` 中寄存器与游戏地址保持 `uint32_t`；宿主函数地址使用 `recomp_func_t`。`:168` 起提供 flat 与 base-offset 两种内存模式。
- 平台：完整 Win32 HLE 的文档构建为 `-m32` Linux；`native32` 则依赖 MSVC x86。**本次确认部分核心能在 ARM64 执行，不等于完整 runtime 已支持 ARM64。**
- 测试：未修改的 `tools/lift/difftest.py` 在本机运行 371 个用例，370 一致、1 失败；本工程另外以固定路径、显式 `-arch arm64`、`-O0/-O2` 复现同一结果。
- HLE 文件：`host_lite.c`、`pe_loader.c`、`kernel32.c`、`wsock32.c` 的单文件语法编译通过；`kernel32_ext.c` 因 `st_mtim/st_atim` 失败。语法通过不证明可正确运行。
- 已知阻塞：APTR/ASTR/RETP、PE 映射、线程栈/TIB、堆及游戏扩展仍依赖宿主与 guest 地址相同。详见 ARM64_FEASIBILITY。
- 64 位工具链区别：`recomp64_cpu` 处理 x86-64 客体，不自动解决当前 PE32 游戏在 ARM64 宿主上的问题。
- 可复用价值：本轮首选的提升器与核心语义来源；适合先建设 guest 地址转换边界，再逐步移植 HLE。

## 其他候选的状态

任务书列出的 Chrono Divide、StillM8、RA2WEB、Apple WebKit 封装、其他 TS forks、RA2 VM、RA2YR_ReSource、OpenRA/OpenCE 及其技术参考，**本轮尚未克隆或完成授权、代码关系、构建和游戏验证**。不将它们计为独立可用引擎，不声称已完成全清单仓库审计。

用户已选择优先讨论真正 ARM64 原生，因此本批先验证两个核心仓库；网页封装复现仍属待办，不作为本次成功成果。

## 固定证据

所有源码路径均相对于 `vendor/<仓库>/`。两个 checkout 未作修改；提交号保存在 `repos.lock.json` 和 `logs/environment.json`。完整命令与当前结果参见 BUILD_LOG。
