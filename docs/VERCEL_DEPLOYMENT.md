# Vercel 静态部署

准备命令（在工程根目录运行，下面的 OWNER/REPO 替换为用户选定的公开资源仓库）：

```sh
.venv/bin/python tools/prepare_github_resources.py
.venv/bin/python tools/prepare_vercel_web.py --resources-repository OWNER/REPO
```

生成目录：`.local/vercel-site/`。这是唯一应提交给 Vercel CLI 的目录，
不要把工程根目录作为上传目录。无需安装前端依赖或在 Vercel 编译游戏。

当前部署目录约 24.2 MB，包含页面、静态版本清单、JavaScript 加载器、
v0.1.5 的压缩完整程序和增量包。未压缩 Wasm 约 135 MB，保留在本机；
浏览器下载压缩程序后分块解压、校验并存入 IndexedDB。

## 配置

模板是 `deploy/vercel/vercel.json`，准备工具将其复制到部署目录。
使用静态站点（Framework: Other），无需 Build Command / Install Command，输出目录 `.`。

- 全站 COOP `same-origin`、COEP `require-corp`、CORP `same-origin`。
- 页面、脚本和版本清单每次访问重新验证；带内容散列的加载器和程序包使用一年 immutable 缓存。
- Vercel 部署目录不包含原版资源；资源分块单独上传到用户选定的 GitHub Releases。
- 部署没有日志服务，诊断记录留在页面和浏览器本地，不向原 Tailscale 地址回传。
- `setup.html` 兼容链接重定向到同一游戏页面的设置弹窗。

当前压缩包适合与网页同站点托管，因此不依赖 GitHub Releases 或跨域下载。
后续每个程序版本仍由版本号、目标 SHA-256 和逐块散列验证。

## 发布

已连接 Vercel 账号 tinypoint，并在个人工作区创建项目 `ra2-web`。
项目关联保存在 `.local/vercel-site/.vercel/project.json`，尚未上传或发布。
控制台：https://vercel.com/tinypoints-projects/ra2-web

也可使用 Vercel CLI 从生成目录部署：

```sh
cd .local/vercel-site
npx vercel login
npx vercel
```

先使用预览部署检查响应头和文件访问；正式发布使用 `npx vercel --prod`。
部署 URL 上仍需用户用 iPhone 实际验证游戏，准备阶段没有运行游戏测试。

后续生成工具会保留此目录下 `.vercel` 的项目关联，其余文件重新生成。
Vercel 项目若启用了部署保护，需要先通过账号验证，手机才能访问该部署。

## 手机迁移

使用固定的正式域名，避免每次预览 URL 更换导致缓存分离。
新域名无法读取 Tailscale 域名的 IndexedDB；GitHub Releases 模式首次打开会自动下载缺失资源。
也可以导入手机已有的 `resource-pack.ra2pack`，以避免重新下载已有资源。
程序包可自动下载，或在同一设置弹窗中手动导入。
之后普通刷新复用本地资源，页面更新不会清空资源缓存。

## 检查范围

准备工具检查当前发布程序和版本匹配、完整压缩程序解压后的 SHA-256、
更新包头和原资源包导入顺序，并限制部署目录小于 100 MiB。
准备结果记录在 `logs/web-vercel-preparation.json`。
实际 Vercel 响应头、iPhone 多线程运行和网络速度，需要部署后确认。

## GitHub Releases 自动资源下载

已准备 19 个资源文件，共 372,410,994 字节；不重复上传原包中已过时的 Wasm。
资源被拆成 37 个最多 16 MiB 的内容寻址文件，名称为 SHA-256.bin。
资源集合标签是 `resources-6b1eec50c3890081`；资源不变时标签和分块地址保持不变。
准备目录 `.local/github-resources/`，公开仓库为 `tinypoint/ra2-native`，同时维护 macOS 与 Web 源码；资源上传至其 Releases。

`prepare_github_resources.py` 从用户原包中提取数据，逐块及整文件核验散列；
`prepare_vercel_web.py --resources-repository OWNER/REPO` 生成相应资源清单和 Vercel external rewrite。
浏览器以同域 `/resources/SHA.bin` 请求，再由 Vercel 转发至公开 Releases，
从而避免浏览器直接跨域读取下载附件。该路径的资源流量仍会经过 Vercel，
不是绕过 Vercel 流量配额的直连方案。上游重定向及真实响应头还需部署后验证。

下载后沿用原有 IndexedDB 文件散列+块编号缓存；部分下载中断后只补缺的块。
新下载的每块在写缓存前核验 SHA-256；界面会显示当前下载文件、进度和速度。
已有本地资源包仍可导入，文件散列兼容。GitHub Releases 模式进入页面默认开始
下载与启动，不要求用户先手动下载并上传资源。

公开仓库普通下载无需浏览器持有 GitHub 令牌。私有仓库需要不同的服务器鉴权方案，
不能直接将令牌写入网页或版本清单。用户已确认公开发布；资源与代码共用同一仓库，分块仅上传至 Releases。
省略 `--resources-repository` 时仍可生成原本地导入模式。
