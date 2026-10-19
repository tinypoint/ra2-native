# 独立浏览器移植

用户选择直接在手机浏览器运行游戏，不采用远程串流；用户已明确禁止继续使用子代理。

当前构建路径与 macOS 原生构建分开：

- Emscripten SDK 6.0.12，固定 SDK tag 35ff8a6d150541276abbc6bae512ca90bcfbe220，工具链仅在 `.local/emsdk`。
- 原有 23116 个真实游戏函数复用，构建产物 `.local/web-build/ra2-web.js/.wasm` 不纳入 Git，不作为 MIT 游戏源码分发。
- 有界 wasm32 guest arena，默认 512 MiB，保护权限仅为软件元数据，不假装有宿主 mprotect 隔离。
- 实际 wasm32/Node 内存检查 38/38；不代表完整游戏或手机兼容已经验证。
- FFmpeg 7.1.5 单独编译为 pthread Wasm，仅启用 Bink 所需组件；native 输出不变。
- SDL2 2.32.10、SDL2_ttf 2.20.2 使用 Emscripten ports；它们与原生 framework 是独立构建。
- Win32 HLE 的 Darwin 文件时间和 sockaddr 差异在忽略的 web 构建副本中适配。
- 游戏在 pthread worker 执行，主线程保留网页响应。此版本需要安全上下文和 COOP/COEP；普通内网 HTTP 可以缓存，但不能因此声称能运行 pthread Wasm。

## 构建

```sh
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python tools/check_web_memory.py --emcc .local/emsdk/upstream/emscripten/emcc
.venv/bin/python tools/build_web_movies.py
.venv/bin/python tools/build_web_game.py
.venv/bin/python tools/serve_web_preview.py
```

server 只提供固定前端文件、构建产物和白名单游戏资源。URL 的访问 token 在 `.local/web-preview/access-token`，不会枚举工程目录。只作用户的私人测试入口，不发布游戏数据。

## 缓存

页面与资源版本分离。小清单更新；游戏文件用 SHA256 作为 IndexedDB key，普通刷新命中本地后不请求对应资源。构建文件使用含散列的 URL 与 immutable cache；页面/清单获取新版本。浏览器有清理与配额限制，不能保证无限期保存。

已在真实 Chrome 的 HTTP 内网地址验证：Blowfish.dll 首次 225331 字节，刷新后同一资源网络下载为 0，资源请求合计一次。原始结果：`logs/web-cache-browser-results.json`。此结果不是手机 Safari 验收。

首个对外页面误做成了进度与缓存说明页，未满足用户要看游戏的要求；该页已替换为实际游戏加载入口，未将其描述为游戏成功。

## iPhone initialization interruption — 2026-10-18

User reports iPhone reload at “下载与载入完成，原游戏正在初始化…”, with resource cache retained. Suspected memory pressure; no iOS crash report, so cause is not proven. Web initial linear memory lowered from 768 MiB to 64 MiB with growth enabled; guest arena lowered from 512 MiB to 384 MiB, allocated without eager clearing and zeroed page-by-page on first commit. Browser MEMFS takes ownership of file buffers. Native ARM64 implementation is unchanged.

Native and wasm32 memory contract checks: 38/38 each. Desktop Chrome verified old imported resource pack → 4,260,731-byte runtime update → actual RA2 menu, with no game asset or full Wasm download. Evidence: `logs/web-mobile-memory-browser-results.json`, `.local/web-browser-tests/mobile-memory-game.png`. iPhone success remains unverified.

`tools/build_web_runtime_update.py` creates a verified Git binary delta from the original frozen Wasm; `web/runtime-update.js` applies it to existing IndexedDB chunks, validates each target chunk and writes the new program cache. The original full resource pack remains importable. Update can be fetched automatically or imported from `runtime-update.ra2update` downloaded over the faster LAN path. Local update files, snapshots, tokens and game data stay under ignored `.local`.

## iPhone Wasm call stack overflow — 2026-10-18

Actual iPhone report (private `.local/web-preview/browser-errors.jsonl`) now preserves the original error: `RangeError: Maximum call stack size exceeded`. The trace repeats lifted `0x005F2B50` (Wasm function 13621, 10,301 locals) and `0x005135F0` (function 8965, 7,780 locals) through window-procedure callbacks. Binaryen coalescing reduces them to 214 and 666 locals; whole-module maximum drops from 29,590 to 4,809, and program size from 170,956,596 to 135,476,306 bytes. This is a concrete stack-pressure reduction; the iPhone still needs to verify the new build.

