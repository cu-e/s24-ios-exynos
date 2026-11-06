#!/usr/bin/env python3
"""Independent actual native header inspection; no producer tool execution."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import stat
import time

WT = Path(__file__).resolve().parents[4]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
OWNER = MAIN / 'worktrees/str-018-e1s-development-providers-20261106'
CORE = WT / 'docs/integration/platform/native93-libkern-review/read-products.py'
assert hashlib.sha256(CORE.read_bytes()).hexdigest() == '9d7a7e31855d3f1db649685f8054a84fe6972182bf8b521599d59152bb4f381e'
spec = importlib.util.spec_from_file_location('accepted_cn_readonly_hashes', CORE)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
req, data, pin, load = core.req, core.data, core.pin, core.load

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    products, signatures, invocations, commands = [], [], [], []
    outcome, error = 'fail', None
    try:
        admission = []
        for n in range(3):
            available = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))) * 1024
            req(available >= 4 * 1024**3, 'Read-only4GiB admission')
            admission.append(available)
            if n < 2:
                time.sleep(.25)
        descriptor = load(OWNER / 'fixtures/public/e1s-development-providers/generated-headers.json', '07724b361a15671a7a31d5f14daf11b4d892dc732d0f181cfd780c7223c97fbe')
        raw = load(descriptor['raw_evidence']['path'], descriptor['raw_evidence']['sha256'])
        root = load(descriptor['root_evidence']['path'], descriptor['root_evidence']['sha256'])
        plan = load(descriptor['source_plan']['path'], descriptor['source_plan']['sha256'])
        provider = load(plan['provider_plan']['path'], plan['provider_plan']['sha256'])
        verification = load(descriptor['manifest']['path'], descriptor['manifest']['sha256'])
        req(root['outcome'] == 'pass' and root['released'] is True and root['owned_survivors'] == [] and root['reservations'] == {'STR-018': 'complete'}, 'Exact released root98 authority')
        control = root['commands'][0]
        argv = control['argv']
        arg = lambda key: argv[argv.index(key) + 1]
        req(control['task'] == 'STR-018' and control['outcome'] == 'pass' and control['exit_code'] == 0 and control['evidence_sha256'] == descriptor['raw_evidence']['sha256'], 'Actual root header caller terminal PASS')
        req(arg('--source-plan') == descriptor['source_plan']['path'] and arg('--source-plan-sha256') == descriptor['source_plan']['sha256'], 'Exact admitted header plan')
        pin(arg('--approval'), arg('--approval-sha256'))
        pin(OWNER / 'fixtures/public/e1s-development-providers/header_only.py', descriptor['caller_sha256'])
        req(plan['executor_sha256'] == descriptor['caller_sha256'] == root['caller_sha256'] == '97d201ce8f6cfee9ca2c222fc11a8fe584eaa08155dbcf8e1c9633ae6e41bad2', 'Exact original header caller')
        req(raw['source_plan_sha256'] == descriptor['source_plan']['sha256'] and raw['outcome'] == 'pass' and raw['own_reservation_released'] is True and not raw.get('budget_release_error'), 'Raw004 normal own cleanup PASS')
        req(raw['compiler_started'] is raw['archive_executed'] is raw['layout_executed'] is False, 'Header-only result')
        req(plan['max_jobs'] == 1 and plan['max_owned_rss_bytes'] == 512 * 1024**2 and plan['command_count'] == 31 and len(provider['commands']) == 37, 'Exact phase and resource bounds')
        for path, digest in {**provider['input_sha256'], **plan['helper_sha256']}.items():
            pin(path, digest)
        req(len(provider['input_sha256']) == 665, 'Exact665 current input bindings')
        source_context = load(provider['source_context']['path'], provider['source_context']['sha256'])
        source_root = Path(source_context['source_root'])
        source_manifest = load(source_context['source_manifest'], source_context['source_manifest_sha256'])
        definitions = data(source_root / 'makedefs/MakeInc.def', source_manifest['makedefs/MakeInc.def']).decode()
        make_cmd = data(source_root / 'makedefs/MakeInc.cmd', source_manifest['makedefs/MakeInc.cmd']).decode()
        assignment = lambda name: re.search(r'^' + re.escape(name) + r'\s*:?=\s*(.+)$', make_cmd, re.M).group(1)
        embedded = shlex.split(assignment('SUPPORTED_EMBEDDED_PLATFORMS'))
        simulator = shlex.split(assignment('SUPPORTED_SIMULATOR_PLATFORMS'))
        platforms = shlex.split(assignment('SUPPORTED_PLATFORMS').replace('$(SUPPORTED_SIMULATOR_PLATFORMS)', ' '.join(simulator)).replace('$(SUPPORTED_EMBEDDED_PLATFORMS)', ' '.join(embedded)))
        platform_flags = [('-D' if p == 'iPhoneOS' else '-U') + 'XNU_PLATFORM_' + p for p in platforms]
        req(len(platform_flags) == 13 and platform_flags.count('-DXNU_PLATFORM_iPhoneOS') == 1, 'Genuine13 native platform selectors')
        private_common = re.findall(r'^XNU_PRIVATE_UNIFDEF\s*\+=\s*(\S+)\s*$', definitions, re.M)
        req(len(private_common) == 7, 'Genuine source-defined private prefix')
        tool = provider['commands'][30]['argv'][0]
        expected_flags = {}
        for visibility, variable in [('public', 'KINCFRAME_UNIFDEF'), ('private', 'KPINCFRAME_UNIFDEF')]:
            line = re.search(r'^' + variable + r'\s*=\s*(.+)$', definitions, re.M).group(1)
            expanded = line.replace('$(PLATFORM_UNIFDEF)', ' '.join(platform_flags)).replace('$(XNU_PRIVATE_UNIFDEF)', ' '.join(private_common)).replace('$(SEED_DEFINES)', '')
            req('$(' not in expanded, 'Completely source-derived native filter argv')
            expected_flags[visibility] = [tool] + shlex.split(expanded)
            req(len(expected_flags[visibility]) == 27, 'Exactly13 platform plus13 privacy flags')
        out = Path(plan['actual_output'])
        req(out == Path(control['out']), 'Exact fresh004 output')
        rows = provider['header_expected_rows']
        req(len(rows) == len(raw['headers']) == 315 and len({r['output_template'] for r in rows}) == 315, 'Exact315 unique selected products')
        mig = load(provider['MIG']['path'], provider['MIG']['sha256'])
        for row, observed in zip(rows, raw['headers']):
            req(time.monotonic() - started < 120, 'Finite read-only header review')
            core.rss()
            path = Path(row['output_template'])
            req(path.is_relative_to(out) and observed['path'] == str(path) and observed['source'] == row['source'] and observed['logical_header'] == row['logical_header'] and observed['visibility'] == row['visibility'] and observed['native_kind'] == row['native_kind'], 'Exact installed typed header selection')
            req(path.stat().st_size == observed['bytes'] > 0 and stat.S_IMODE(path.stat().st_mode) == 0o444 and observed['mode'] == '0444' and observed['status'] == 'actual-installed', 'Actual nonempty0444 ordinary header')
            pin(path, observed['sha256'])
            origin = row['source']
            pin(origin['path'], origin['sha256'])
            if origin['kind'] == 'fresh-prepared-source':
                req(source_manifest[origin['relative_to_source']] == origin['sha256'] and Path(origin['path']) == source_root / origin['relative_to_source'], 'Raw source header exact STR014 manifest authority')
            else:
                product = mig['products'][origin['logical_product']]
                req(origin['kind'] == 'actual-qualified-composite-MIG-export' and product['mode'] == origin['mode'] == 'export' and product['path'] == origin['path'] and product['sha256'] == origin['sha256'], 'Actual export-mode MIG producer, never raw fallback')
                pin(origin['staged_native_prerequisite'], origin['sha256'])
            declaration = source_root / row['declaration']
            lines = data(declaration, source_manifest[row['declaration']]).decode().splitlines()
            if row['declaration_token_lines']:
                req(any(row['source_name'] in lines[n-1].replace('\\', '').split() for n in row['declaration_token_lines']), 'Genuine selected source declaration token')
            else:
                rule = data(source_root/'makedefs/MakeInc.rule', source_manifest['makedefs/MakeInc.rule']).decode()
                declaration_text = '\n'.join(lines)
                excluded = re.search(r'^NOT_EXPORT_HEADERS\s*=\s*(.+)$', declaration_text, re.M).group(1).split()
                req(row['declaration']=='iokit/IOKit/Makefile' and row['source_name']=='IOInterrupts.h' and row['native_kind']=='INSTALL_KF_MI_LCL_LIST' and row['visibility']=='private', 'Only exact genuine wildcard-selected header exception')
                req('ALL_HEADERS = $(notdir $(wildcard $(SOURCE)*.h))' in declaration_text and 'EXPORT_MI_LIST\t= $(filter-out $(NOT_EXPORT_HEADERS), $(ALL_HEADERS))' in declaration_text and row['source_name'] not in excluded, 'Source wildcard and filter-out include actual h basename')
                req('INSTALL_KF_MI_LCL_LIST = $(EXPORT_MI_LIST)' in rule and Path(origin['path']).parent==declaration.parent, 'Native default private-install rule consumes wildcard source list')
            products.append(observed)
        req(Counter(r['visibility'] for r in rows) == {'public': 1, 'private': 314}, 'Exact native visibility distribution')
        req(len(plan['setup_exact_copies']) == 4, 'Only four actual MIG prerequisite copies')
        for copy in plan['setup_exact_copies']:
            pin(copy['source'], copy['sha256'])
            pin(copy['destination'], copy['sha256'])
        req(len(plan['native_flag_files']) == len(raw['native_filter_flags']) == len(raw['native_filter_argv']) == 32, 'Exact32 independent native signature files')
        for guard in plan['native_flag_files']:
            path = Path(guard['path'])
            visibility = 'public' if 'kincmidir' in path.parts else 'private'
            expected = expected_flags[visibility]
            raw_bytes = data(path, raw['native_filter_flags'][str(path)])
            req(raw_bytes == (' '.join(expected) + '\n\0').encode(), 'Exact source-derived argv/newline/single-terminal-NUL signature bytes')
            req(guard['expected_argv'] == raw['native_filter_argv'][str(path)] == expected, 'Full flag vector equality without stripping or missing-token tolerance')
            signatures.append({'path': str(path), 'sha256': raw['native_filter_flags'][str(path)], 'visibility': visibility, 'argv': expected})
        req(len(raw['commands']) == 31, 'Only31 actual header commands')
        for index, (step, process) in enumerate(zip(provider['commands'][:31], raw['commands'])):
            req(step['phase'] == 'headers' and process['argv'] == step['argv'] and process['cwd'] == step['cwd'], 'Actual genuine per-group argv/cwd')
            req(process['child_started'] and process['exit_code'] == (1 if index == 30 else 0) and process['resource_qualification'] == 'pass' and not process.get('stop_reason') and process['after']['owned_processes'] == [] and process['after']['owned_tree_rss_bytes'] == 0, 'Actual accepted native exit/resource/cleanup')
            req(process['rss_budget_bytes'] == 512 * 1024**2 and process['peak_total_owned_rss_bytes'] <= 512 * 1024**2 and process['peak_project_rss_bytes'] <= 6 * 1024**3, 'Observed bounded native command RSS')
            stdout = data(out / ('header-' + str(index).zfill(3) + '.stdout.txt'), process['stdout_sha256']).decode()
            data(out / ('header-' + str(index).zfill(3) + '.stderr.txt'), process['stderr_sha256'])
            if index < 30:
                req('CURRENT_MACHINE_CONFIG=E1S' in process['argv'] and 'CURRENT_KERNEL_CONFIG=DEVELOPMENT' in process['argv'] and 'PLATFORM=iPhoneOS' in process['argv'] and 'SEED_DEFINES=' in process['argv'], 'Native E1S DEVELOPMENT filter context and genuine empty seed')
                actual_lines = [line for line in stdout.splitlines() if line.startswith(tool + ' ')]
                selected = [rows[i] for i in step['header_rows']]
                req(len(actual_lines) == len(selected), 'Exactly selected native filter invocations in actual Make stdout')
                remaining = selected.copy()
                for line in actual_lines:
                    prefix = shlex.split(line.split(' > ', 1)[0])
                    matches = [r for r in remaining if prefix[:-1] == expected_flags[r['visibility']] and (Path(step['cwd']) / prefix[-1]).resolve() == Path(r['source'].get('staged_native_prerequisite', r['source']['path'])).resolve()]
                    req(len(matches) == 1, 'Unique actual full26flags plus exact source/mode invocation')
                    selected_row = matches[0]
                    req(' ' + selected_row['literal_Make_target_template'] + ' ||' in line, 'Actual source-defined literal install target, including dot/empty segments')
                    remaining.remove(selected_row)
                    invocations.append({'command_index': index, 'visibility': selected_row['visibility'], 'installed_header': selected_row['output_template'], 'source_operand': prefix[-1], 'argv_prefix': prefix[:-1]})
                req(not remaining, 'No selected header omitted')
            commands.append({'id': step['id'], 'argv': process['argv'], 'cwd': process['cwd'], 'exit_code': process['exit_code'], 'resource_qualification': process['resource_qualification'], 'owned_after': process['after']['owned_processes']})
        req(len(invocations) == 315 and Counter(r['visibility'] for r in invocations) == {'public': 1, 'private': 314}, 'Actual315 full native flag invocation evidence')
        firehose = raw['firehose_export']
        req(firehose == descriptor['firehose_export'] and firehose['sha256'] == '14be8d31d66882894037431ec5df75a88e39e2100e8246a7df20ac2f708b6cb2' and firehose['bytes'] == 2582, 'Exact genuine Firehose actual export')
        pin(firehose['path'], firehose['sha256'])
        req(verification['headers'] == raw['headers'] and verification['header_count'] == 315 and verification['all_current_inputs_unchanged'] is True and verification['current_input_bindings'] == provider['input_sha256'], 'Owner verification matches independent current665 inputs and actual products')
        for name, identity in core.STATS.items():
            req(core.ident(Path(name).stat()) == identity, 'Input remained unchanged through review')
        outcome = 'ACCEPT_ACTUAL315_NATIVE_FILTERED_HEADERS_AND_SEPARATE_FIREHOSE_EXPORT'
    except BaseException as exc:
        error = repr(exc)
    finally:
        files = {}
        for name, value in [('products.json', products), ('signatures.json', signatures), ('actual-invocations.json', invocations), ('commands.json', commands)]:
            p = args.out / name
            p.write_text(json.dumps(value, indent=2) + '\n')
            files[str(p)] = pin(p)
        evidence = {'kind': 'host-test', 'origin': 'local-host', 'task': 'INT-003', 'owner': 'codex-integrator-platform-20261106-cn', 'recorded_at': datetime.now(timezone.utc).isoformat(), 'outcome': outcome, 'error': error, 'checks': core.N, 'actual_headers': len(products), 'signature_files': len(signatures), 'actual_filter_invocations': len(invocations), 'commands': commands, 'elapsed_seconds': time.monotonic() - started, 'reader_memory': core.rss(), 'source_sha256': pin(__file__), 'observed_physical_sha256': core.OBS, 'artifact_sha256': files, 'failed001_002_003_unqualified': True, 'compiler_archive_layout_provider_ABI_link_runtime_hardware_qualified': False, 'no_producer_tool_or_namespace_MAIN_broker_ledger_mutation': True}
        p = args.out / 'evidence.json'
        p.write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps({'outcome': outcome, 'error': error, 'headers': len(products), 'signatures': len(signatures), 'actual_invocations': len(invocations), 'evidence_sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'reader_memory': evidence['reader_memory']}))
    if error:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
