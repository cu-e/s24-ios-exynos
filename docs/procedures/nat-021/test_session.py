#!/usr/bin/env python3
"""Host fault injection: this file never invokes adb or opens a phone."""
import contextlib,importlib.util,io,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('session',Path(__file__).with_name('session.py'))
session=importlib.util.module_from_spec(spec);spec.loader.exec_module(session)

class FaultControls(unittest.TestCase):
    def scenario(self,mode='--execute',mismatch=False,busy=False,wrong_target=False,reboot_failure=False,retry=False,partial=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);base=root/'candidate';base.mkdir()
            stock=root/'stock';stock.write_bytes(b'stock!')
            image=base/'recovery.img';image.write_bytes(b'native')
            new=session.digest(image.read_bytes());old=session.digest(stock.read_bytes())
            (base/'report.json').write_text(json.dumps(dict(outcome='pass',image=dict(sha256=new))))
            (base/'binary-review.json').write_text(json.dumps(dict(outcome='pass')))
            state={'bytes':b'stock!','writes':[],'reboots':0,'bad':mismatch,'partial':partial}
            def fake(argv,**kw):
                code=0;out=''
                if argv==['adb','get-state']:out='device'
                elif argv==['adb','reboot','recovery']:
                    state['reboots']+=1;code=1 if reboot_failure else 0
                elif argv[:3]==['adb','shell','-T']:
                    cmd=argv[3]
                    if cmd==session.WRITE:
                        state['writes'].append(kw['input']);state['bytes']=kw['input']
                        if state['partial']:
                            state['partial']=False;state['bytes']=b'partly';code=1
                    elif 'sha256sum' in cmd:
                        out=session.digest(state['bytes'])+'  /dev/block/sda18'
                        if state['bad'] and state['writes']:
                            state['bad']=False;out='0'*64+'  /dev/block/sda18'
                    elif 'pidof dd' in cmd:out='busy' if busy else 'idle'
                    elif 'readlink' in cmd:out=('/dev/block/sda19' if wrong_target else '/dev/block/sda18')+'\n6\nblock_device'
                    elif 'dumpsys battery' in cmd:out='level=84\ntemperature=298'
                    else:
                        out={'getprop ro.product.model':'SM-S921B','getprop ro.product.device':'e1s',
                             'getprop ro.build.PDA':'S921BXXS9BYH3','getprop sys.boot_completed':'1'}[cmd]
                else:raise AssertionError('unexpected command '+repr(argv))
                return subprocess.CompletedProcess(argv,code,out.encode(),b'')
            with patch.multiple(session,ROOT=root,SIZE=6,CANDIDATE=image,STOCK=stock,NEW_SHA=new,STOCK_SHA=old), \
                 patch.object(session.subprocess,'run',side_effect=fake), \
                 patch.object(session.subprocess,'check_output',return_value='adb\n'),contextlib.redirect_stdout(io.StringIO()):
                with patch('sys.argv',['session','--out',str(root/'run'),mode] if mode else ['session','--out',str(root/'run')]):
                    rc=session.main()
                if retry:
                    with patch('sys.argv',['session','--out',str(root/'retry'),'--execute']):
                        self.assertEqual(session.main(),2)
            return rc,state
    def test_single_launch_after_readback(self):
        rc,s=self.scenario();self.assertEqual((rc,s['writes'],s['reboots']),(0,[b'native'],1))
    def test_readback_mismatch_restores_without_reboot(self):
        rc,s=self.scenario(mismatch=True);self.assertEqual((rc,s['bytes'],s['reboots']),(2,b'stock!',0))
        self.assertEqual(s['writes'],[b'native',b'stock!'])
    def test_partial_write_failure_restores_without_reboot(self):
        rc,s=self.scenario(partial=True);self.assertEqual((rc,s['bytes'],s['reboots']),(2,b'stock!',0))
    def test_busy_writer_and_wrong_target_refuse_every_write(self):
        for kw in [dict(busy=True),dict(wrong_target=True)]:
            rc,s=self.scenario(**kw);self.assertEqual((rc,s['writes'],s['reboots']),(2,[],0))
    def test_preflight_never_writes(self):
        rc,s=self.scenario(mode='');self.assertEqual((rc,s['writes'],s['reboots']),(0,[],0))
    def test_attempt_marker_refuses_retry(self):
        rc,s=self.scenario(retry=True);self.assertEqual(len(s['writes']),1);self.assertEqual(s['reboots'],1)
    def test_unknown_reboot_result_never_launches_another_writer(self):
        rc,s=self.scenario(reboot_failure=True);self.assertEqual((rc,len(s['writes']),s['reboots']),(2,1,1))

if __name__=='__main__':unittest.main()
