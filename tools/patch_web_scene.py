"""Add lifecycle notifications to the Web-only lifted Conquer.CPP copy."""
def patch(source):
    start=source.index('void sub_00481BF0(void) {')
    end=source.index('\nvoid sub_',start+1)
    body=source[start:end]
    for label,state in [('00481BF0',1),('00481DBA',2),('00481DDA',1)]:
        needle='L_'+label+':\n'
        assert body.count(needle)==1, label
        body=body.replace(needle,needle+'    ra2_web_scene('+str(state)+');\n')
    needle='RECOMP_REGS_OUT(); return;'
    assert needle in body
    body=body.replace(needle,'ra2_web_scene(0); '+needle)
    return 'extern void ra2_web_scene(int);\n'+source[:start]+body+source[end:]
