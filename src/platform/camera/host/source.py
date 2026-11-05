"""Read-only exact-pin camera text input acquisition; no shared Git writes."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import re

REVISION = '417484173abc2c4fa93e738ea82ad9f2e84911b1'
PREFIX = 'drivers/media/platform/exynos/camera/'
FILES = [
    PREFIX+'Makefile', PREFIX+'Kconfig', PREFIX+'pablo-video.c',
    PREFIX+'include/is-video.h', PREFIX+'include/pablo-framemgr.h',
    PREFIX+'include/is-metadata.h', PREFIX+'include/is-common-config.h',
    PREFIX+'hardware/api/is-hw-common-dma.c',
    PREFIX+'hardware/include/is-hw-common-dma.h',
    PREFIX+'vendor/mcd/esx/s5e9945-e1s_camera.dtsi',
    PREFIX+'ischain/is-v12_0_0/is-config.h',
    PREFIX+'include/v12_0_0/is-param.h',
    PREFIX+'v4l2/format.c', PREFIX+'v4l2/video.c',
    PREFIX+'include/pablo-video.h',
    PREFIX+'include/is-type.h', PREFIX+'include/pablo-mem.h',
    PREFIX+'include/is-common-enum.h',
    PREFIX+'include/v12_0_0/is-metadata-vendor.h',
    PREFIX+'v4l2/vb2.c', PREFIX+'v4l2/ioctl.c',
    PREFIX+'is-device-csi_v4.c',
    PREFIX+'ischain/is-v12_0_0/is-subdev-mcsp.c',
    'arch/arm64/configs/e1s_defconfig',
    'arch/arm64/configs/s5e9945-base_defconfig',
    'include/uapi/linux/videodev2.h',
]

def acquire(lab, output):
    output.mkdir(parents=True, exist_ok=False)
    records = []
    env = {**os.environ, 'GIT_NO_LAZY_FETCH':'1', 'GIT_OPTIONAL_LOCKS':'0'}
    for index, name in enumerate(FILES):
        command = ['git','-C',str(lab/'references/s24-linux'),'show',REVISION+':'+name]
        result = subprocess.run(command,env=env,capture_output=True,timeout=20)
        record = dict(source=name,revision=REVISION,argv=command,git_exit=result.returncode,
                      recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))
        (output/(str(index)+'.git.stderr')).write_bytes(result.stderr)
        if result.returncode:
            record['url']='https://raw.githubusercontent.com/dx4m/android-kernel-samsung-e1s/'+REVISION+'/'+name
            record['fetch_argv']=['curl','--fail','--silent','--show-error','--location','--max-time','25',
                '--max-filesize','4194304','--dump-header',str(output/(str(index)+'.HTTP.headers')),record['url']]
            fetched=subprocess.run(record['fetch_argv'],capture_output=True,timeout=30)
            record['fetch_exit']=fetched.returncode
            (output/(str(index)+'.curl.stderr')).write_bytes(fetched.stderr)
            headers=(output/(str(index)+'.HTTP.headers')).read_text()
            statuses=re.findall(r'^HTTP/\S+\s+(\d+)',headers,re.M)
            record['HTTP_status']=int(statuses[-1]) if statuses else None
            if fetched.returncode:
                record['fetch_error']=fetched.stderr.decode(errors='replace');records.append(record)
                (output/'provenance.json').write_text(json.dumps(records,indent=2)+'\n')
                raise RuntimeError('Exact-pin curl acquisition failed')
            data=fetched.stdout
            if len(data)>4*1024*1024:raise ValueError('Bounded exact-pin text fetch exceeded4MiB')
        else:data=result.stdout
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        record['sha256']=hashlib.sha256(data).hexdigest();record['bytes']=len(data)
        records.append(record)
        (output/'provenance.json').write_text(json.dumps(records,indent=2)+'\n')
    return records

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(acquire(args.lab_root,args.output),indent=2))
