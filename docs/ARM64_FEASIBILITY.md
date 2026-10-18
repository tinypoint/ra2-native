# ARM64 可行性：第一批实测

最新进展：用户上传游戏文件后，已完成 **10 个真实 RA2 函数、110/110 个受控对照用例**，见 [真实函数 PoC](REAL_GAME_POC.md)。真实函数仍未覆盖完整运行时；游戏没有启动。下文主要保留先前无游戏文件时的第一批实验记录。

## 本机环境

macOS 27.0.1，arm64；Apple Clang 21.0.0；项目 Python 3.12.13。指针 64 位，`long double` 64 位，页大小 16384 字节。实际输出见 `logs/environment.json`、`logs/platform-probe.log`。

本次所有被测 C 二进制都以 `clang -arch arm64` 编译；`file` 输出为 `Mach-O 64-bit executable arm64`。Unicorn 执行 x86 指令仅作为语义参考，未嵌入被测本地二进制。

## 观测与含义

| 实验 | 结果 | 能说明什么 |
| --- | --- | --- |
| 原样完整工程配置 | CMake 拒绝非 32 位宿主 | 上游构建不能直接用于本目标 |
| 原样上游差分脚本 | 370/371 一致 | 核心非 flat 内存模式具备本机执行基础 |
| 显式 ARM64，O0/O2 | 各 370/371 一致 | 这组结果未随这两种优化级别变化 |
| 原创虚表/导入/回调 fixture | 12/12 一致 | 本轮覆盖的单线程调用链无需 x86 宿主 ABI |
| malloc 指针与低地址 mmap hint | malloc 超过 4 GiB，hint 未落在 0x00400000 | 不能把本次实际宿主指针直接截为 32 位 |
| Mach-O 加载命令 | 本实验 __PAGEZERO 大小 0x100000000 | 当前默认链接布局占住低 4 GiB；不是对全部链接策略的不可能性证明 |

合成链路：guest 对象保存 32 位虚表地址；虚表保存 guest 函数地址；转换后方法更新对象；经 guest IAT 调用原创 C shim；shim 再调用转换后的 stdcall 回调。内存始终分配在 4 GiB 以上。六个输入包含有符号边界与无符号回绕；分别使用 global/local register 模式。核对 EAX、ESP、对象写回、shim 与 callback 次数；**没有全面核对所有寄存器、标志、并发和异常。**

## 保留的语义失败

`sse.sqrtps` 对负数 `-2.25f` 开平方根产生 NaN，输出字节 `0x00410107`：ARM64 C 为 `0x7f`，Unicorn x86 为 `0xff`；该差异对应 NaN 符号位。`lift32_sse.py:37` 将其表达为 `sqrtf`。

O0/O2 结果一致。本轮未修改比较策略、未忽略 NaN 位、未宣称全部通过；测试脚本因此返回 1。下一步需用受控 x86 硬件执行再确认参考行为，并决定是否需要精确模拟这些位。当前未证明 RA2/YR 会执行此 SSE 路径。

## 必须改造的边界

1. **地址模型**：`recomp_types.h:168` 有非 flat 的 `ADDR` 支持，可复用；但 HLE 的 `win32hle.h:41` 直接解引用 guest ESP，`:45` 和 `:46` 直接把 guest 指针当宿主指针，`:52` 把宿主指针截断返回。仅关闭 `RECOMP_FLAT_MEMORY` 不够。
2. **分配与加载**：`host_lite.c:105` 起的 TIB、`:120` 的线程栈，`pe_loader.c:80` 起的 PE 映射都依赖同址模型。游戏堆、数据、栈必须进入统一 guest 地址空间，宿主资源保留真实指针。已有 `host_lite.c:283` 起的 handle 表能存 `void*`，值得保留，不能误判所有 HANDLE 都要重写。
3. **macOS 接口**：`kernel32_ext.c:289` 等使用 Linux stat 时间字段，实测编译失败；PE 加载器将缺失的 `MAP_FIXED_NOREPLACE` 自定义为 Linux 数值，语法通过不保证 Darwin 上语义正确；默认 16 KiB 页需纳入提交粒度设计。
4. **游戏特有 ABI**：`src/linux/main.c:58` 的 guest varargs 不能直接拿给 ARM64 `vsnprintf`；Blowfish 对象私有状态、HD 体素代码、路径和文件资源亦需地址审计。
5. **其余正确性**：x87 的 double 模型不等于完整 80 位精度；计时、线程切换、SSE/MXCSR、SEH、非对齐 C 访问、Windows 路径、回调与存档布局仍需真实代码验证。

## 第一批实验结束时未达到的条件（历史）

未取得指定版本的真实游戏可执行文件和资源；未验证 lifted RA2/YR 函数；未验证 PE 数据加载、完整 HLE、画面、输入、音频、存档、战役、遭遇战、MOD、联机或性能。未生成可玩的 .app。

这些是取得上传文件前的限制记录。其中真实函数对照现已通过一个有限范围的实验，PE 图像在测试宿主中可以读取；完整 HLE、游戏启动、影音、存档和完整一局仍未验证。4 GiB 虚拟窗口在真实函数宿主中也已保留并按需提交，不代表完成通用 guest 内存管理。
