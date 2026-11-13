#!/usr/bin/env python3
"""Host-only no-response IRQ admission regression; no device access."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT / 'artifacts/nat-123/kernel-003/src/bsd_e1s_touch.o/e1s_touch.c'
PATCH = HERE / 'e1s_touch.patch'
HOST = HERE.parent / 'nat-121/host'


def run_case(responsive=False, fixed=True):
    with tempfile.TemporaryDirectory(prefix='nat125-', dir=os.environ.get('TMPDIR')) as directory:
        directory = Path(directory)
        src = directory / 't.c'
        src.write_text(BASE.read_text())
        if fixed and PATCH.exists():
            subprocess.run(['patch', '-s', str(src), str(PATCH)], check=True)
        text = '\n'.join(l for l in src.read_text().splitlines() if not l.startswith('#include'))
        text = text.replace('return *(volatile uint32_t *)reg;', 'return host_rd(reg);')
        text = text.replace('*(volatile uint32_t *)reg = value;', 'host_wr(reg, value);')
        pre = '#include "shim.h"\nuint32_t host_rd(uintptr_t); void host_wr(uintptr_t,uint32_t);\n'
        pre += '#define kernel_thread_start host_thread_start\nstatic int threads;\n'
        pre += 'static kern_return_t host_thread_start(void (*f)(void *,wait_result_t),void *a,thread_t *t) { (void)f;(void)a;*t=0;threads++;return 0;}\n'
        if responsive == 'valid':
            # Explicit synthetic SPI peer; this verifies admission, not electrical SPI.
            anchor = 'static void\nstm_write('
            peer = ('static void host_transfer(const uint8_t *tx,uint8_t *rx,uint32_t n) { '
                    '(void)tx; if(rx) { memset(rx,0,n); if(n>=9) { rx[4]=0x53;rx[5]=0x54;rx[6]=0x48;rx[7]=0x36;rx[8]=1; } } }\n')
            text = text.replace(anchor, peer + anchor)
            # Leave the original transfer definition intact, replace callers only.
            text = text.replace('e1s_spi_transfer(tx, NULL, n);', 'host_transfer(tx, NULL, n);')
            text = text.replace('e1s_spi_transfer(tx, rx, len + 2);', 'host_transfer(tx, rx, len + 2);')
            text = text.replace('e1s_spi_transfer(tx, rx, len + 4);', 'host_transfer(tx, rx, len + 4);')
        text += '\nint main(void) { host_steps=3;'
        if responsive is True:
            # A synthetic high MISO yields all FF, used as no-response control.
            text += ' *(uint32_t *)(fake_page[0]+0xe4)=1;'
        text += ' e1s_touch_init(); printf("RESULT irq=%d threads=%d bad=%d\\n",host_irq_attached,threads,host_bad);return 0;}\n'
        src.write_text(pre + text)
        exe = directory / 't'
        subprocess.run(['cc', '-std=gnu11', '-w', '-I', str(HOST), str(src), str(HOST / 'harness.c'), '-o', str(exe)], check=True)
        return subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=10).stdout


class AdmissionTests(unittest.TestCase):
    def test_unfixed_zero_id_enables_irq_and_thread(self):
        self.assertIn('RESULT irq=1 threads=1 bad=0', run_case(fixed=False))

    def test_fixed_zero_id_never_enables_irq_or_thread(self):
        self.assertIn('RESULT irq=0 threads=0 bad=0', run_case())

    def test_responsive_peer_keeps_stage3_and_correct_id_log(self):
        out = run_case(responsive='valid')
        self.assertIn('RESULT irq=1 threads=1 bad=0', out)
        self.assertIn('device id: ok (53 54 48 36 01)', out)

    def test_fixed_all_ff_never_enables_irq_or_thread(self):
        self.assertIn('RESULT irq=0 threads=0 bad=0', run_case(responsive=True))


if __name__ == '__main__':
    unittest.main(verbosity=2)
