import hashlib,importlib.util,json,pathlib,sys
M=pathlib.Path('/home/egor/dev/pet/s24-ios-exynos');H=pathlib.Path(__file__).resolve().parent
p=M/'worktrees/vm-035-20261106/tools/build/avf_kernel_objects.py'
assert hashlib.sha256(p.read_bytes()).hexdigest()=='5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8'
s=importlib.util.spec_from_file_location('accepted_source_boundary',p);e=importlib.util.module_from_spec(s);s.loader.exec_module(e)
o=H/'runs'/sys.argv[1];o.mkdir(parents=True,exist_ok=False)
script=sys.argv[2] if len(sys.argv)>2 else 'probe.py'
assert script in ['probe.py','runtime_probe.py']
r=e.run_child([sys.executable,'-B','-s',str(H/script),'--out',str(o)],H,o,'probe',e.supervisor(M),timeout=120,admit=True)
(o/'supervised.json').write_text(json.dumps({'kind':'host-test','origin':'local-host','process':r,'probe_sha256':hashlib.sha256((H/script).read_bytes()).hexdigest()},indent=2)+'\n')
print(json.dumps({'process_outcome':r['outcome'],'exit_code':r.get('exit_code'),'peak_RSS':r.get('peak_total_owned_rss_bytes'),'evidence':str(o/'evidence.json')}))
sys.exit(0 if r['outcome']=='pass' else 1)
