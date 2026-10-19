"""Apply browser-only control adaptations to the native USER32 source copy."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def patch(source: str) -> str:
    start = source.index('static uint32_t combobox_proc(')
    end = source.index('\nstatic uint32_t trackbar_proc(', start)
    source = source[:start] + (ROOT/'runtime/web/combobox.inc').read_text() + source[end:]
    # A dropdown extends past the combo's selection field and sits above siblings.
    start = source.index('    win_t *best = NULL;', source.index('uint32_t hle_window_at('))
    source = source[:start] + '''    for (int i = MAX_WIN - 1; i >= 0; i--) {
        win_t *x = &g_win[i];
        if (!x->used || x->kind != K_COMBOBOX || !x->dropped || !visible(x) || (x->style & WS_DISABLED)) continue;
        int ox, oy; origin(x, &ox, &oy);
        int bottom = x->h + x->nitems * (x->item_h > 0 ? x->item_h : 1);
        if (bottom > x->drop_h) bottom = x->drop_h;
        if (sx >= ox && sx < ox + x->w && sy >= oy && sy < oy + bottom) {
            if (cx) *cx = sx - ox;
            if (cy) *cy = sy - oy;
            return x->hwnd;
        }
    }
''' + source[start:]
    # An open combo captures its list, but a press on a different control
    # must close it and continue to the newly hit control in the same click.
    start = source.index('    g_cursor_x = sx, g_cursor_y = sy;', source.index('void hle_input_mouse('))
    source = source[:start] + '''    if (message == WM_LBUTTONDOWN) {
        win_t *captured = W(g_capture);
        if (captured && captured->kind == K_COMBOBOX && captured->dropped) {
            int ox, oy; origin(captured, &ox, &oy);
            int bottom = captured->h + captured->nitems * (captured->item_h > 0 ? captured->item_h : 17);
            if (bottom > captured->drop_h) bottom = captured->drop_h;
            if (sx < ox || sx >= ox + captured->w || sy < oy || sy >= oy + bottom) {
                uint32_t h = captured->hwnd;
                hle_send(h, 0x014Fu, 0, 0);
                if (g_capture == h) g_capture = 0;
            }
        }
    }
''' + source[start:]
    # Layout passes resize the visible field to 21px. Do not overwrite the
    # independent dropdown height with that single-line size.
    old = 'if (do_size && x->kind == K_COMBOBOX && (x->style & 3u) != 1u) x->drop_h = ph, ph = x->h;'
    new = 'if (do_size && x->kind == K_COMBOBOX && (x->style & 3u) != 1u) { if (ph > x->h) x->drop_h = ph; ph = x->h; }'
    assert old in source
    source = source.replace(old, new)
    # Destroying/hiding a custom popup exposes its parent again. Windows
    # generates paint for that region; retaining the last pixels is incorrect.
    start = source.index('    item_free(x);\n    x->used = 0;', source.index('static void destroy('))
    source = source[:start] + source[start:].replace('    item_free(x);\n    x->used = 0;', '''    uint32_t exposed = x->parent ? x->parent : x->owner;
    int repaint = (x->style & WS_VISIBLE) != 0;
    item_free(x);
    x->used = 0;
    if (repaint) for (win_t *p = W(exposed); p; p = W(p->parent))
        if (!p->destroying) invalidate(p, 1);''', 1)
    old = 'if ((x = W(A32(0))) && show) invalidate(x, 1);'
    new = '''if ((x = W(A32(0)))) {
            if (show) invalidate(x, 1);
            else for (win_t *p = W(x->parent ? x->parent : x->owner); p; p = W(p->parent))
                if (!p->destroying) invalidate(p, 1);
        }'''
    assert old in source
    source = source.replace(old, new)
    old = 'if (fl & 0x80u) x->style &= ~WS_VISIBLE;'
    new = '''if (fl & 0x80u) {
            x->style &= ~WS_VISIBLE;
            for (win_t *p = W(x->parent ? x->parent : x->owner); p; p = W(p->parent))
                if (!p->destroying) invalidate(p, 1);
        }'''
    assert old in source
    source = source.replace(old, new)
    # Acknowledge after the guest window procedure returns, not when a
    # message is merely queued/peeked. Only browser builds get this counter.
    needle = '    if (m == WM_PAINT && (x = W(h))'
    assert source.count(needle) == 1
    source = source.replace(needle, '    if (m == WM_LBUTTONDOWN || m == WM_LBUTTONUP || m == WM_RBUTTONDOWN || m == WM_RBUTTONUP) hle_web_mouse_completed++;\n' + needle)
    source = 'unsigned hle_web_mouse_completed;\n' + source
    return source
