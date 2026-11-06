"""Describe the exact E1S source preparation; no compiler or hardware access."""
import ast
import hashlib
import json
import re


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pinned_files(base, expected):
    for name, digest in expected.items():
        path = base / name
        if path.resolve() != base.resolve() / name or sha(path) != digest:
            raise ValueError('E1S profile input differs: ' + name)


def integer_define(text, name):
    values = re.findall(r'^#define\s+' + re.escape(name) + r'\s+(\d+)\s*$', text, re.M)
    if len(values) != 1:
        raise ValueError('Ambiguous/missing E1S definition: ' + name)
    return int(values[0])


def source_profile(project, donor, prepared, provenance, patches):
    """Called only after prepare_xnu has applied its complete selected series."""
    pin_path = project / 'fixtures/public/e1s-profile/pins.json'
    pins = json.loads(pin_path.read_text())
    revisions = {p['id']: p['revision'] for p in provenance}
    if revisions != pins['source_revisions']:
        raise ValueError('E1S source revision selection differs')
    if patches != pins['patches']:
        raise ValueError('E1S ordered patch provenance differs')
    for base, key in [(project, 'project_sha256'), (donor, 'donor_sha256'),
                      (prepared, 'prepared_sha256')]:
        pinned_files(base, pins[key])
    compatible = pins['compatible_loader_evidence']
    if sha(project / compatible['evidence_path']) != compatible['evidence_sha256']:
        raise ValueError('Compatible loader evidence differs')
    board = (prepared / 'pexpert/pexpert/arm64/board_config.h').read_text()
    blocks = re.findall(r'#ifdef ARM64_BOARD_CONFIG_E1S\n(.*?)#endif[^\n]*', board, re.S)
    if len(blocks) != 1 or '#include <pexpert/arm64/E1S.h>' not in blocks[0]:
        raise ValueError('E1S board selection/header is missing')
    topology = {n: integer_define(blocks[0], n) for n in
                ['MAX_CPUS', 'MAX_CPU_CLUSTERS', 'MAX_CPU_CLUSTER_PHY_ID']}
    if topology != pins['required_topology']:
        raise ValueError('E1S source topology differs from the reviewed capacity')
    header = (prepared / 'pexpert/pexpert/arm64/E1S.h').read_text()
    for name in ['E1S', 'E1S_BRINGUP', 'GENERIC_GIC_V3_IRQ', 'GENERIC_PSCI_SMP']:
        if integer_define(header, name) != 1:
            raise ValueError('E1S board capability selection differs: ' + name)
    # Read literal values without importing/executing the donor ADT generator.
    adt = ast.parse((donor / 'tools/e1s/xnu/mkadt.py').read_text())
    literals = {}
    for node in adt.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name):
                literals[target.id] = value
            elif isinstance(target, ast.Tuple) and isinstance(value, tuple):
                literals.update({n.id: v for n, v in zip(target.elts, value)
                                 if isinstance(n, ast.Name)})
    packer = ast.parse((donor / 'tools/e1s/xnu/mkpayload.py').read_text())
    cmdlines = []
    for node in ast.walk(packer):
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            if node.args[0].value == '--cmdline':
                cmdlines.extend(ast.literal_eval(k.value) for k in node.keywords
                                if k.arg == 'default')
    if len(cmdlines) != 1 or cmdlines[0].split().count('cpus=1') != 1:
        raise ValueError('Explicit one-CPU donor bring-up selection is missing')
    cpu_tables = [ast.literal_eval(n.value) for n in ast.walk(adt)
                  if isinstance(n, ast.Assign) and len(n.targets) == 1
                  and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'cpu_table']
    full = [table for table in cpu_tables if len(table) == topology['MAX_CPUS']]
    if len(full) != 1 or len({row[1] for row in full[0]}) != topology['MAX_CPU_CLUSTERS']:
        raise ValueError('Donor ADT topology and E1S header capacity disagree')
    gic = (donor / 'shim/e1s-xnu/gic.c').read_text()
    for c_name, py_name in [('GICD_BASE', 'GICD'), ('GICR_BASE', 'GICR'),
                            ('GICR_SIZE', 'GICR_SIZE')]:
        values = re.findall(r'^#define\s+' + c_name + r'\s+(0x[0-9a-fA-F]+)UL\s*$', gic, re.M)
        if len(values) != 1 or int(values[0], 16) != literals[py_name]:
            raise ValueError('Loader/ADT GIC declarations disagree: ' + c_name)
    return {
        'schema': 'e1s-source-profile-v1', 'machine': 'E1S', 'arch': 'arm64',
        'board_macro': 'ARM64_BOARD_CONFIG_E1S', 'source_capacity': topology,
        'bringup': {'payload_default_cmdline': cmdlines[0], 'requested_cpus': 1,
                    'actual_boot_cpus': None, 'actual_mpidrs': None,
                    'smp_qualified': False, 'donor_smp_table': full[0],
                    'donor_smp_table_is_device_observation': False},
        'timer': {'source_timebase_hz': literals['TIMEBASE'],
                  'source_virtual_timer_intid': literals['VTIMER_INTID'],
                  'measured_cntfrq_hz': None},
        'interrupts': {'source_controller': 'arm,gic-v3',
                       'source_gicd_base': literals['GICD'],
                       'source_gicd_size': literals['GICD_SIZE'],
                       'source_gicr_base': literals['GICR'],
                       'source_gicr_size': literals['GICR_SIZE'],
                       'hardware_delivery_qualified': False},
        'memory': {'physical_window': None, 'complete_live_fdt': None,
                   'firmware_carveouts_qualified': False,
                   'selection': 'Validated live FDT with nonempty exclusions; no payload fallback',
                   'loader_patch_sha256': pins['project_sha256'][
                       'patches/e1s-boot/0001-loader-memory-validation.patch']},
        'configuration': None, 'required_future_inputs': [
            'Explicit kernel configuration and coherent E1S generated headers/recipes',
            'E1S-qualified dependency archives; guest BCM2837 products are not substitutes',
            'Configuration-specific exports:37 selected RELEASE ABI providers remain unresolved; DEVELOPMENT body link is separate',
            'Live DTB/backing/carve-outs, boot CPU state and safe recovery before hardware use'],
        'source_revisions': revisions, 'patches': patches,
        'pins_sha256': sha(pin_path), 'prepared_sha256': pins['prepared_sha256'],
        'donor_sha256': pins['donor_sha256'], 'project_sha256': pins['project_sha256'],
        'compatible_loader_revision': pins['compatible_loader_revision'],
        'compatible_loader_evidence': compatible,
        'later_uart_watchdog_patches_selected': False,
        'kernel_compiled': False, 'hardware_executed': False,
    }
