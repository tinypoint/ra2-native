# Web 0.1.9: resolution confirmation

Reproduced with the 0.1.8 runtime and a touch event sequence: main menu → Options → resolution → third item (1024×768×16). Canvas remains 640×480 and FPS continues near 31. The options page no longer reacts.

Read-only inspection of the live HWND tree found a second visible dialog at [95,76,451,328], children 1473 (GUI:Ok), 1738 (GUI:Cancel), and static 1499 (GUI:ConfirmModeChange). Capture was zero and browser pointer state was released. The dialog was logically active but absent from the pixels. Clicking its actual OK bounds caused SetDisplayMode(1024x768x16) and primary surface recreation. This establishes a hidden confirmation modal, rather than a dead browser or stale touch capture.

The narrow, verified defect is that the original custom confirmation dialog's pixels are not presented by the Web path, although its controls and message loop are alive. Completing pending parent paints before notification did not resolve it and that experimental change was reverted.

The Web adapter exposes only a visible dialog containing static ID 1499 with text GUI:ConfirmModeChange and both expected buttons (1473/1738). The frontend displays an explicit confirmation dialog. Its response is queued to the game thread, revalidates the dialog creation sequence (HWND slots are reused between initial approval and keep-mode confirmation), and sends the original WM_COMMAND/BN_CLICKED to the real dialog. The game's own callback decides acceptance or cancellation; no configuration or game state is bypassed. Ordinary menu input remains unchanged. Native USER32 is untouched.

A separate robustness fix decouples Web input pumping from primary-surface availability and fetches the current surface after input processing. Input can change the display mode and release/recreate the old primary, so pre-input pixel pointers must not be retained.

The page displays application v0.1.9 separately from original RA2's built-in game version. FPS has no border/background box. Phone Safari verification remains separate from desktop touch-event reproduction.

Verified against the final 0.1.9 Wasm bb63de2ddf40b54a38c4cb1faf776d642a43bbf5dc64d41967c18f28ec9d998b using Chrome touch events: initial confirmation appears, Cancel dismisses it, another selection can be made, first OK switches to 1024×768, the second confirmation accepts independently, and the dialog closes with the resolution retained. Clicking Main Menu after both confirmations returns to the working main menu. Final snapshot: FPS 28–31, canvas 1024×768, confirmation closed, FPS border 0px. Safari on the user's phone still needs confirmation. Evidence is in ignored logs/web-resolution-v019-result.json and local screenshots.

## 0.1.10: original popup rendering and menu viewport

A focused message trace established the missing ordering detail: the native mode dialog 10220 and its children 10230–10250 receive WM_PAINT, then the underlying Options dialog 10020 receives another WM_PAINT. The popup's cached BSurface contains the original background art; the shared display surface ends up containing only the Options page. Flushing paints before selection notification cannot fix a subsequent repaint.

The Web USER32 adapter now preserves the pixels occupied by a visible upper dialog while a lower dialog paints into their shared DirectDraw buffers. A pixel trace confirmed that the lower paint can run synchronously inside the upper dialog paint callback after its controls have drawn; re-invalidating the popup either loops or still permits that nested overwrite. Pixel protection covers both the primary and the original menu render surface, validates surface identity before restoring, and frees its temporary copies after the callback. Pointer hit-testing also follows the top dialog instead of allowing a deeper control behind it to win. The correction uses live window geometry and creation order, not resolution-specific control IDs. The HTML confirmation, special reply export, and resolution state bridge are removed. Both approval stages remain in the original game.

The front-end art is centered at up to 800×600 by original function 006F3930 in larger display modes. The Web presenter uses that menu content rectangle rather than presenting its extra internal black padding. Input events add the same viewport origin before entering USER32. Scenario guards exclude the battle view and its dialogs from this menu presentation adjustment. Browser contain scaling continues to preserve aspect ratio; screen/game aspect-ratio differences can still create exterior letterboxing. No native macOS source is changed.

Verified with Chrome touch events: the original dialog is visually present with its background, message, and both buttons; Cancel works; both approval stages work; the actual display remains 1024×768 while the menu canvas presents its 800×600 content; Main Menu responds after the change. The final Safari-optimized Wasm a2c8f0f7c7ffd8fd1ec611962cb0472b1354f63dff5fe280a858677072f336fe passed the same focused Chrome touch flow at FPS 31 after returning to the menu, and WebAssembly.validate returned true. Physical iPhone playtesting remains with the user.

## 0.1.11: map-list scrollbar placement

The original game creates the map ListBox and its ScrollBar as separate sibling windows. Its dialog layout enumerator moves both by the resolution centering offset. The Web HLE also emitted WM_SIZE when MoveWindow only changed the list position. The game's list resize callback moved its scrollbar early, then the layout enumerator applied the offset again. At 1024×768 the list was [444,270,177,264] but the bar was [813,414,20,264], an extra [192,144].

The Web-only patch suppresses WM_SIZE for ListBox moves with unchanged dimensions. Real list size changes still notify the original procedure, and WM_MOVE remains unchanged. No scrollbar coordinates or game settings are hardcoded. Native macOS HLE is unchanged.

Focused Chrome touch checks against the final optimized Wasm passed at 640×480, 800×600, and 1024×768. In all three, the scrollbar begins at list.x + list.width and list.y; its frame extends two pixels past the list, as at the original base resolution. Clicking the lower arrow changes the visible map rows. Original custom widget scrolling does not update the HLE fallback top field, so action verification compares the visible list rather than that field. Physical iPhone verification remains with the user. Local evidence: logs/web-scrollbar-{640,800,1024}.json and .local/scrollbar-*-after.png.
