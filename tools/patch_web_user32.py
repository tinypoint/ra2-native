"""Apply browser-only control adaptations to the native USER32 source copy."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def patch(source: str) -> str:
    # Guest windows share DirectDraw pixels. Preserve the visible upper window
    # while an overlapping lower window repaints, including synchronous paints
    # issued from inside the upper window's own paint callback.
    needle = 'static uint32_t call_proc(uint32_t proc, uint32_t h, uint32_t m, uint32_t w, uint32_t l) {'
    assert source.count(needle) == 1
    source = source.replace(needle, '''static int visible(win_t *);
static void origin(win_t *, int *, int *);
extern void *ra2_web_save_pixels(int,int,int,int);
extern void ra2_web_restore_pixels(void *);
typedef struct web_clip { void *pixels; struct web_clip *next; } web_clip;
static int web_clipping;
static web_clip *web_clip_above(uint32_t h) {
    win_t *painted=W(h), *layer=painted;
    if (!painted || !visible(painted)) return NULL;
    while (layer && layer->kind!=K_DIALOG) layer=W(layer->parent);
    if (!layer) return NULL;
    int px,py; origin(painted,&px,&py);
    web_clip *clips=NULL;
    for(int i=0;i<MAX_WIN;i++) {
        win_t *above=&g_win[i];
        if(!above->used || above->destroying || above->kind!=K_DIALOG ||
           above->parent!=layer->parent || above->seq<=layer->seq || !visible(above)) continue;
        int ax,ay; origin(above,&ax,&ay);
        int l=px>ax?px:ax,t=py>ay?py:ay;
        int r=px+painted->w<ax+above->w?px+painted->w:ax+above->w;
        int b=py+painted->h<ay+above->h?py+painted->h:ay+above->h;
        if(r<=l || b<=t)continue;
        void *pixels=ra2_web_save_pixels(ax,ay,ax+above->w,ay+above->h);
        if(!pixels)continue;
        web_clip *item=malloc(sizeof *item);
        if(!item){ra2_web_restore_pixels(pixels);continue;}
        item->pixels=pixels;item->next=clips;clips=item;
    }
    return clips;
}
''' + needle)
    needle = '    uint32_t r = hle_call_guest(proc, 4, a);'
    assert source.count(needle) == 1
    source = source.replace(needle, '''    web_clip *clips=NULL;int was_clipping=web_clipping;
    if(m==WM_PAINT && !web_clipping) {
        clips=web_clip_above(h);
        if(clips)web_clipping=1;
    }
''' + needle + '''
    while(clips){web_clip *next=clips->next;ra2_web_restore_pixels(clips->pixels);free(clips);clips=next;}
    web_clipping=was_clipping;''')
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
    # A visible popup covers lower controls even if those controls have a
    # deeper parent chain. Pointer targeting must follow the displayed layer.
    needle = '    win_t *best = NULL;'
    start = source.index(needle, source.index('uint32_t hle_window_at('))
    source = source[:start] + '''    win_t *cover = NULL;
    for (int i=0;i<MAX_WIN;i++) {
        win_t *x=&g_win[i];int ox,oy;
        if(!x->used||x->destroying||x->kind!=K_DIALOG||!visible(x))continue;
        origin(x,&ox,&oy);
        if(sx>=ox&&sy>=oy&&sx<ox+x->w&&sy<oy+x->h&&(!cover||x->seq>cover->seq))cover=x;
    }
''' + source[start:]
    needle = 'if (!x->used || !visible(x) || (x->style & WS_DISABLED) || x->kind == K_STATIC) continue;'
    assert source.count(needle) == 1
    source = source.replace(needle, needle + '\n        if (cover && !is_descendant(x->hwnd,cover->hwnd)) continue;')
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
    # Moving a list without resizing must not send WM_SIZE. The game's list
    # resize handler repositions its separate sibling scrollbar. A fabricated
    # resize moves that scrollbar before the dialog's layout enumerator reaches
    # it, so the same centering offset is applied twice at larger resolutions.
    needle = '    if (do_move) x->x = px, x->y = py;'
    assert source.count(needle) == 1
    source = source.replace(needle, '''    int web_notify_size = do_size && (x->kind != K_LISTBOX || pw != x->w || ph != x->h);
''' + needle)
    needle = '    if (do_size) hle_send(h, WM_SIZE,'
    assert source.count(needle) == 1
    source = source.replace(needle, '    if (web_notify_size) hle_send(h, WM_SIZE,')
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
    source += """
int hle_web_dialog_open(void) {
 for(int i=0;i<MAX_WIN;i++){win_t *x=&g_win[i];
  if(x->used&&!x->destroying&&x->w>0&&x->h>0&&(x->kind==K_DIALOG||x->dlgproc)&&visible(x))return 1;
 }return 0;
}
"""
    return source
