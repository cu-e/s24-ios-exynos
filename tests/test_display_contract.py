"""Compiled owned display/input boundaries with independent integer expectations."""
import ctypes as C
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src/platform/display'


class Layout(C.Structure):
    _fields_=[('capacity',C.c_uint64),('offset',C.c_uint64),('stride',C.c_uint64),
              ('width',C.c_uint32),('height',C.c_uint32),('format',C.c_uint32),('flags',C.c_uint32)]


class Point(C.Structure):
    _fields_=[('x',C.c_uint32),('y',C.c_uint32)]


class Event(C.Structure):
    _fields_=[('time_ns',C.c_uint64),('epoch',C.c_uint32),('sequence',C.c_uint32),('kind',C.c_uint32),
              ('slot',C.c_uint32),('x',C.c_uint32),('y',C.c_uint32)]


class State(C.Structure):
    _fields_=[('time_ns',C.c_uint64),('epoch',C.c_uint32),('sequence',C.c_uint32),('active',C.c_uint32),
              ('needs_resync',C.c_uint32),('stopped',C.c_uint32)]


class DisplayContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('cc'):raise unittest.SkipTest('Host C compiler required')
        cls.temp=tempfile.TemporaryDirectory(prefix='s24-ui-contract-')
        lib=Path(cls.temp.name)/'ui.so'
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wpedantic','-shared','-fPIC',
                        str(SRC/'contract.c'),'-o',str(lib)],check=True,capture_output=True,text=True,timeout=30)
        cls.lib=C.CDLL(str(lib))
        cls.lib.ui_layout_check.argtypes=[C.POINTER(Layout),C.POINTER(C.c_uint64)]
        cls.lib.ui_region.argtypes=[C.POINTER(Layout),*([C.c_uint32]*4),C.POINTER(C.c_uint64),C.POINTER(C.c_uint64)]
        cls.lib.ui_map_point.argtypes=[*([C.c_uint32]*6),C.POINTER(Point)]
        cls.lib.ui_pixel_point.argtypes=[C.POINTER(Point),C.c_uint32,C.c_uint32,C.POINTER(Point)]
        cls.lib.ui_event_decode.argtypes=[C.c_void_p,C.c_size_t,C.POINTER(Event)]
        cls.lib.ui_input_init.argtypes=[C.POINTER(State),C.c_uint32]
        cls.lib.ui_input_apply.argtypes=[C.POINTER(State),C.POINTER(Event)]
        cls.lib.ui_input_stop.argtypes=[C.POINTER(State)]

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def check_layout(self,p):
        end=C.c_uint64(999);r=self.lib.ui_layout_check(C.byref(p),C.byref(end));return r,end.value

    def test_framebuffer_extent_and_padding_with_exact_last_byte(self):
        p=Layout(10108800,0,4320,1080,2340,1,0)
        self.assertEqual(self.check_layout(p),(0,10108800))
        p.capacity-=1;self.assertEqual(self.check_layout(p),(3,0))
        # Last row needs its pixels, not a whole stride of trailing padding.
        p=Layout(136,8,64,16,2,2,0)
        self.assertEqual(self.check_layout(p),(0,136))
        p.stride=65;p.capacity=137
        self.assertEqual(self.check_layout(p),(0,137))
        p.stride=63;self.assertEqual(self.check_layout(p),(3,0))
        p.format=99;self.assertEqual(self.check_layout(p),(2,0))
        p.format=1;p.flags=1;self.assertEqual(self.check_layout(p),(2,0))

    def test_extent_against_python_big_integer_oracle_including_overflow(self):
        rng=random.Random(24009945)
        for i in range(2048):
            w=rng.randint(1,16384);h=rng.randint(1,16384)
            stride=rng.choice([rng.getrandbits(64),4*w+rng.randrange(128),4*w-1])
            offset=rng.choice([rng.getrandbits(64),0,4096]);actual=offset+(h-1)*stride+4*w
            capacity=rng.choice([2**64-1,min(actual,2**64-1),max(0,min(actual-1,2**64-1))])
            p=Layout(capacity,offset,stride,w,h,1,0)
            want=3 if stride<4*w else 4 if actual>2**64-1 else 3 if actual>capacity else 0
            with self.subTest(case=i):self.assertEqual(self.check_layout(p),(want,actual if want==0 else 0))

    def test_subrect_rejects_wrapped_empty_and_outside_ranges(self):
        p=Layout(256,8,32,6,4,1,0)
        a=C.c_uint64();b=C.c_uint64()
        self.assertEqual(self.lib.ui_region(C.byref(p),1,1,3,2,C.byref(a),C.byref(b)),0)
        self.assertEqual((a.value,b.value),(44,88))
        for args in [(0,0,0,1),(5,3,2,1),(0,4,1,1),(2**32-1,0,2,1),(0,1,1,2**32-1)]:
            self.assertEqual(self.lib.ui_region(C.byref(p),*args,C.byref(a),C.byref(b)),3)
            self.assertEqual((a.value,b.value),(0,0))

    def test_normalized_transform_rotation_and_separate_logical_pixels(self):
        p=Point();pixel=Point()
        for x,y in [(0,0),(4095,0),(0,4095),(4095,4095),(0x123,0xab4)]:
            for flip in range(4):
                nx=x*65535//4095;ny=y*65535//4095
                if flip&1:nx=65535-nx
                if flip&2:ny=65535-ny
                for rot,want in enumerate([(nx,ny),(65535-ny,nx),(65535-nx,65535-ny),(ny,65535-nx)]):
                    self.assertEqual(self.lib.ui_map_point(x,y,4095,4095,flip,rot,C.byref(p)),0)
                    self.assertEqual((p.x,p.y),want)
        p=Point(65535,65535)
        for w,h in [(1080,2340),(1125,2436),(1,1)]:
            self.assertEqual(self.lib.ui_pixel_point(C.byref(p),w,h,C.byref(pixel)),0)
            self.assertEqual((pixel.x,pixel.y),(w-1,h-1))
        for args in [(4096,0,4095,4095,0,0),(0,0,0,4095,0,0),(0,0,4095,4095,4,0),(0,0,4095,4095,0,4)]:
            self.assertEqual(self.lib.ui_map_point(*args,C.byref(p)),3)
            self.assertEqual((p.x,p.y),(0,0))

    @staticmethod
    def wire(**overrides):
        vals=dict(magic=0x49483145,version=1,size=40,epoch=7,sequence=1,time=1234,kind=1,slot=9,x=0x1234,y=65535,reserved=0)
        vals.update(overrides)
        return struct.pack('<IHHIIQHHIII',*vals.values())

    def decode(self,wire):
        # Deliberately unaligned input; no casting to native structs permitted.
        data=C.create_string_buffer(b'x'+wire);out=Event()
        r=self.lib.ui_event_decode(C.byref(data,1),len(wire),C.byref(out));return r,out

    def test_wire_exact_version_size_range_reserved_and_unaligned_bytes(self):
        r,e=self.decode(self.wire());self.assertEqual(r,0)
        self.assertEqual((e.time_ns,e.epoch,e.sequence,e.kind,e.slot,e.x,e.y),(1234,7,1,1,9,0x1234,65535))
        for wire in [self.wire()[:n] for n in range(40)]+[self.wire()+b'x']:
            r,e=self.decode(wire);self.assertEqual(r,1);self.assertEqual(bytes(e),bytes(32))
        for overrides in [dict(version=2),dict(size=24),dict(magic=0),dict(reserved=1),dict(epoch=0),dict(sequence=0),dict(time=0),dict(slot=10),dict(kind=0),dict(x=65536),dict(kind=4,slot=1)]:
            r,e=self.decode(self.wire(**overrides));self.assertNotEqual(r,0);self.assertEqual(bytes(e),bytes(32))

    def state(self):
        s=State();self.assertEqual(self.lib.ui_input_init(C.byref(s),7),0);return s

    def apply(self,s,seq,kind=1,slot=0,time=None,epoch=7):
        e=Event(time if time is not None else seq*100,epoch,seq,kind,slot,0,0)
        return self.lib.ui_input_apply(C.byref(s),C.byref(e))

    def test_contacts_require_initial_cancel_and_valid_transitions(self):
        s=self.state();self.assertEqual(self.apply(s,1),8)
        self.assertEqual(self.apply(s,1,4),0)
        for slot in range(10):self.assertEqual(self.apply(s,slot+2,1,slot),0)
        self.assertEqual(s.active,1023)
        self.assertEqual(self.apply(s,12,2,9),0)
        self.assertEqual(self.apply(s,13,3,9),0);self.assertEqual(s.active,511)
        self.assertEqual(self.apply(s,14,2,9),9);self.assertEqual(s.active,511)
        self.assertEqual(self.apply(s,15,2,0),8)
        self.assertEqual(self.apply(s,16,4),0);self.assertEqual(s.active,0)

    def test_loss_replay_clock_wrong_session_stop_and_wrap(self):
        s=self.state();self.apply(s,1,4);self.apply(s,2)
        self.assertEqual(self.apply(s,4,2),7);self.assertEqual(s.active,1)
        self.assertEqual(self.apply(s,5,4),0)
        self.assertEqual(self.apply(s,6,epoch=8),6);self.assertEqual(s.needs_resync,0)
        self.assertEqual(self.apply(s,6),0)
        self.assertEqual(self.apply(s,6),7)
        self.assertEqual(self.apply(s,7,4,time=599),10);self.assertEqual(s.active,1)
        self.assertEqual(self.apply(s,8,4),0)
        self.apply(s,9);self.lib.ui_input_stop(C.byref(s))
        self.assertEqual(s.active,1);self.assertEqual(self.apply(s,10,4),11);self.assertEqual(s.active,1)
        s=self.state();self.assertEqual(self.apply(s,2**32-1,4),0)
        self.assertEqual(self.apply(s,1),7)


if __name__=='__main__':unittest.main()
