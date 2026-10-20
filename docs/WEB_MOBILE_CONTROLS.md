# Web mobile controls 0.1.8

Web-only implementation; the native macOS runtime is unchanged. The phone playtest is left to the user. Compilation, JavaScript syntax and release asset hashes are checked separately.

## Input and layout

Single tap produces left down/up; dragging produces left drag. Two simultaneous touches pan with arrow-key pairs, alongside the left joystick. Each camera source owns its held keys, so releasing one does not release the other. Two-finger panning starts before single-finger dragging; an already-started box selection must be released first. Production gadgets accept a 500 ms long press producing one right down/up without a left click.

Base H is above the lower-left joystick. Lower-right controls are D/S, G/T, then contextual cancel. The top-right operation manual lists implemented controls and explicitly marks teams, modifier gestures and chat as unavailable on mobile. Desktop pointer/keyboard input is preserved.

## Guest state and cancel evidence

`runtime/web/mobile.c` runs under the guest lock in the Web frame hook. Battle availability uses the original `0066A400` mouse-path guards and excludes visible USER32 dialogs. This does not gate basic menu pointer input.

Display object: `008324E0`. Selection count: `00A40C70`. Cancel mode priority follows `0049AF90`: placement at +11A0, mode flags +11AC..11AE, target sentinel +11B4, flags +11AF/+11B0, then selection. The queued cancel command revalidates its expected mode and invokes the original `0049AF90` right-up handler with ECX=Display. It takes no mouse coordinates. Its fallback calls `00482BC0`, preserving original Deselect callbacks and cleanup rather than directly clearing a count.

Production rectangles come from the active gadget linked list at `00A40EEC`, next pointer +4, SelectClass vtable `007AB37C`, rect +C/+10/+14/+18, strip owner +2C. Disabled is +1E (original input path `004CF50F` skips callbacks when nonzero); +1D is the sticky capture flag and must not be used as disabled.

Guest state is reported synchronously to the main thread at most every 100 ms, avoiding asynchronous references to stack JSON or unsynchronized reads of guest data. Cancel is reentrancy guarded. Existing bounded mouse acknowledgement logic remains unchanged.

## Remaining verification

Physical iPhone playtesting is still required: battle guard coverage, production long press, diagonal two-finger pan, deployment followed by cancel, menu sliders, and independent tap release. No browser gameplay pass was run for this release, per user request.

## Browser settings and saves

The `user-files.js` frontend adds a mutable overlay in the separate `ra2-web-user-files` IndexedDB database. After immutable resource loading and before callMain, it restores changed files and deletion tombstones. Successful writes, truncations, renames and deletes under /game are tracked. Open writable handles defer persistence; closing a dirty file schedules a transaction after 100 ms. Transactions contain fresh byte copies; failed transactions retain dirty paths for retry and show an on-screen warning. Read-only resource loads are not copied into the save database. Visibility/pagehide flushing is supplementary, not the primary save mechanism.

No automatic game-state save is implied: the user must use the game's save action. Browser termination before a completed IndexedDB transaction can still lose the newest change. Storage is scoped to the website and browser; clearing site data, private browsing teardown, or browser eviction can remove it. Existing lost saves cannot be recovered. The frontend update reuses the 0.1.8 runtime with no program download. The contract check in tests/web-user-files.cjs covers restoration, open-writer exclusion, rename/delete, cache separation and transaction failure retry; physical iPhone game save/load is not yet playtested.
