#!/usr/bin/env python3
"""Host-execute bounded ID sequence against explicit synthetic SPI peers."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT / 'artifacts/nat-125/kernel-001/src/bsd_e1s_touch.o/e1s_touch.c'
HOST = HERE.parent / 'nat-121/host'


def run_case(answer=False):
    with tempfile.TemporaryDirectory(prefix='nat128-', dir=os.environ.get('TMPDIR')) as tmp:
        tmp = Path(tmp)
        source = tmp / 't.c'
        source.write_text(BASE.read_text())
        patch = HERE / 'diagnostic.patch'
        if patch.exists():
            subprocess.run(['patch', '-s', str(source), str(patch)], check=True)
        text = '\n'.join(l for l in source.read_text().splitlines() if not l.startswith('#include'))
        text = text.replace('return *(volatile uint32_t *)reg;', 'return host_rd(reg);')
        text = text.replace('*(volatile uint32_t *)reg = value;', 'host_wr(reg, value);')
        # Observe actual complete command frames at the SPI transfer boundary.
        pos = text.index('static void\ne1s_spi_transfer(')
        end = text.index('\nstatic void\nstm_write(', pos)
        peer = '''static void
e1s_spi_transfer(const uint8_t *tx, uint8_t *rx, uint32_t n)
{
    printf("TX");
    for(uint32_t i=0;i<n;i++) printf(" %02x", tx ? tx[i] : 0);
    printf("\\n");
    if(rx) { memset(rx,0,n); if(HOST_ANSWER) memset(rx,0x5a,n); }
}
'''
        text = text[:pos] + peer + text[end:]
        pre = '#include "shim.h"\nuint32_t host_rd(uintptr_t); void host_wr(uintptr_t,uint32_t);\n'
        pre += '#define HOST_ANSWER %d\n' % answer
        pre += '#define kernel_thread_start host_thread_start\nstatic int threads;\n'
        pre += 'static kern_return_t host_thread_start(void (*f)(void *,wait_result_t),void *a,thread_t *t) { (void)f;(void)a;*t=0;threads++;return 0;}\n'
        text += '\nint main(void) { host_steps=3; e1s_touch_init(); printf("RESULT irq=%d threads=%d bad=%d\\n",host_irq_attached,threads,host_bad);return 0;}\n'
        source.write_text(pre + text)
        exe = tmp / 't'
        subprocess.run(['cc','-std=gnu11','-w','-I',str(HOST),str(source),str(HOST/'harness.c'),'-o',str(exe)],check=True)
        return subprocess.run([str(exe)],check=True,capture_output=True,text=True,timeout=10).stdout


class PollingTests(unittest.TestCase):
    def test_exact_readonly_sequence_and_bound_for_both_peers(self):
        expected = ['TX c0 22', 'TX d1 00 00 00 00 00 00 00 00',
                    'TX fb 20 00 00 00 00 00 00 00 00 00 00 00 00'] * 3
        for answer in (False, True):
            with self.subTest(answer=answer):
                out = run_case(answer)
                self.assertEqual([l for l in out.splitlines() if l.startswith('TX')], expected)
                self.assertIn('RESULT irq=0 threads=0 bad=0',out)
                self.assertIn('poll-only diagnostic complete',out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