Desktop Chrome passes original-pack import → compressed program update → real game menu, retaining all game resources. `logs/web-stack-browser-results.json` and `logs/web-stack-optimization-results.json` record the result. Constrained Chrome with a 256 KiB stack did not reproduce the original Safari failure, so it is not claimed as an iPhone regression test. Local Playwright WebKit could not complete launch; no WebKit test result is claimed.

The changed program compresses better as a full compressed program than a Git delta: `runtime-stack-update.ra2update` is 33,314,626 bytes (about 31.8 MiB). The importer decompresses and verifies 16 MiB chunks while writing IndexedDB, without materializing the entire decompressed module. The original 519 MB pack remains valid; no map/resource redownload is needed. Future browser builds run `tools/optimize_web_stack.py` with a cached Binaryen pass and deterministic linker input order. Worker errors are unwrapped and sent to the private host, with only bounded error/stage/log fields; no game data or credentials are uploaded.

## Program release numbering

The confirmed playable stack-optimized build is now `v0.1.0`. Its versioned download is `ra2-web-v0.1.0.ra2update`; this labels the existing program without changing its SHA-256, so previously installed copies require no download. The page shows the release number and whether the program is locally cached. Existing unversioned update files remain importable when their target hash matches.

Future packages require an explicit version: `python tools/build_web_runtime_update.py --version 0.1.1`. Filenames include that version; reusing a version for different program bytes is rejected. The source record is `web/runtime-release.json`; served version metadata is accepted only when its target matches the currently served Wasm.

## Automatic start and contained game viewport

Complete cached installs now start by default, without a prior preference flag; legacy `?import=1` links also start. Explicit maintenance mode is `?autostart=0`. A detected interrupted launch still requires a manual retry. The pending marker is cleared on the first real game frame so an intentional refresh does not suppress subsequent automatic starts.

The active game fills the available dynamic viewport, preserving compact controls and the program version. Canvas uses centered `object-fit: contain` in portrait, landscape and fullscreen; pointer coordinates account for letterboxing, ignore presses in black bars, and clamp captured releases outside the game to avoid stuck buttons. No program/resource hashes change. Desktop Chrome verification: first automatic start with no preference, immediate automatic reload, zero game resource downloads, 390×844 and 844×390 layouts fully inside the viewport and correct pointer mapping. Evidence: `logs/web-auto-contain-results.json`.

## Mobile gesture experiment removed

At the user's request, the custom gesture classifier, long-press selection, two-finger cancellation, camera key emulation and read-only placement/context reader were removed. The browser again forwards basic pointer movement/button events and physical keyboard input, without interpreting gestures. Full-page contain rendering, automatic launch, caching and page overscroll prevention remain. Native macOS code was not changed. Earlier gesture test logs describe the removed experiment, not the current implementation.

Browser v0.1.1 repairs standard combo dropdown pointer selection, selection notifications and idempotent open/close transitions using `runtime/web/combobox.inc` in the browser's generated USER32 copy. Browser input processing leaves a guest frame between button/key transitions, so a deferred phone tap cannot collapse its down/up state or bypass capture established by the down message. The native USER32 and lifted sources remain unchanged.

The phone's reported free-for-all crash included the deeply reentered menu/scrollbar callback at guest VA `0x005F6690`. This callback still had 4,809 locals after coalescing. A browser-only source copy compiles that one function with `optnone,noinline`, moving its temporaries onto the linear C stack; the resulting callback has 4 Wasm locals. The rest of the game retains its optimization settings. v0.1.1 passes Wasm format validation and the verified update-package reconstruction; interactive phone confirmation remains with the user. Its update is 33,189,725 bytes; installed game/map data is reused.

Serving now reads `.local/web-published`, a snapshot of a complete release, rather than the mutable build directory. Compilation and optimization cannot expose partial or unoptimized programs. Release snapshots are kept under ignored `.local/web-releases/`.

The game now has one page. The small gear inside the game viewport opens a native dialog containing imports, installed program version, cache status, transfer progress, start/reload and diagnostics. Complete caches still launch automatically. Missing files or errors open the dialog; game input is released and keyboard events are withheld while it is open. Imports can update IndexedDB while an existing game runs; applying them requires an explicit reload that ends that match. `setup.html` is a compatibility redirect to the root with `#settings`; the separate setup document has been removed. This UI-only change reuses v0.1.1 and all resource hashes.

