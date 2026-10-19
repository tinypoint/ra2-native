/* Browser target: complete the standard combo's pointer dropdown behavior.
 * This is inserted into the browser copy of USER32; native builds are unchanged. */
static void web_combo_drop(win_t *x, int open) {
    uint32_t h = x->hwnd, parent = x->parent;
    open = open != 0;
    if (x->dropped == open) return;
    x->dropped = open;
    if (open) {
        x->top = 0;
        x->tracking = 0;
        x->sel1 = -1;
        /* Some templates resize the field to one line after creation. Keep
         * enough height for real options rather than an empty dropdown. */
        int ih = x->item_h > 0 ? x->item_h : 17;
        x->item_h = ih;
        int rows = x->nitems < 8 ? x->nitems : 8;
        if (x->drop_h < x->h + rows * ih) x->drop_h = x->h + rows * ih;
        g_capture = h;
    } else if (g_capture == h) g_capture = 0;
    invalidate(x, 0);
    if (!open) {
        x->tracking = 0;
        x->sel1 = -1;
        /* Repaint the whole containing dialog, including the pixels covered
         * by the popup, instead of leaving old list rows on the surface. */
        for (win_t *p = W(parent); p; p = W(p->parent)) invalidate(p, 1);
    }
    notify(x, open ? 7u : 8u);  /* CBN_DROPDOWN / CBN_CLOSEUP, only on a transition */
}
static void web_combo_select(win_t *x, int index, int close) {
    uint32_t h = x->hwnd;
    if (index < 0 || index >= x->nitems) return;
    int changed = x->cursel != index;
    x->cursel = index;
    snprintf(x->text, sizeof x->text, "%s", x->items[index].text ? x->items[index].text : "");
    invalidate(x, 0);
    if (close) { web_combo_drop(x, 0); if (!(x = W(h))) return; }
    if (changed) notify(x, 1u);  /* CBN_SELCHANGE */
    if (!(x = W(h))) return;
    if (close) {
        notify(x, 9u);          /* CBN_SELENDOK */
        if ((x = W(h))) web_combo_drop(x, 0);
    }
}
static uint32_t combobox_proc(win_t *x, uint32_t m, uint32_t w, uint32_t l) {
    int handled;
    uint32_t r = list_msg(x, m, w, l, &handled);
    if (handled) {
        if (m == 0x014Eu && x->cursel >= 0)
            snprintf(x->text, sizeof x->text, "%s", x->items[x->cursel].text ? x->items[x->cursel].text : "");
        return r;
    }
    switch (m) {
    case 0x014Fu: web_combo_drop(x, w != 0); return 1;
    case 0x0157u: return (uint32_t)x->dropped;
    case 0x0152u: {
        int ox, oy; origin(x, &ox, &oy);
        /* The game builds its own ComboDropWin from this rectangle without
         * entering the builtin dropdown handler. A field-height rectangle
         * produces a zero-row custom popup. */
        int rows = x->nitems < 8 ? x->nitems : 8;
        int ih = x->item_h > 0 ? x->item_h : 17;
        int minimum = x->h + rows * ih + 2;
        if (x->drop_h < minimum) x->drop_h = minimum;
        put_rect(l, ox, oy, ox + x->w, oy + x->drop_h); return 1;
    }
    case 0x0141u: return 1;
    case 0x0155u: case 0x0156u: return 0;
    case WM_LBUTTONDOWN: {
        uint32_t h = x->hwnd;
        int px = (int16_t)l, py = (int16_t)(l >> 16);
        set_focus(h);
        if (!(x = W(h))) return 0;
        if (x->dropped && px >= 0 && px < x->w && py >= x->h) {
            int index = x->top + (py - x->h) / (x->item_h > 0 ? x->item_h : 1);
            if (py < x->drop_h && index < x->nitems) {x->sel1=index;x->tracking=1;invalidate(x,0);}
            else web_combo_drop(x, 0);
        } else web_combo_drop(x, !x->dropped && px >= 0 && px < x->w && py >= 0 && py < x->h);
        return 0;
    }
    case WM_LBUTTONUP: {
        int index = x->sel1;
        int selecting = x->tracking;
        x->tracking = 0;
        x->sel1 = -1;
        if (x->dropped && selecting && index >= 0) web_combo_select(x, index, 1);
        return 0;
    }
    case WM_KEYDOWN:
        if (w == 0x1Bu) { web_combo_drop(x, 0); return 0; }
        if (w == 0x0Du && x->dropped) { web_combo_select(x, x->cursel, 1); return 0; }
        if (w == 0x73u) { web_combo_drop(x, !x->dropped); return 0; } /* F4 */
        if ((w == 0x26u && x->cursel > 0) || (w == 0x28u && x->cursel + 1 < x->nitems))
            web_combo_select(x, x->cursel + (w == 0x26u ? -1 : 1), 0);
        return 0;
    case WM_KILLFOCUS:
        web_combo_drop(x, 0); return 0;
    case WM_PAINT: {
        uint32_t h = x->hwnd;
        paint_list(x);
        if (!(x = W(h)) || !x->dropped) return 0;
        int ih = x->item_h > 0 ? x->item_h : 1;
        for (int row = 0; x->top + row < x->nitems && x->h + row * ih < x->drop_h; row++) {
            int bottom = x->h + (row + 1) * ih;
            if (bottom > x->drop_h) bottom = x->drop_h;
            owner_draw(x, 3u, x->top + row, x->top + row == x->cursel ? 1u : 0u,
                       0, x->h + row * ih, x->w, bottom);
            if (!(x = W(h)) || !x->dropped) break;
        }
        return 0;
    }
    default: return def_proc(x->hwnd, m, w, l);
    }
}
