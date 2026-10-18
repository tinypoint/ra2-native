# 真实 RA2 函数 ARM64 PoC

2026-10-18，Asia/Shanghai。**10 个实际游戏函数已转换并编译为 ARM64；55 个受控初态 × global/local register 两种模式，110/110 一致。** 这是隔离函数验证，不是完整游戏启动。

## 上传服务

用户请求关闭后，向本次上传服务 PID 11643 发送 SIGTERM，删除运行状态文件，并确认 `127.0.0.1:8765` 返回连接拒绝。接收的游戏文件保留在 `incoming/`，不纳入 Git。未声称已关闭用户手机上的浏览器标签。

## 输入与提取

上传文件 `红警1.06原版.exe`，139730908 字节；SHA-256：

`41bbcc83e4357ed6eecad7e5635738447ebf0117034e4179dfb93208be9206e5`

`file`、7-Zip 均识别为 NSIS 自解压安装包。仅静态解包，没有执行安装器、启动器、游戏或升级器。包中第三方启动/升级程序未提取到实验游戏目录。

提取工具来自 [7-Zip 官方下载页](https://www.7-zip.org/download.html) 指向的 [26.04 macOS 发布附件](https://github.com/ip7z/7zip/releases/download/26.04/7z2604-mac.tar.xz)，保存于 `.local/7zip/`。下载归档 SHA-256 为 `bee04358cbcbc7106273cee0e8d72916db2696c48067a3538c34d8cd6fd16578`。此散列用于复现本次下载，不声称是作者独立签名验证。

```sh
mkdir -p .local/7zip game/ra2-upload-41bbcc83
curl -fL https://github.com/ip7z/7zip/releases/download/26.04/7z2604-mac.tar.xz \
  -o .local/7zip/7z2604-mac.tar.xz
tar -xJf .local/7zip/7z2604-mac.tar.xz -C .local/7zip
.local/7zip/7zz l -slt 'incoming/红警1.06原版.exe'
.local/7zip/7zz x 'incoming/红警1.06原版.exe' -ogame/ra2-upload-41bbcc83 -y \
  game.exe Game.dat Ra2.exe Binkw32.dll Blowfish.dll '*.mix' '*.mmx' '*.ini'
```

本次选择提取 21 个文件，共 372824718 字节。完整清单、尺寸、SHA-256、PE 信息和资源版本字符串见 `logs/game-input-inventory.json`。未提取的内容仍完整保留在上传包里；没有擅自修复或覆盖输入。

## 文件核验与限制

- `game.exe`：4485392 字节，SHA-256 `fe67fdac5073530a79baec14c4e072b5e7e4c0c462cee9659870c5330e9e6e3e`。
- PE32 i386，ImageBase `0x00400000`，入口 `0x00785AA0`；编译时间戳 `0x3B1EBBED` 与上游 `run_lift.py` RA2 目标检查值一致。
- 从 PE 资源读到 FileVersion/ProductVersion 为 `1.08`，安装包名为 1.06；不能仅凭这些字符串判定游戏补丁版本、官方来源或文件未修改。
- 本文件尺寸与上游记录的 Steam 文件尺寸不同。没有官方文件可作全字节比较，因此不声称是 Steam/EA 字节相同版本，也未直接套用上游所有固定地址补丁。
- RTTI 恢复 944 个类、1194 个虚表、6324 个虚方法。被测函数地址分别用该输入的真实虚表槽确认，而不是只相信其他版本的地址表。
- `ra2.mix` 约 282 MB、`language.mix` 约 53 MB，另有地图 MIX、Blowfish.dll 与 Binkw32.dll；未对 MIX 内所有内容完成解密或完整性检查。
- `Theme.mix`、`movies01.mix`、`movies02.mix` 均仅 5 字节，明显不能提供完整音乐/过场内容。不能用此包验收完整影音与战役体验。
- 来源为用户上传的第三方重打包文件，分发来源和授权未核实。游戏文件、生成代码、ARM64 游戏函数二进制均只留在忽略目录，没有对外发布。

## 实际被测代码

| 入口 | 通过该输入 RTTI 确认的类 | 验证内容 |
| --- | --- | --- |
| `0x005D4E40` | UnitClass | 三个坐标字段复制、thiscall 与 ret 4 |
| `0x0041B320` | UnitClass | 有符号坐标向网格坐标换算，含负数与边界 |
| `0x00453C70` | BuildingClass | 坐标偏移、输出写回、保存寄存器 |
| `0x004CDA80` | FootClass | 多个状态字段重置 |
| `0x005950E0` | TechnoClass | 状态字段与 -1 比较 |
| `0x006C16D0` | TechnoClass | 实际虚表间接调用，再读取类型对象字段 |
| `0x006C12C0` | UnitClass | 上一调用链中的真实虚表尾调用 thunk |
| `0x00705020` | UnitClass | 上一调用链中的真实类型指针读取 |
| `0x0058DEB0` | VectorClass@N | 从 double 数组读取并通过 x87 返回 |
| `0x006D3EA0` | TechnoClass | 从 PE 原始数据段读取 double 常量 |

55 个受控初态覆盖 0、1、255、256、-1、-256、INT_MAX、INT_MIN 和六组 double 值。函数描述来自可观察的代码操作，不声称恢复了原始源代码方法名。

## 运行和比较方法

```sh
.venv/bin/python poc/run_real_game_checks.py --exe game/ra2-upload-41bbcc83/game.exe
```

脚本验证输入 SHA-256，调用固定提交的上游 RTTI 工具，以该游戏文件中的真实指令生成函数 C，再用 Apple Clang 编译为 ARM64。本轮不用全游戏 lift、图形 API、Wine、Rosetta 或 Windows DLL 执行。

ARM64 宿主保留 4 GiB guest 虚拟空间，使用 16 KiB 对齐 mprotect 按需提交 PE 图像和测试内存；guest 0 保持不可访问。宿主 arena 位于 4 GiB 以上，所有 guest VA 仍保持 32 位。图像只允许读写，不允许作为宿主代码执行。此实现只是测试宿主，不是完整 PE 加载器或 Win32 HLE。

Unicorn 直接执行同一文件内的 x86 指令，比较：8 个通用寄存器、定义的算术标志和 DF、64 KiB 测试内存、PE 图像未被意外修改、x87 栈深度与返回 double 的位模式、ESP 返回平衡。

明确的比较边界：

- XOR/TEST 后的 AF，以及多位 SAR 后的 AF/OF 按 x86 未定义标志排除；逐用例记录在 JSON。
- 只有实际虚表调用测试排除 `ESP_initial - 4` 处已返回调用的四字节返回地址：原始 x86 保存真实代码返回地址，提升模型保存占位值。该差异不隐藏；其余栈内存仍比较。
- 浮点函数只验证加载和返回，没有验证复杂 x87 运算、80 位中间精度、异常或全部舍入模式。
- 没有覆盖 Win32 导入、原版游戏主循环、系统资源加载、线程、存档或完整局内行为。参考仅为 Unicorn，尚未做 x86 硬件独立对照。

## 结果与下一步

`logs/real-game-results.json` 保存函数来源、长度与函数体散列、每个测试结果、寄存器、浮点返回值、比较排除项。`logs/real_game_*-compile.log` 保存命令，`*-file.log` 证明二进制为 `Mach-O 64-bit executable arm64`。

**110/110 通过，退出码 0。** 原先“无游戏文件所以不能验证真实函数”的阻塞已解除；原先上游通用测试的 NaN 差异仍存在，本次通过不将其抹去。

下一关是将这一地址模型落到 pcrecomp 的真实 HLE：PE 数据映射、堆、线程栈/TIB、Win32 指针参数与返回值，再推进无界面初始化。当前只足以支持继续运行时移植，不足以宣布完整游戏已移植。
