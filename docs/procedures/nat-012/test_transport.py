import importlib.util
from pathlib import Path
import struct
import unittest
s=importlib.util.spec_from_file_location('restore',Path(__file__).with_name('restore_stock.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class GuardTests(unittest.TestCase):
    def test_wire_target_and_forbidden_operations(self):
        b=m.packet(0x66,3,(0,6291456,0,8,18,1,0,0))
        self.assertEqual(len(b),1024)
        self.assertEqual(struct.unpack_from('<10I',b),(0x66,3,0,6291456,0,8,18,1,0,0))
        for cmd in [(0x65,0),(0x67,2),(0x66,7),(0x68,0)]:
            with self.assertRaises(ValueError):m.packet(*cmd)
        for words in [(0,6291456,0,8,20,1,0,0),(0,6291456,0,8,18,1,1,0),(0,100663296,0,8,18,1,0,0)]:
            with self.assertRaises(ValueError):m.packet(0x66,3,words)
    def test_measured_pit_and_corruption_reject(self):
        b=Path('artifacts/recovery-rescue-20261110-01/device.pit').read_bytes()
        self.assertEqual(m.validate_pit(b)[2],18)
        b=bytearray(b);b[28+24*132+8]=20
        with self.assertRaises(ValueError):m.validate_pit(b)
    def test_nonzero_result_is_rejected(self):
        class Device:
            def write(self,ep,b,timeout):return len(b)
            def read(self,ep,n,timeout):return struct.pack('<II',0x66,7)
        class Out:
            def __truediv__(self,other):return self
            def write_text(self,*args):pass
        with self.assertRaises(RuntimeError):m.Link(Device(),Out()).command(0x66,0)
if __name__=='__main__':unittest.main()
