# Provenance

These files are an adapted subset of `sp00nznet/pcrecomp`, commit
`bd26806fbd4714d670d2dee75973c5eaff64674c`, `runtime/win32hle/`.
The original MIT LICENSE is retained here. No game code is included.

Local changes separate PE32 addresses from host pointers, allocate guest
heaps/stacks/TIBs in a 4 GiB arena, preserve additional machine state across
callbacks/threads, and map PE data through that arena. Host objects in the
original handle table remain ordinary 64-bit pointers.

This is a partial runtime port. The remaining upstream HLE source files must
not be linked without auditing and adapting their direct guest-pointer casts.
The initial VM backend uses host-page protection granularity; finer protection
or decommit requests return failure rather than claiming exact Windows semantics.

The ARM64 port also includes USER32 callbacks, DirectDraw surface storage,
GDI DIB storage and macOS system font selection, Cocoa/Metal presentation
through SDL2, CoreAudio mixing, and FFmpeg-backed Bink objects. All guest-visible
buffers and nested callback pointers use guest VAs; host decoder objects remain
64-bit pointers in private state. FFmpeg and SDL binaries stay in .local.

Structured storage is also adapted from the pinned upstream storage.c. Guest COM objects and STATSTG buffers use guest addresses; private file state stays native. PE32 STATSTG CLSID offset is 48. Commits write a same-directory temporary file, fsync and rename; failures return errors. This is a CFB subset, not a claim of complete Windows storage compatibility.
