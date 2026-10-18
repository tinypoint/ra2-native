# Provenance

`blowfish.c` is adapted from `sp00nznet/redalert2-recomp`, commit
`ffc982534951acec02211cc79f9ed1a734bddc16`, `src/linux/blowfish.c`.
Its upstream license is preserved as `LICENSE.upstream`, including the
previously noted unrelated game-name wording in its scope appendix.

The adaptation translates guest object addresses explicitly and allocates
object state inside the guest arena. Initial cipher tables are read locally
from the user-provided Blowfish.dll; no DLL code or extracted table is embedded
or distributed here.
