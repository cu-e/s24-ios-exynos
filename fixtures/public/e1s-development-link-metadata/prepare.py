"""STR032 metadata recipe binding only. Does not invoke Make or generators."""
import hashlib
import json
from pathlib import Path

WT = Path(__file__).resolve().parents[3]
MAIN = WT.parents[1]
BASE = WT/'fixtures/public/e1s-development-link-metadata'
OUT = WT/'artifacts/e1s-development-link-metadata/generate-1'
OWNER = 'codex-e1s-development-link-metadata-20261106-sr32'

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def prepare():
    pins = {}
    def pin(path, expected=None):
        path = Path(path)
        digest = sha(path)
        if expected is not None and digest != expected:
            raise ValueError('Changed bound input: '+str(path))
        pins[str(path)] = digest
        return path
    def read(path, expected=None):
        return json.loads(pin(path, expected).read_text())
    inventory = read(MAIN/'worktrees/int-platform-20261106/docs/integration/platform/native-link-readiness-20261106/inventory.json',
        '88ad0d071bb04b1a061d4ad1e451e2abc3bb40deda32c64c646e9064816ae991')
    context = read(MAIN/'fixtures/public/e1s-native-source-ports/source-context.json',
        '3b87fdab0a2953438c7fd78f420e138604c258b5d09b97c444187737347df8dc')
    source = Path(context['source_root'])
    manifest = read(context['source_manifest'], context['source_manifest_sha256'])
    for path, digest in inventory['source_rule_input_sha256'].items():
        pin(path, digest)
        p = Path(path)
        if p.is_relative_to(source):
            if manifest[str(p.relative_to(source))] != digest:
                raise ValueError('Source outside accepted derivative: '+path)
    version = read(MAIN/'fixtures/public/e1s-development-version/generated-development.json',
        '3377dee1ef93f28db5f07e5f5b8b09058fb477aafa2b6147237ad15c0333a1c8')
    read(MAIN/'fixtures/public/e1s-development-exports/qualified-namespace.json',
        '96694dccbb3723199ea0f27893ee7e40b33373a916c4a500a91af5e89e87d5a5')
    pin(source/'config/MasterVersion','70716152d26b917b0ad1034d77d18dd55073cddf48d43f04becbb5c5edd95c52')
    helpers = {}
    for name,path,digest in [
        ('supervisor',MAIN/'tools/build/qemu_host.py','faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99'),
        ('cancellation',MAIN/'worktrees/vm-022-link-cursor-20261106/tools/build/avf_guest_link_inputs.py','9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5'),
        ('work_guard',MAIN/'worktrees/vm-022-diagnostic-20261106/fixtures/public/avf-guest-link-inputs/run-link-diagnostic.py','23b88dcc7c2ca20064b4ad8204d9cc713783f79f858d7e25791b85f58a8803d5')]:
        pin(path,digest); helpers[name] = dict(path=str(path),sha256=digest)
    tools = ['/usr/bin/env','/bin/sh','/usr/bin/perl','/usr/bin/grep','/usr/bin/egrep','/usr/bin/awk',
             '/usr/bin/sort','/usr/bin/git','/usr/bin/date','/usr/bin/whoami','/usr/bin/plistutil']
    tool_modes = {}
    for path in tools:
        pin(path)
        p = Path(path)
        if not p.is_file() or not p.stat().st_mode & 0o111:
            raise ValueError('Host executable absent: '+path)
        tool_modes[path] = dict(resolved_path=str(p.resolve()),mode=p.stat().st_mode & 0o777)
    pin('/usr/lib64/libplist-2.0.so.4.6.0')
    for name in ['serializer-types.xml','malformed.xml','truncated-binary.plist']:
        pin(BASE/name)
    config = OUT/'kernel/config'
    kernel = OUT/'kernel'
    symbols = inventory['pending_metadata']['symbolsets.plist']['symbols']
    if symbols != ['BSDKernel','IOKit','Libkern','Mach','MACFramework','Unsupported','Private','Kasan','Kcov']:
        raise ValueError('Unexpected native symbol-set order')
    exports = inventory['pending_metadata']['all-kpi.exp']['inputs']
    expected = [str(source/'config'/(n+s+'.exports')) for n in symbols[:7] for s in ['', '.arm64']]
    expected += [str(source/'config'/n) for n in ['Unused.exports','Kasan_disabled.exports','Kcov_disabled.exports']]
    if exports != expected or inventory['pending_metadata']['all-alias.exp']['inputs'] != expected:
        raise ValueError('Native17 selection differs')
    if list((source/'config').glob('*.arm64.iPhoneOS.exports')):
        raise ValueError('New platform exports require independent selection review')
    env = ['/usr/bin/env','-i','PATH=/usr/bin:/bin','LC_ALL=C','LANG=C','PYTHONUTF8=1','PYTHONNOUSERSITE=1',
        'PYTHONDONTWRITEBYTECODE=1','GIT_NO_LAZY_FETCH=1','GIT_OPTIONAL_LOCKS=0','GIT_TERMINAL_PROMPT=0',
        'HOME='+str(OUT/'home'),'TMPDIR='+str(OUT/'tmp')]
    commands = []; setup = []; validations = []; products = []
    def command(name,phase,argv,outputs,accept=(0,)):
        commands.append(dict(id=name,phase=phase,argv=env+list(map(str,argv)),cwd=str(OUT),
            outputs=list(map(str,outputs)),accepted_exit_codes=list(accept),timeout_seconds=20))
        products.extend(map(str,outputs))
    for kind,filename in [('exports','all-kpi.exp'),('aliases','all-alias.exp')]:
        command(kind,'exports',['/bin/sh',source/'config'/('generate_linker_'+kind+'.sh'),kernel/filename,*exports],[kernel/filename])
    symplists = []
    for n,template in zip(symbols,inventory['pending_metadata']['symbolsets.plist']['Info_plist_templates']):
        info = config/'System.kext/PlugIns'/(n+'.kext')/'Info.plist'
        setup.append(dict(source=template,destination=str(info),sha256=pins[template]))
        command('newvers-'+n,'xml',['SRCROOT='+str(source),'OBJROOT='+str(kernel),'TARGET='+str(config),
            'CURRENT_KERNEL_CONFIG_LC=development','KERNEL_BUILD_DATE='+version['build_date'],
            'KERNEL_BUILD_OBJROOT='+version['build_object_root'],'/usr/bin/perl',source/'config/newvers.pl',info],[info])
        component = [source/'config'/(n+s+'.exports') for s in ['', '.arm64']] if n in symbols[:7] else [source/'config'/(n+'_disabled.exports')]
        output = config/(n+'.symbolset.plist'); symplists.append(output)
        command('symbolset-'+n,'xml',['/bin/sh',source/'config/generate_symbolset_plist.sh',output,info,*component],[output])
    combined = kernel/'symbolsets.xml.plist'
    command('combine','xml',['/bin/sh',source/'config/generate_combined_symbolsets_plist.sh',combined,*symplists],[combined])
    def convert(name,src,dst,fmt,accept=(0,)):
        command(name,'serializer',['/usr/bin/plistutil','-i',src,'-o',dst,'-f',fmt],[dst] if accept==(0,) else [],accept)
    controls = OUT/'serializer-controls'; validation = OUT/'validation'
    convert('control-to-binary',BASE/'serializer-types.xml',controls/'types.bin','bin')
    convert('control-to-xml',controls/'types.bin',controls/'types.xml','xml')
    validations.append([str(BASE/'serializer-types.xml'),str(controls/'types.bin'),str(controls/'types.xml')])
    for name,src,fmt in [('bad-xml',BASE/'malformed.xml','bin'),('truncated-binary',BASE/'truncated-binary.plist','xml'),('unknown-format',BASE/'serializer-types.xml','not-a-format')]:
        convert('reject-'+name,src,controls/(name+'.rejected'),fmt,(1,2))
    for n,src in zip(symbols,symplists):
        dst=validation/(n+'.xml');convert('lint-'+n,src,dst,'xml'); validations.append([str(src),str(dst)])
    convert('combined-to-binary',combined,kernel/'symbolsets.plist','bin')
    convert('combined-to-xml',kernel/'symbolsets.plist',validation/'symbolsets.roundtrip.xml','xml')
    validations.append(list(map(str,[combined,kernel/'symbolsets.plist',validation/'symbolsets.roundtrip.xml'])))
    if len(commands)!=37 or len(set(products))!=len(products):raise ValueError('Unexpected recipe/count')
    return dict(schema='e1s-development-link-metadata-plan-v1',kind='source-review',task='STR-032',owner=OWNER,
        source_root=str(source),actual_output=str(OUT),input_sha256=pins,tool_identity=tool_modes,helpers=helpers,
        selected_exports=exports,symbol_order=symbols,commands=commands,setup=setup,expected_products=products,
        typed_tree_equalities=validations,version_context=dict(master_version=version['master_version'],
            build_date=version['build_date'],build_object_root=version['build_object_root']),
        phases=dict(exports=2,text=21,full=37),limits=dict(jobs=1,owned_rss_bytes=256*1024**2,child_seconds=20,whole_seconds=180,child_address_space_bytes=1024**3),
        serializer=dict(candidate='libplist-2.6.0-5.fc43.x86_64 /usr/bin/plistutil',native_plutil_available=False,
            native_plutil_oracle_qualified=False,portable_host_mapping_qualified=False,
            mapping={'plutil -lint -s FILE':'plistutil -i FILE -o OWNED_XML -f xml; compare typed tree',
                'plutil -convert binary1 -s FILE':'plistutil -i RAW_XML -o FILE -f bin; binary header and typed-tree roundtrip'},
            warning='Native -s means silent; plistutil -s means sort. Never forward it.'),
        obligations=dict(full_37_exports_retained=True,check_all_exports='separate future linked-image audit; config/Makefile120-145 unchanged',
            DEVELOPMENT_exported_symbols_list=False,actual_target_generation=False,SDK_or_IPC_or_provider_ABI_qualified=False))

if __name__ == '__main__':
    plan=prepare()
    target=WT/'artifacts/e1s-development-link-metadata/prepare-1/execution-plan.json'
    with target.open('x') as stream:stream.write(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(dict(plan=str(target),sha256=sha(target),commands=len(plan['commands']),inputs=len(plan['input_sha256']))))
