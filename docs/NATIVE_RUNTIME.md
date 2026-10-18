# 实际 ARM64 运行时移植与启动实验

> 后续验收（2026-10-18）：优化构建、124/124 项运行时检查、真实跨进程保存/加载，以及一局遭遇战到积分结算均已验证。性能与边界见 [PERFORMANCE](PERFORMANCE.md)、[SAVE_LOAD](SAVE_LOAD.md)。下文先前的 100 项检查及“待验收”描述保留其历史阶段含义。

2026-10-18。此阶段在用户上传的 game.exe 上执行，已经超出隔离函数 PoC；已目视确认主菜单、菜单输入以及默认遭遇战战场；基地车选择与展开已验证，完整一局和正式安装包仍待验证。

## 实现范围

在 `runtime/win32hle-arm64/` 保留并改造 pcrecomp 的实际 HLE 源码；来源固定为 `bd26806fbd4714d670d2dee75973c5eaff64674c`，MIT 许可证随源码保留。逐文件来源与改造散列见 `logs/arm64-runtime-source-manifest.json`。上游 vendor checkout 保持原样。

主要改动：

- `runtime/arm64/guest_memory.c` 保留 4 GiB 虚拟窗口，使用 guest VA 管理 PE、堆、线程栈与 TIB。宿主地址高于 4 GiB；guest 0 保持不可访问。
- HLE 的 A32/APTR/ASTR/RETP 经明确地址转换，拒绝将 arena 外的宿主指针截断给游戏。
- guest 分配与宿主对象分开；句柄表继续存储完整宿主指针。命名互斥量使用独立句柄共享对象，最后一个句柄关闭后才释放对象。
- 实际 PE 加载器将区段复制到 guest 窗口，填零 BSS、绑定 IAT，并拒绝范围冲突。添加文件/区段范围检查；没有把整个上传程序作为宿主可执行映射。
- 线程保存与回调恢复补全标志、SSE、MXCSR 和 GS 状态；线程栈与 TIB 不再用原生 malloc 指针截断。
- CRT 环境块、命令行、区域回调字符串和 COM 临时参数转为 guest 内存；文件时间改用 Darwin 的 stat 字段。
- 模块、资源目录、文件读写、Winsock 中 hostent 的嵌套地址及 COM 虚表/BSTR 都经 guest 地址转换。
- CreateThread、CREATE_SUSPENDED、ResumeThread、完成等待和 GetExitCodeThread 已移植；不再把 pthread 指针截断充当线程 ID。RtlUnwind 明确报未实现，不静默跳过。
- 消息泵未接入时，WSAAsyncSelect 明确失败；没有声称联机已经可用。

这些源文件只实现了原 HLE 的一部分，不允许把其余仍直接转换指针的上游文件混入 ARM64 目标。

## 运行时集成测试

```sh
.venv/bin/python tools/check_arm64_runtime.py
```

最终结果以 `logs/arm64-runtime-results.json` 为准。当前 **100/100** 检查通过，覆盖：

- 从原始 game.exe 文件装载 PE，拒绝同地址重复装载，绑定全部 368 个导入。
- HeapAlloc/HeapReAlloc/HeapSize/HeapFree、零初始化和增长时填零。
- VirtualAlloc reserve/commit、邻页隔离、decommit/recommit 填零、只读保护、释放及失败路径。
- CRT 环境块、GetSystemInfo、模块句柄、动态 GetProcAddress 和实际文件读取/时间戳。
- 从 HLE 回调到真实游戏坐标函数，恢复 caller 栈、TIB、标志和 SIMD 状态。
- 两个线程在 Sleep 让出执行权后保持各自状态；多媒体定时器进入显式 guest 回调并可停止。
- Winsock 初始化、IPv4 文本和 localhost 的 PE32 hostent 嵌套指针；没有验证局域网游戏。
- COM 对象、虚表和 IUnknown 引用计数，BSTR 的长度前缀与释放。
- 命名互斥量的独立句柄、共享存活期和最后关闭后的名称移除。
- 挂起线程、恢复、线程 ID、完成等待和退出结果；WaitAll 超时不得部分消费自动重置事件。
- 窗口 CREATESTRUCT 嵌套指针、类 atom、PE32 变参格式化。
- DirectDraw Lock 返回可写 guest 像素，Release 释放自有像素并保留外部像素。
- DirectSound PCM buffer 的 guest 指针，以及 Bink 缺失文件的失败与错误字符串。

