from pathlib import Path
import importlib.util,sys
D=Path('docs/integration/platform/wave29-products-20261106').resolve();p=D/'reader.py';s=importlib.util.spec_from_file_location('cn_actual_wave_reader',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
for task in ['vm-016','vm-017','vm-041']:
 m.COUNT=0;m.NAMES=[];m.OBS={};m.START=0
 sys.argv=[str(p),'--config',str(D/task/'config.json'),'--output',str(Path('artifacts/platform-integration')/('wave29-'+task.replace('-','')+'-review1'))]
 m.main()
