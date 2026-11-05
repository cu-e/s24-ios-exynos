#!/usr/bin/env python3
"""Named primary public vector fetch into a fresh ignored artifact directory."""
import argparse,datetime,hashlib,json,urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False)
meta=json.loads((HERE/'testdata/vectors.json').read_text())
url=meta['primary_url'];data=urllib.request.urlopen(url,timeout=30).read()
sha=hashlib.sha256(data).hexdigest()
if sha!=meta['archive_sha256']:raise ValueError('Primary archive changed; refuse silent vector updates')
(a.out/'XTSTestVectors.zip').write_bytes(data)
(a.out/'fetch.json').write_text(json.dumps({'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'url':url,'sha256':sha,'bytes':len(data),'outcome':'pass'},indent=2)+'\n')
print(a.out/'XTSTestVectors.zip')