当前集成测试 IAT 中 362 个导入绑定到已注册 HLE 处理器，6 个绑定到**被调用即报错**的缺失入口。“绑定成功”不代表这些 API 已全部实现或通过完整语义验证。

最初一次测试错误地断言宿主指针的低 32 位一定与 guest VA 不同；当 arena 刚好位于 4 GiB 的整数倍地址时，这个断言不成立。初次失败原样保留在 `logs/arm64-runtime-first-execution.log`；修正为同时检查宿主指针确实超过 4 GiB，以及显式双向地址转换。未放宽真实数据或 API 行为比较。

## 完整程序转换与构建

```sh
.venv/bin/python vendor/pcrecomp/tools/disasm/disasm32.py \
  game/ra2-upload-41bbcc83/game.exe --output .local/ra2-functions.json \
  --seed-functions poc/generated_game/rtti-seeds.json
.venv/bin/python tools/lift_game_for_arm64.py
.venv/bin/python tools/bootstrap_native_graphics.py
.venv/bin/python tools/bootstrap_native_movies.py
.venv/bin/python tools/build_native_boot.py
```

函数目录 23111 个条目；提升闭合后 23116 个函数、0 个未提升 stub、0 个提升错误。上游统计另有 168 个 `no_terminator` 项，不能隐藏；这些项和目录完整性仍需实际执行回归验证。

生成约 578 万行 C，首次编译生成 ARM64 Mach-O 启动探针，随后接入 SDL Cocoa/Metal 显示与 CoreAudio。当前用 `-O0` 降低探索阶段构建成本，使用 `RECOMP_LOCAL_REGS`、`-fwrapv`、`-fno-strict-aliasing`，未启用 fast-math。没有性能结论。

`tools/lift_game_for_arm64.py` 调用固定版本的上游驱动，禁用该驱动的 remaster 补丁与自定义 hook；不将此上传版本默认当成与 Steam 全字节相同版本。生成代码和可执行文件全部留在 `.local/`，不纳入 Git、不分发。

## 实际进入启动入口

```sh
.venv/bin/python tools/run_native_boot.py --attempt review
```

历次原始日志、退出码与阻塞：

| 尝试 | 实际结果 |
| --- | --- |
| 1：核心 HLE | 进入 CRT，完成部分堆/TLS 初始化；停在缺失的 GetStdHandle |
| 2：接入 CRT、文件和模块 | 继续通过代码页/环境初始化，停在 timeGetTime |
| 3：接入时钟 | 585 次接口调用，停在 wsock32.dll#115（WSAStartup） |
| 4：接入 Winsock | 1326 次接口调用，停在 OleInitialize |
| 5：接入 COM | 2023 次接口调用，执行 ExitProcess(0)；并未进入菜单 |
| 6–8：启动器协议与注册表 | 确认真实错误提示，定位 Blowfish COM 和模块路径问题 |
| 9：资源服务 | 实际 MIX 文件读取、解密；停在 CreateThread |
| 10：线程 | 约 8.1 万次接口调用，停在 GetSystemMetrics |
| 11：窗口层 | 停在 DirectDrawCreate |
| 12：DirectDraw | Cocoa/Metal 窗口、640×480×16 主表面；停在 DirectSound |
| 13：DirectSound | CoreAudio 44100 Hz 初始化，停在 Bink；导出的首帧是黑屏 |
| 14–15：明确的无解码器失败 | 返回 NULL 后，游戏的视频句柄路径访问空指针；未伪造视频对象 |
| 16：真实 Bink 解码 | 从 MIX 内解码 472×450、431 帧、15 fps 动画；实际显示 640×480 繁体中文主菜单，20 秒探针由 watchdog 退出 |
| 17：单人菜单点击 | 实际注入鼠标按下/抬起，已显示单人游戏子菜单 |
| 18–19：遭遇战 | 20 秒不足以完成加载；60 秒探针已显示遭遇战设置，未证明开局 |
| 20：开始遭遇战 | 默认地图已加载，实际显示部队、基地车、战争迷雾及资金栏；未完成整局 |
| 21：定时选择尝试 | 游戏出生布局有变化，定时坐标没有选中基地车；不算操作成功 |
| 22：实时输入 | 根据画面选择基地车，发送 D 键；建造厂与发电厂建造图标已出现 |