v0.1.2 defers combo selection until pointer release, closes before notifying game callbacks, invalidates containing dialogs to erase popup rows, releases an old combo's capture before routing a press to a different control, and keeps resized dropdowns tall enough for their options. Interactive phone verification is pending. The verified delta from v0.1.1 is 5,949 bytes. A standalone compressed fallback (23,704,326 bytes) supports browsers without that base. The app selects the offer using its cached base metadata; original resource-pack programs remain importable. Delta reconstruction retains only one old 16 MiB chunk at a time to limit iPhone memory use.

v0.1.3 follows real phone control reports: seven AI-slot combos were enabled with four choices, but all dropdown rectangles were only 21px tall while rows were 23px. The game uses its own `ComboDropWin` (observed separate capture HWND), so the earlier builtin dropdown-open helper did not run. Its lifted popup creator at 0x005F5A20 reads CB_GETDROPPEDCONTROLRECT and CB_GETITEMHEIGHT to size visible rows. Field layout had overwritten drop_h with field height. Browser move adaptation now preserves dropdown height for field-sized resizes, and CB_GETDROPPEDCONTROLRECT returns enough room for up to eight real options without relying on builtin popup activation. Delta from v0.1.2 is 4,773 bytes. Wasm, package reconstruction and live offer were validated; phone gameplay verification remains pending.

The preview and userspace Tailscale processes are managed by per-user launchd agents `local.ra2.web-preview` and `local.ra2.web-access`. Their plists are in ~/Library/LaunchAgents; KeepAlive restarts exited processes and RunAtLoad starts them at user login. Existing node identity, state directory, SOCKS port, Serve configuration and resource cache paths are preserved. Use `launchctl kickstart -k gui/$(id -u)/local.ra2.web-preview` for future server-code restarts; do not start another standalone server on port 8767. Static UI changes and published release symlink switches do not need a restart.

v0.1.4 follows phone reports where ComboDropWin disappeared from the HWND tree and capture became zero after selection, while the user still saw its list. Browser DestroyWindow, ShowWindow(SW_HIDE) and SetWindowPos(SWP_HIDEWINDOW) now invalidate the exposed parent hierarchy for repaint, instead of retaining popup pixels after logical removal. This is a window damage-handling fix, not a forced selection or fake popup state. The verified delta from v0.1.3 is 5,110 bytes. Interactive phone verification is pending; the separate resolution-control report remains unconfirmed. Read-only diagnostics now include clicked non-combo child controls so settings controls can be classified without modifying their enabled state.

## Mobile diagonal panning and corner controls — 2026-10-19

The user confirmed dropdowns now close correctly on the phone after the v0.1.4 repaint fix. The main-menu resolution dropdown remains unresolved.

The web shell now uses circular translucent controls: H lower left, cancel lower right, settings upper right, and FPS upper left. Controls use available letterboxing; centered contain scaling leaves room when necessary. There is no bottom toolbar.

The user reported diagonal two-finger drags stepping between axes. The previous gesture gate accumulated each axis independently, while the web input queue consumed only one arrow transition per presentation. v0.1.5 gates travel as one vector and submits diagonal directions together; the queue applies adjacent arrow transitions with the same press/release state in one tick. Opposing press/release transitions and mouse taps remain separated. Existing 24 px distance gate and 40 ms pulse / 120 ms interval remain. Native input code is untouched. Source-level vector checks and an isolated host C queue check passed; phone feel is intentionally left for the user to assess, with no interactive game test.

The user requested a virtual camera stick instead of two-finger camera dragging. Web shell `joystick-1` places a 104 px fixed stick in the lower left, H above it on the left, and cancel in the lower right. Stick travel has an 8 px dead zone, eight held arrow directions with angle hysteresis, and releases keys on pointer release/cancellation, capture loss, tab blur or opening settings. Canvas fingers remain ordinary click/box-selection input and may operate concurrently with the stick. Two-finger pan interpretation is removed. Contain fitting uses the actual visible controls' rectangles to avoid covering game pixels. This is a UI-only update using program v0.1.5 and existing resources; syntax and live static delivery checked, phone feel left for the user.

Phone feedback: joystick thumb did not recenter on release. `joystick-release-2` adds window-capture pointer release/cancel handling plus iOS touchend/touchcancel fallback tracking only the joystick finger, avoiding interruption when the other hand lifts. Visual recentering happens before key-release forwarding. Capture is explicitly released, with pagehide and mouse-buttons-zero cleanup. Static delivery and syntax checked; phone confirmation pending.
