# ARM64 性能测量

2026-10-18。按用户确认的 3 → 2 → 1 顺序，先测性能，再验证跨进程存档/读档，最后完整对局。

## 条件与边界

同机顺序运行，RA2.INI 的 Skirmish.GameSpeed 固定为 2，测量后逐字节恢复原设置。逐接口日志关闭，500 ms 采样游戏帧，按实际出现的菜单推进。OS 文件缓存和出生随机数未固定；下表为各一次测量，不能外推所有地图与长局。

游戏逻辑帧数通过只读读取已核验输入的 `0xA40D2C` 取得。该地址的日志读取与递增指令证据见 `logs/game-frame-counter-evidence.json`。显示更新与逻辑帧分别统计。CPU 的 100% 表示一个逻辑核心；内存为整个进程峰值 RSS。

| 构建 | 进入战场 | 逻辑帧/秒中位数 | 显示更新/秒中位数 | 战场 CPU 中位数 | 峰值 RSS |
| --- | --- | --- | --- | --- | --- |
| -O0，对照 | 45.26 秒 | 31.17 | 31.16 | 42.95% | 260.5 MiB |
| -O2 | 41.78 秒 | 31.25 | 31.25 | 36.20% | 234.6 MiB |
| -O2，实验性空闲等待 | 41.29 秒 | 31.22 | 31.19 | 38.08% | 见原始 JSON |

编译优化没有明显缩短菜单动画与初始化等待。采用 -O2、关闭逐接口日志及批量截图写入；实验性消息循环等待保持关闭，它在固定速度下未体现收益，在最高速下会降低逻辑吞吐。

最高速 GameSpeed=0 的逻辑更新率远高于显示帧率；满一个核心与正常固定速度的 CPU 数值不能混为一项对比。`release-unpaced-1` 的观察末段与另一测试窗口重叠，已标记无效，不纳入正式对比。

## 复现

```sh
.venv/bin/python tools/build_native_boot.py --profile debug
.venv/bin/python tools/build_native_boot.py --profile release
.venv/bin/python tools/benchmark_native_game.py --profile debug --label debug-fixed-new --game-speed 2 --battle-seconds 15
.venv/bin/python tools/benchmark_native_game.py --profile release --label release-fixed-new --game-speed 2 --battle-seconds 15
```

基准使用先前已目视确认的本机游戏帧作界面识别参考，保留在 `.local/native-boot/`。每次测试按序运行；测试程序对新运行加互斥锁，退出时恢复原 RA2.INI。原始结果与样本见 `logs/performance-*.json`，汇总为 `logs/performance-comparison.json`。所有生成游戏代码、二进制、资产和画面均保留在忽略的本地目录。
