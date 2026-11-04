#!/usr/bin/env python3
"""Read-only prerequisite check. Never downloads an Apple SDK or runs a kernel build."""
import argparse
import json
import os
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk',type=Path,default=os.environ.get('S24_IOS_SDK'))
    p.add_argument('--dependency-tools',type=Path,default=os.environ.get('S24_XNU_DEPENDENCY_TOOLS'))
    args=p.parse_args();missing=[];observations={}
    if args.sdk is None:missing.append('Explicit local iPhoneOS16.5 SDK path (--sdk or S24_IOS_SDK)')
    else:
        settings=args.sdk/'SDKSettings.json'
        if not settings.is_file():missing.append('SDKSettings.json in supplied SDK')
        else:
            data=json.loads(settings.read_text());version=str(data.get('Version',''))
            observations['sdk_version']=version
            if version!='16.5':missing.append('Selected SDK must match iPhoneOS16.5; do not silently change ABI')
        for relative in ['usr/include','System/Library/Frameworks']:
            if not (args.sdk/relative).is_dir():missing.append('SDK directory '+relative)
    if args.dependency_tools is None:missing.append('Explicit pinned HakiOS XNU dependency/build tool directory')
    elif not (args.dependency_tools/'xnu-build.sh').is_file():missing.append('Reviewed xnu-build.sh in dependency tool directory')
    print(json.dumps({'outcome':'blocked' if missing else 'prerequisites-present','missing':missing,'observations':observations,'kernel_compiled':False,'limitation':'Presence checks alone do not verify the full dependency ABI, build or hardware boot'},indent=2))
    return 2 if missing else 0


if __name__=='__main__':raise SystemExit(main())
