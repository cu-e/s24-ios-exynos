#!/usr/bin/env python3
"""Read-only audit of root83 retained files. Never run C, decoder or compiler."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
MAIN = ROOT.parent.parent
PREP = ROOT/'artifacts/e1s-boot-log-host/prepare-001'
MEASURE = ROOT/'artifacts/e1s-boot-log-host/measure-root83-001'
OUT = ROOT/'artifacts/e1s-boot-log-host/audit-001'
OUT.mkdir(exist_ok=False)
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def dump(p, value): p.write_text(json.dumps(value, indent=2)+'\n')
assert sha(MEASURE/'evidence.json') == '7b708be54d9c4420e3f4221762da61b60647454807cf4e27accd750f3eccefd7'
assert sha(PREP/'plan.json') == 'dce2be32ee775886cc3813c0e4174d5e00d6498736898dcf69664fb209073b14'
raw = json.loads((MEASURE/'evidence.json').read_text())
plan = json.loads((PREP/'plan.json').read_text())
assert raw['outcome'] == 'pass' and raw['expected_negative_cases_confirmed'] == 2
assert raw['owner'] == 'codex-e1s-boot-log-host-20261106-sr20'
assert raw['task'] == 'STR-020' and raw['experiment'] == 'STR020HOST-001'
assert raw['owned_survivors'] == [] and len(raw['seen_owned_sessions']) == 5
assert all(s['owned_processes'] == [] for s in raw['terminal_sessions'])
assert len(raw['commands']) == len(plan['commands']) == 5
max_combined = 0
rows = []
for declared, retained in zip(plan['commands'], raw['commands']):
    command = retained['raw_command']; name = declared['id']
    assert retained['id'] == name and command['argv'] == declared['argv']
    assert command['cwd'] == declared['cwd']
    assert command['exit_code'] == declared['expected_exit_code']
    assert command['after']['owned_processes'] == [] and not command['events']
    assert json.loads((MEASURE/(name+'.json')).read_text()) == command
    assert sha(MEASURE/(name+'.log')) == retained['combined_log_sha256']
    assert all(retained['environment'][k] == v for k,v in declared['env'].items())
    if declared['expected_exit_code'] == 1:
        assert command['outcome'] == 'fail' and retained['raw_failure_not_relabelled']
        assert retained['assessment'] == 'expected-negative-confirmed'
        log = (MEASURE/(name+'.log')).read_text()
        assert all(s in log for s in declared['required_combined_log_substrings'])
    else:
        assert command['outcome'] == 'pass' and retained['assessment'] == 'normal-command-pass'
    samples = [json.loads(line) for line in (MEASURE/(name+'.samples.jsonl')).read_text().splitlines()]
    max_combined = max([max_combined] + [s.get('combined_owned_rss_bytes', 0) for s in samples])
    rows.append({'id':name, 'raw_exit':command['exit_code'], 'raw_outcome':command['outcome'],
                 'assessment':retained['assessment'], 'session':command['owned_session'],
                 'sample_count':len(samples), 'log_sha256':sha(MEASURE/(name+'.log'))})
assert max_combined <= 256*1024**2
for p,h in plan['input_sha256'].items(): assert sha(p) == h, p
for binding in plan['runner_bindings'].values(): assert sha(binding['path']) == binding['sha256']
for p,h in raw['output_sha256'].items(): assert sha(p) == h, p

# Import only the accepted pure MD parser API, not any execution path.
parser = MAIN/'tools/build/avf_kernel_objects.py'
assert sha(parser) == '9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755'
spec = importlib.util.spec_from_file_location('actual_host_md_parser', parser)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
deps = module.dependencies(PREP/'host.d', PREP, PREP/'host-controls')
md = re.sub(r'\\\r?\n', '', (PREP/'host.d').read_text()).splitlines()[0]
requested = module.make_tokens(md.split(':', 1)[1])
assert len(deps) == len(set(str(Path(p).resolve()) for p in requested))
actual_inputs=[]
for declared in requested:
    path=Path(declared); canonical=path.resolve()
    assert canonical.is_file()
    stat=canonical.stat()
    actual_inputs.append({'MD_requested_path':declared,'canonical_path':str(canonical),
                          'sha256':sha(canonical),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns})
assert {str(PREP/n) for n in ['host-controls.c','actual-loader-log.inc','extent-cases.inc']} <= set(deps)
dump(OUT/'actual-md-inputs.json', {'MD_file':str(PREP/'host.d'),'MD_sha256':sha(PREP/'host.d'),
     'parser_path':str(parser),'parser_sha256':sha(parser),'requested_count':len(requested),
     'unique_canonical_count':len(deps),'inputs':actual_inputs,
     'observation':'Actual compiler MD plus post-run file hashes; no compiler replay or invented SDK. Host system headers were not prebound before original compile.'})

loader=(PREP/'source/shim/e1s-xnu/loader.c').read_text()
parts=[]; sections={}
for name,first,last in [('abi','#define BOOT_LINE_LENGTH','uint64_t boot_args_pa;'),
 ('actual_record','/* CPU-local loader diagnostic record.','static uint64_t fb_base;'),
 ('actual_logging','static void log_init(','static void clean('),
 ('actual_extent','/* Preserve the existing payload reserve,','static int\nchoose_window(')]:
    start=loader.index(first); end=loader.index(last,start); text=loader[start:end]
    digest=hashlib.sha256(text.encode()).hexdigest()
    assert digest == plan['actual_source_ranges'][name]['sha256']
    parts.append(text); sections[name]=digest
macros=''.join(line+'\n' for line in loader.splitlines() if line.startswith(
    ('#define LOG_MAGIC\t','#define LOG_HEADER\t','#define LOG_MAX\t')))
assert (PREP/'actual-loader-log.inc').read_text() == macros+'\n'+'\n'.join(parts)
vectors=json.loads((ROOT/'fixtures/public/e1s-boot-log-host/extent-vectors.json').read_text())['vectors']
assert len(vectors) == 9
vectors_checked=[]
maximum=(1<<64)-1; reserve=32<<20
for v in vectors:
    image=int(v['image'],16); end=int(v['actual_linker_end'],16); payload=int(v['selected_payload'],16)
    old_size=(payload-image+reserve) if payload>image else 0x40000+reserve
    calculated=max(old_size,end-image)
    valid=end>=image and old_size<=maximum and image+calculated<=maximum
    assert v['expected_success'] == valid
    assert v['expected_reserved_size'] == (hex(calculated) if valid else None)
    vectors_checked.append({'id':v['id'],'success':valid,'reserved_size':hex(calculated) if valid else None})
lines=['struct extent_case { uintptr_t image, end, payload; int valid; uint64_t size; };',
       'static const struct extent_case extent_cases[] = {']
for v in vectors:
    fields=['UINT64_C('+v[k]+')' for k in ['image','actual_linker_end','selected_payload']]
    fields += [str(int(v['expected_success'])),'UINT64_C('+(v['expected_reserved_size'] or '0')+')']
    lines.append('    { '+', '.join(fields)+' },')
lines.append('};')
assert (PREP/'extent-cases.inc').read_text() == '\n'.join(lines)+'\n'
decoder=json.loads((PREP/'decoder-evidence.json').read_text())
assert decoder == {'outcome':'pass','kind':'host-test','actual_decoder_records':2,
    'first_offset':7,'second_offset':65310,'text_lengths':[65280,27],'kernel_marker':None,
    'with_explicit_decoy_candidates':3,'decoy_offset':130610,'truncated_header_ignored':True,
    'magic_extraction_is_not_authentication':True}
assert 'actual host assertions=65356 extent_vectors=9 record_size=65300' in (MEASURE/'actual-host-controls.log').read_text()
result={'kind':'source-review','origin':'local-host','outcome':'pass',
    'recorded_at':datetime.now(timezone.utc).isoformat(),'commands_replayed':0,
    'raw_evidence_sha256':sha(MEASURE/'evidence.json'),'five_command_validation':rows,
    'actual_MD_requested_inputs':len(requested),'actual_MD_unique_canonical_inputs':len(deps),
    'MD_input_manifest_sha256':sha(OUT/'actual-md-inputs.json'),'four_actual_sections':sections,
    'independent_extent_vectors':vectors_checked,'retained_decoder_result':decoder,
    'sampled_peak_combined_owned_rss_bytes':max_combined,'zero_live_owned_survivors':True,
    'runtime_or_decoder_replayed':False,
    'limitations':['Read-only post-run MD/source/artifact audit; no compiler/C/decoder replay.',
       'MD covers actual preprocessor inputs; post-run hashes are not a precompile atomic snapshot.',
       'Host header/layout and sanitizer behavior do not qualify native target layout, mapping, persistence or kernel0011/0012.']}
dump(OUT/'validation.json',result)
print(json.dumps({'read_only_audit':'pass','actual_MD_inputs':len(deps),'sections':len(sections),
    'extent_vectors':len(vectors),'actual_assertions_from_retained_log':65356,
    'sampled_combined_rss_bytes':max_combined,'host_commands_replayed':0,
    'validation_sha256':sha(OUT/'validation.json')}))
