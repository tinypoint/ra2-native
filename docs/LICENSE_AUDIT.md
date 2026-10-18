# 授权与来源：第一批记录

日期：2026-10-18。这里记录看到的文件与工程边界，不是对最终产品发布权的结论。尚未完成全仓逐文件及完整 Git 历史来源审查。

| 对象 | 本次证据 | 本项目处理 |
| --- | --- | --- |
| pcrecomp 自有工具与运行时 | 固定提交的 `LICENSE` 为 MIT；Scope 明确区分转换目标 | 原样下载到忽略的 vendor；未发布、未将其误标为本项目原创 |
| redalert2-recomp 自有代码 | `LICENSE:1` 起 MIT；`:25` 起范围说明 | 记录许可文本和来源，未改上游 |
| redalert2-recomp 许可证异常 | `LICENSE:27`、`:29` 写成 The Movies / Lionhead / Activision | 看起来存在模板遗留；不能自行代替维护者更正或认定全部来源已核清 |
| 游戏可执行文件、DLL、数据 | 未取得；上游明确要求自备副本 | 不纳入 Git，不下载来源未核实的整合包 |
| 从真实游戏生成的 C / ARM64 二进制 | 两个上游 LICENSE 均说明 MIT 不覆盖转换目标 | 不推导为 MIT；未来发布方案需单独核查，用户导入资产不自动解决游戏逻辑代码的分发问题 |
| 本轮原创合成 x86 fixture 和桥接宿主 | `poc/run_native_checks.py` 的 FIXTURES、`poc/bridge_host.c` | 没有从 RA2/YR 提取；明确标记为合成测试 |
| 上游差分用例与自动生成物 | 直接调用固定提交的 `tools/lift/difftest.py` | 保留上游来源；生成物不纳入 Git，不把 371 个用例称为本项目原创 |

## 当前研究依赖

固定版本见 `requirements.txt`；安装包元数据见 `logs/dependency-licenses.json`。

- Capstone 5.0.9：本地 wheel 的 `capstone-5.0.9.dist-info/LICENSE.TXT` 为三条款 BSD 文本。
- pefile 2024.8.26：本地 wheel 的 LICENSE 为 MIT。
- Unicorn 2.1.4：**wheel 的 License 字段写 BSD，但其描述写 GPLv2**；[对应标签的官方 COPYING](https://github.com/unicorn-engine/unicorn/blob/2.1.4/COPYING) 是 GPLv2。不能只相信包的摘要字段。当前仅作为研究脚本中的 x86 参考，不链接或打包进被测 ARM64 C 程序。
- CMake 4.4.4：wheel 有 Apache 2.0、BSD 3 及其内嵌组件许可文件；Ninja 1.13.2 的元数据为 Apache-2.0。这两者为本地构建工具，未打包到游戏。
- SDL2、SDL2_ttf、ffmpeg：本轮没有安装或打包，未来选定确切版本、构建选项与分发形式后再核查；不能仅按库名给最终发布结论。

## 游戏获取调查

本次网络检索确认 [Steam 官方商店页面](https://store.steampowered.com/app/2229850/) 和 [EA 官方合集页面](https://www.ea.com/games/command-and-conquer/command-and-conquer-the-ultimate-collection)。没有自动购买、登录或下载游戏。未找到并核实可供当前 PoC 使用的官方免费完整目标版本；此表述不声称互联网上不存在任何试玩包。

后续需要官方安装目录中的指定版本输入。若采用试玩版，必须另行确认其授权、PE 版本、函数地址及支持内容，不能当成 Steam/EA 版 `game.exe 1.006` / `gamemd.exe 1.001` 直接使用。

## 尚未完成

Chrono Divide 与所有衍生 Web 项目的许可证、来源及 Fork 关系未审计；没有复制其引擎。其他参考仓库也未完成授权审查。本地研究完成不等于已经能发布包含游戏逻辑的 .app。现阶段适合形成社区贡献的是地址模型实验、可复现测试、问题记录及后续独立的运行时改造。