第五次的正常退出不是成功启动游戏。阅读实际函数后确认，上传版本的 `0x004918F0` 仍检查 Windows 启动器创建的命名互斥量；在没有启动器协议对象时，`Startup.CPP` 的路径提前返回。此上传版本与上游说明中已修改该检查的 Steam 版本不能混为一谈。

宿主增加显式的 `--with-launcher` 模式，由 Mac 宿主创建游戏原来期望的命名互斥量和通知事件，承担启动器职责。游戏字节、检查函数及 GetLastError 的一般语义均未打补丁。

```sh
.venv/bin/python tools/run_native_boot.py --attempt launcher --with-launcher
```

该模式的实际后续结果单独记入对应的 `logs/native-boot-attempt-*.json/.log`。不能将提供协议对象本身描述成已进入菜单。

## 仍需解决的架构边界

- 初始 guest 分配器每次以宿主页分配，优先验证正确性，没有针对游戏堆吞吐与碎片优化。
- 保护、decommit 采用 16 KiB 宿主页粒度，细于此粒度的请求明确失败；不是完整 Windows 4 KiB 页面语义。
- 虚拟 RDTSC 用单调纳秒计数器表达为 1 GHz，不能宣称 x86 周期精确；CPUID、浮点、线程/异常仍需更完整验证。
- 正常返回的 CreateThread 线程会回收栈/TIB；ExitThread、异常展开和部分线程私有返回字符串的完整生命周期仍需补齐。
- 窗口/消息泵、DirectDraw 和 DirectSound 已经在实际启动中执行，存档、完整一局、完整资源内容及帧率尚未验证。上游 WINMM 的无声设备处理不能作为音频成功证明。
- 上传包缺少完整音乐和过场；不改变此前输入来源与资源完整性的限制。

首个主菜单验证记录：`logs/native-boot-attempt-16-bink-decoder.json`。原始大日志 gzip 无损压缩，导出的游戏画面保留在忽略的 `.local/native-boot/menu-verified.png`。20 秒 watchdog 的退出码 124 是限时结束，不能写成完整游戏正常结束。

交互研究启动：`.venv/bin/python tools/launch_native_game.py`。此入口关闭探针 watchdog 和逐接口日志，不注入点击，运行结果写入 `logs/native-interactive.log`；尚未作为可玩版本验收。

本机研究应用可用 `tools/package_local_app.py` 创建在 `.local/Red Alert 2 ARM64.app`，包含 ARM64 二进制与 SDL frameworks。仅以 ad-hoc 本地签名，未公证；游戏资源通过本机目录配置引用，没有复制进应用，也没有发布。该本机包不等于可跨机器安装的正式产品。

应用包通过 LaunchServices 实际启动并显示主菜单，15 秒测试由 watchdog 结束，非正常通关退出。记录：`logs/local-app-verification.json`、`logs/local-app-game.log`。基地车操作证据：`logs/native-boot-attempt-22-live-input.json`。
