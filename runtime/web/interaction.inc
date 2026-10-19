/* Appended only to the Web USER32 build copy. Inspect the real message queue,
 * rather than assuming that a canvas presentation consumed its mouse events. */
int hle_web_mouse_pending(void) {
    for (int i=0;i<g_qn;i++)
        if (g_q[i].message>=WM_MOUSEMOVE && g_q[i].message<=WM_MBUTTONUP)
            return 1;
    return 0;
}
int hle_web_dialog_open(void) {
    for (int i=0;i<MAX_WIN;i++) {
        win_t *x=&g_win[i];
        if (x->used && !x->destroying && x->w>0 && x->h>0 &&
            (x->kind==K_DIALOG || x->dlgproc) && visible(x)) return 1;
    }
    return 0;
}
void hle_web_reset_input(void) {
    g_keys[1]&=1;g_keys[2]&=1;
    for (int vk=37;vk<=40;vk++)g_keys[vk]&=1;
    g_capture=0;
    for (int i=g_qn-1;i>=0;i--)
        if (g_q[i].message>=WM_MOUSEMOVE && g_q[i].message<=WM_MBUTTONUP) {
            memmove(g_q+i,g_q+i+1,sizeof g_q[0]*(size_t)(--g_qn-i));
        }
}
