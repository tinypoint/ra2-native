# Web 0.1.9: resolution confirmation

Reproduced with the 0.1.8 runtime and a touch event sequence: main menu → Options → resolution → third item (1024×768×16). Canvas remains 640×480 and FPS continues near 31. The options page no longer reacts.

Read-only inspection of the live HWND tree found a second visible dialog at [95,76,451,328], children 1473 (GUI:Ok), 1738 (GUI:Cancel), and static 1499 (GUI:ConfirmModeChange). Capture was zero and browser pointer state was released. The dialog was logically active but absent from the pixels. Clicking its actual OK bounds caused SetDisplayMode(1024x768x16) and primary surface recreation. This establishes a hidden confirmation modal, rather than a dead browser or stale touch capture.

The narrow, verified defect is that the original custom confirmation dialog's pixels are not presented by the Web path, although its controls and message loop are alive. Completing pending parent paints before notification did not resolve it and that experimental change was reverted.

The Web adapter exposes only a visible dialog containing static ID 1499 with text GUI:ConfirmModeChange and both expected buttons (1473/1738). The frontend displays an explicit confirmation dialog. Its response is queued to the game thread, revalidates the dialog creation sequence (HWND slots are reused between initial approval and keep-mode confirmation), and sends the original WM_COMMAND/BN_CLICKED to the real dialog. The game's own callback decides acceptance or cancellation; no configuration or game state is bypassed. Ordinary menu input remains unchanged. Native USER32 is untouched.

A separate robustness fix decouples Web input pumping from primary-surface availability and fetches the current surface after input processing. Input can change the display mode and release/recreate the old primary, so pre-input pixel pointers must not be retained.

The page displays application v0.1.9 separately from original RA2's built-in game version. FPS has no border/background box. Phone Safari verification remains separate from desktop touch-event reproduction.

Verified against the final 0.1.9 Wasm bb63de2ddf40b54a38c4cb1faf776d642a43bbf5dc64d41967c18f28ec9d998b using Chrome touch events: initial confirmation appears, Cancel dismisses it, another selection can be made, first OK switches to 1024×768, the second confirmation accepts independently, and the dialog closes with the resolution retained. Clicking Main Menu after both confirmations returns to the working main menu. Final snapshot: FPS 28–31, canvas 1024×768, confirmation closed, FPS border 0px. Safari on the user's phone still needs confirmation. Evidence is in ignored logs/web-resolution-v019-result.json and local screenshots.
