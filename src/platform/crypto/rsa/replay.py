#!/usr/bin/env python3
"""Replay primary cases, public integer oracle and deterministic C header."""
import argparse,json,zipfile
from pathlib import Path
from vectors import parse,oracle,header
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--json',type=Path,required=True);p.add_argument('--header',type=Path,required=True);args=p.parse_args()
    corpus=json.loads(args.json.read_text());z=zipfile.ZipFile(args.archive);primary=[];excluded=[]
    for name in corpus['members']:
        records,_,skip=parse(z.read(name).decode(),name);primary.extend(records);excluded.extend(skip)
    if primary!=corpus['rows'][:len(primary)] or excluded!=corpus['excluded']:raise ValueError('Primary replay differs')
    for row in corpus['rows']:
        values=[bytes.fromhex(row[k]) for k in ['n','e','signature']]
        oid=bytes.fromhex(row['oid']) if row['oid'] else None
        if oracle(*values,oid,bytes.fromhex(row['hash']))!=row['expected']:raise ValueError('Independent public integer oracle mismatch')
    first=next(row for row in corpus['rows'] if row['expected'])
    n=bytes.fromhex(first['n'])[::-1];e=bytes.fromhex(first['e'])
    if not(int.from_bytes(n,'big')&1) or oracle(n,e,bytes.fromhex(first['signature']),bytes.fromhex(first['oid']),bytes.fromhex(first['hash'])):
        raise ValueError('Independent reversed-modulus negative premise fails')
    header(corpus['rows'],args.header)
    print(json.dumps(dict(primary=len(primary),excluded=len(excluded),total=len(corpus['rows']),public_integer_oracle='pass')))
if __name__=='__main__':main()
