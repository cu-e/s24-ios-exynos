"""Exercise the real owned STM parser/adapter; no phone or MMIO access."""
import ctypes as C
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src/platform/input/stm'
REFERENCES=Path(os.environ.get('S24_STM_REFERENCE_ROOT',ROOT/'references'))


class Coordinate(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['slot','action','x','y','touch_type','pressure','major','minor','remaining']]
class Config(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['max_x','max_y','flip','rotation']]
class Event(C.Structure):
    _fields_=[('time_ns',C.c_uint64)]+[(n,C.c_uint32) for n in ['epoch','sequence','kind','slot','x','y']]
class State(C.Structure):
    _fields_=[('time_ns',C.c_uint64)]+[(n,C.c_uint32) for n in ['epoch','sequence','active','needs_resync','stopped']]
class Adapter(C.Structure):
    _fields_=[('logical',State),('candidate',State),('pending',Event),('config',Config)]+[(n,C.c_uint32) for n in ['pending_valid','dispatching','stop_after']]
EMIT=C.CFUNCTYPE(C.c_int,C.c_void_p,C.POINTER(Event))


def packet(x=0x123,y=0xabc,slot=0,action=1,touch_type=0,remaining=0):
    # Project fixture writer follows named Samsung byte fields, not parser code.
    raw=bytearray(16);raw[0]=action*64+slot*4;raw[1]=x//16;raw[2]=y//16
    raw[3]=(x%16)*16+y%16;raw[4]=12;raw[5]=9
    raw[6]=31+(touch_type//4)*64;raw[7]=remaining+(touch_type%4)*64
    return bytes(raw)


class StmTouchTests(unittest.TestCase):
    @classmethod
    def compile(cls,argv):
        result=subprocess.run(argv,capture_output=True,text=True,timeout=30)
        cls.build_records.append(dict(argv=argv,cwd=os.getcwd(),exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr))
        if cls.evidence:
            compiler=Path(cls.compiler).resolve()
            (cls.evidence/'commands.json').write_text(json.dumps(dict(recorded_at=datetime.now(timezone.utc).isoformat(),
                compiler=dict(path=str(compiler),sha256=hashlib.sha256(compiler.read_bytes()).hexdigest()),commands=cls.build_records),indent=2)+'\n')
        result.check_returncode()

    @classmethod
    def setUpClass(cls):
        compiler=shutil.which('cc')
        if compiler is None:raise unittest.SkipTest('Host C compiler required')
        cls.compiler=compiler;cls.build_records=[];cls.evidence=None
        cls.temp=tempfile.TemporaryDirectory(prefix='s24-stm-tests-')
        cls.build_root=Path(cls.temp.name)
        if os.environ.get('S24_STM_EVIDENCE_ROOT'):
            cls.evidence=Path(os.environ['S24_STM_EVIDENCE_ROOT']).resolve()
            if not cls.evidence.is_relative_to(ROOT/'artifacts'):raise ValueError('Owned artifact prefix required')
            cls.evidence.mkdir(parents=True,exist_ok=False);cls.build_root=cls.evidence
        path=cls.build_root/'stm.so'
        cls.compile([compiler,'-std=c11','-Wall','-Wextra','-Werror','-Wpedantic','-shared','-fPIC',
            str(SRC/'protocol.c'),str(ROOT/'src/platform/display/contract.c'),'-o',str(path)])
        cls.lib=C.CDLL(str(path))
        cls.lib.stm_decode.argtypes=[C.c_void_p,C.c_size_t,C.c_uint32,C.c_uint32,C.POINTER(Coordinate)]
        cls.lib.stm_adapter_init.argtypes=[C.POINTER(Adapter),C.POINTER(Config),C.c_uint32]
        cls.lib.stm_adapter_feed.argtypes=[C.POINTER(Adapter),C.c_void_p,C.c_size_t,C.c_uint64,EMIT,C.c_void_p]
        for name in ['stm_adapter_resync','stm_adapter_stop']:
            getattr(cls.lib,name).argtypes=[C.POINTER(Adapter),C.c_uint64,EMIT,C.c_void_p]
        cls.lib.stm_adapter_retry.argtypes=[C.POINTER(Adapter),EMIT,C.c_void_p]
        cls.lib.stm_event_wire.argtypes=[C.POINTER(Event),C.c_void_p,C.c_size_t]
        cls.lib.ui_event_decode.argtypes=[C.c_void_p,C.c_size_t,C.POINTER(Event)]
        cls.lib.ui_map_point.argtypes=[*([C.c_uint32]*6),C.c_void_p]

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        self.adapter=Adapter();self.events=[];self.decline=False
        def accept(_context,event):
            if self.decline:return 1
            self.events.append(Event.from_buffer_copy(event.contents));return 0
        self.emit=EMIT(accept)
        self.assertEqual(self.lib.stm_adapter_init(C.byref(self.adapter),C.byref(Config(4095,4095,0,0)),7),0)

    def decode(self,raw,max_x=4095,max_y=4095):
        result=Coordinate(*([0xffffffff]*9));buffer=C.create_string_buffer(bytes(raw))
        code=self.lib.stm_decode(buffer,len(raw),max_x,max_y,C.byref(result))
        return code,result

    def feed(self,raw=None,now=200):
        raw=packet() if raw is None else raw;buffer=C.create_string_buffer(raw)
        return self.lib.stm_adapter_feed(C.byref(self.adapter),buffer,len(raw),now,self.emit,None)

    def sync(self,now=100):
        return self.lib.stm_adapter_resync(C.byref(self.adapter),now,self.emit,None)

    def test_independent_named_vectors_and_every_nibble(self):
        fixture=json.loads((ROOT/'fixtures/public/stm-touch/vectors.json').read_text())
        for v in fixture['vectors']:
            code,out=self.decode(bytes.fromhex(v['hex']))
            self.assertEqual(code,0)
            self.assertEqual((out.x,out.y,out.slot,out.action,out.touch_type),(v['x'],v['y'],v['slot'],v['action'],v['touch_type']))
        for x in range(16):
            for y in range(16):
                code,out=self.decode(packet(0x120+x,0xab0+y,slot=9))
                self.assertEqual((code,out.x,out.y,out.slot),(0,0x120+x,0xab0+y,9))

    def test_truncation_oversize_null_and_invalid_configuration(self):
        for length in [*range(16),17,32,4096]:
            code,out=self.decode(packet()[:length] if length<16 else packet()+bytes(length-16))
            self.assertEqual(code,4);self.assertEqual(bytes(out),bytes(C.sizeof(out)))
        out=Coordinate();self.assertEqual(self.lib.stm_decode(None,16,4095,4095,C.byref(out)),3)
        self.assertEqual(self.lib.stm_decode(None,16,4095,4095,None),3)
        for x,y in [(0,4095),(4095,0),(4096,4095),(4095,2**32-1)]:self.assertEqual(self.decode(packet(),x,y)[0],3)
        for cfg in [Config(0,4095,0,0),Config(4095,4095,4,0),Config(4095,4095,0,4)]:
            self.assertEqual(self.lib.stm_adapter_init(C.byref(Adapter()),C.byref(cfg),1),3)

    def test_invalid_contact_action_type_and_inclusive_ranges(self):
        for slot in range(10,16):self.assertEqual(self.decode(packet(slot=slot))[0],6)
        raw=bytearray(packet());raw[0]=4
        self.assertEqual(self.decode(raw)[0],5)
        for touch_type in [1,2,4,7,8,15]:self.assertEqual(self.decode(packet(touch_type=touch_type))[0],7)
        for touch_type in [0,3,5,6]:self.assertEqual(self.decode(packet(touch_type=touch_type))[0],0)
        self.assertEqual(self.decode(packet(4095,4095))[0],0)
        self.assertEqual(self.decode(packet(100,101),100,100)[0],6)
        self.assertEqual(self.decode(packet(100,100),100,100)[0],0)

    def test_controller_status_loss_empty_and_unhandled_events(self):
        self.assertEqual(self.decode(bytes(16))[0],1)
        raw=bytearray(16);raw[0]=1;self.assertEqual(self.decode(raw)[0],2)
        for status_id in [0,1,2,255]:
            raw[0]=5;raw[1]=status_id;self.assertEqual(self.decode(raw)[0],8)
        raw[0]=9;raw[1]=0;raw[2]=0x10;self.assertEqual(self.decode(raw)[0],8)
        raw[1]=1;self.assertEqual(self.decode(raw)[0],2)
        raw[0]=2;self.assertEqual(self.decode(raw)[0],2)

    def test_attach_requires_cancel_and_full_ten_contact_lifecycle(self):
        self.assertEqual(self.feed(),10);self.assertFalse(self.events)
        self.assertEqual(self.sync(),0);self.assertEqual(self.events[0].kind,4)
        for slot in range(10):self.assertEqual(self.feed(packet(slot=slot),200+slot),0)
        self.assertEqual(self.adapter.logical.active,1023)
        for slot in range(10):self.assertEqual(self.feed(packet(slot=slot,action=2),300+slot),0)
        for slot in range(10):self.assertEqual(self.feed(packet(slot=slot,action=3),400+slot),0)
        self.assertEqual(self.adapter.logical.active,0)
        self.assertEqual([e.sequence for e in self.events],list(range(1,32)))

    def test_no_implicit_down_and_duplicate_press_requires_cancel(self):
        self.assertEqual(self.sync(),0)
        self.assertEqual(self.feed(packet(action=2)),9);self.assertEqual(self.adapter.logical.active,0)
        self.assertEqual(self.feed(),10);self.assertEqual(self.sync(201),0)
        self.assertEqual(self.feed(now=202),0);self.assertEqual(self.feed(now=203),9)
        self.assertEqual(self.adapter.logical.active,1);self.assertEqual(self.sync(204),0)
        self.assertEqual(self.feed(packet(action=3),205),9)

    def test_declined_delivery_retries_same_event_and_blocks_new_input(self):
        self.assertEqual(self.sync(),0);self.decline=True
        self.assertEqual(self.feed(),14);self.assertEqual(self.adapter.logical.active,0)
        before=bytes(self.adapter.pending)
        self.assertEqual(self.feed(packet(slot=1),201),13)
        self.assertEqual(self.lib.stm_adapter_retry(C.byref(self.adapter),self.emit,None),14)
        self.assertEqual(bytes(self.adapter.pending),before)
        self.decline=False;self.assertEqual(self.lib.stm_adapter_retry(C.byref(self.adapter),self.emit,None),0)
        self.assertEqual(self.adapter.logical.active,1);self.assertEqual(self.events[-1].sequence,2)

    def test_stop_cancels_acknowledged_contacts_before_marking_stopped(self):
        self.sync();self.feed();self.decline=True
        self.assertEqual(self.feed(packet(action=3),201),14)
        self.assertEqual(self.adapter.logical.active,1)
        self.assertEqual(self.lib.stm_adapter_stop(C.byref(self.adapter),202,self.emit,None),14)
        self.assertEqual((self.adapter.pending.kind,self.adapter.pending.sequence),(4,3))
        self.assertEqual(self.adapter.logical.stopped,0);self.assertEqual(self.adapter.logical.active,1)
        self.assertEqual(self.sync(203),13)
        self.decline=False;self.assertEqual(self.lib.stm_adapter_retry(C.byref(self.adapter),self.emit,None),0)
        self.assertEqual((self.adapter.logical.active,self.adapter.logical.stopped),(0,1))
        self.assertEqual(self.feed(now=204),15)

    def test_malformed_clock_and_loss_do_not_clear_active_contacts(self):
        self.sync();self.feed()
        self.assertEqual(self.feed(packet()[:15],201),4)
        self.assertEqual((self.adapter.logical.active,self.adapter.logical.needs_resync),(1,1))
        self.assertEqual(self.feed(packet(action=3),202),10)
        self.assertEqual(self.sync(203),0);self.assertEqual(self.feed(now=202),11)
        self.assertEqual(self.adapter.logical.sequence,3)
        self.assertEqual(self.sync(204),0);self.assertEqual(self.feed(now=205),0)
        status=bytes([5,1])+bytes(14);self.assertEqual(self.feed(status,206),8)
        self.assertEqual(self.adapter.logical.active,1);self.assertEqual(self.adapter.logical.needs_resync,1)

    def test_sequence_exhaustion_reserves_final_cancellation(self):
        self.sync();self.feed();self.adapter.logical.sequence=2**32-2
        self.assertEqual(self.feed(packet(action=2),201),12)
        self.assertEqual(self.adapter.logical.active,1)
        self.assertEqual(self.sync(202),0);self.assertEqual(self.events[-1].sequence,2**32-1)
        self.assertEqual(self.adapter.logical.active,0)
        self.assertEqual(self.lib.stm_adapter_stop(C.byref(self.adapter),203,self.emit,None),0)
        self.assertEqual(self.adapter.logical.stopped,1)

    def test_reentrant_sink_is_busy_and_invalid_cancel_preserves_pending(self):
        self.sync();outcomes=[]
        def reentrant(_context,_event):
            outcomes.append(self.feed(packet(slot=1),201));return 0
        cb=EMIT(reentrant);raw=C.create_string_buffer(packet())
        self.assertEqual(self.lib.stm_adapter_feed(C.byref(self.adapter),raw,16,200,cb,None),0)
        self.assertEqual(outcomes,[13]);self.assertEqual(self.adapter.logical.active,1)
        self.decline=True;self.assertEqual(self.feed(packet(action=3),202),14)
        before=bytes(self.adapter.pending)
        self.assertEqual(self.sync(199),11);self.assertEqual(bytes(self.adapter.pending),before)
        self.decline=False;self.assertEqual(self.lib.stm_adapter_retry(C.byref(self.adapter),self.emit,None),0)

    def test_normalization_rotations_and_owned_wire_interoperate(self):
        for flip in range(4):
            for rotate in range(4):
                self.assertEqual(self.lib.stm_adapter_init(C.byref(self.adapter),C.byref(Config(4095,4095,flip,rotate)),7),0)
                self.sync();self.feed(packet(0x123,0xabc))
                x=0x123*65535//4095;y=0xabc*65535//4095
                if flip&1:x=65535-x
                if flip&2:y=65535-y
                want=[(x,y),(65535-y,x),(65535-x,65535-y),(y,65535-x)][rotate]
                self.assertEqual((self.events[-1].x,self.events[-1].y),want)
        event=Event(0x0102030405060708,7,2,1,9,0x1234,0xabcd);wire=(C.c_ubyte*40)()
        self.assertEqual(self.lib.stm_event_wire(C.byref(event),wire,40),0)
        self.assertEqual(bytes(wire).hex(),'4531484901002800070000000200000008070605040302010100090034120000cdab000000000000')
        decoded=Event();self.assertEqual(self.lib.ui_event_decode(wire,40,C.byref(decoded)),0)
        self.assertEqual(bytes(event),bytes(decoded))
        event.kind=0;self.assertEqual(self.lib.stm_event_wire(C.byref(event),wire,40),5)
        self.assertEqual(bytes(wire),bytes(40))
        self.assertEqual(self.lib.stm_event_wire(C.byref(event),wire,39),4)

    def test_arbitrary_record_bytes_are_bounded(self):
        rng=random.Random(24009945)
        for _ in range(4096):
            raw=rng.randbytes(16);code,out=self.decode(raw)
            self.assertIn(code,range(9))
            if code==0:
                self.assertLess(out.slot,10);self.assertIn(out.action,[1,2,3]);self.assertLessEqual(out.x,4095);self.assertLessEqual(out.y,4095)
            else:self.assertEqual(bytes(out),bytes(C.sizeof(out)))

    def test_corrected_actual_donor_coordinate_equivalence(self):
        if not (REFERENCES/'s24-port/.git').exists():self.skipTest('Pinned s24-port reference not available')
        spec=importlib.util.spec_from_file_location('stm_donor_regression',ROOT/'tests/test_e1s_touch_regression.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.UPSTREAM=REFERENCES/'s24-port';module.SOURCE_PATCH=module.UPSTREAM/'xnu/e1s/patches/0003-e1s-touch.patch'
        path=self.build_root/'donor';path.mkdir()
        text=module.corrected(module.source_file(),path)
        shim=module.harness(text).split('int main(void) {',1)[0]
        shim+='\nvoid donor(const uint8_t *p,unsigned flip,unsigned *out) { e1s_flip=flip; calls=0; for(unsigned i=0;i<10;i++)down[i]=0; post_event(p); out[0]=calls;out[1]=got_x;out[2]=got_y; }\n'
        source=path/'actual-corrected-decoder.c';source.write_text(shim);binary=path/'decoder.so'
        self.compile([self.compiler,'-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',str(source),'-o',str(binary)])
        lib=C.CDLL(str(binary));lib.donor.argtypes=[C.c_void_p,C.c_uint,C.POINTER(C.c_uint)]
        for flip in range(4):
            for lowx in range(16):
                for lowy in range(16):
                    raw=packet(0x120+lowx,0xab0+lowy);out=(C.c_uint*3)();lib.donor(C.create_string_buffer(raw),flip,out)
                    code,coord=self.decode(raw);point=(C.c_uint32*2)()
                    self.assertEqual(code,0)
                    self.assertEqual(self.lib.ui_map_point(coord.x,coord.y,4095,4095,flip,0,point),0)
                    self.assertEqual(tuple(out),(1,point[0],point[1]))


if __name__=='__main__':unittest.main()
