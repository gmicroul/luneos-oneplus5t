#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--proxy', help='optional HTTP proxy URL')
args = parser.parse_args()
base = Path(__file__).resolve().parent
parts = base / 'parts'
parts.mkdir(exist_ok=True)
manifest = json.loads((base / 'parts.json').read_text())
handlers = []
if args.proxy:
    handlers.append(urllib.request.ProxyHandler({'http': args.proxy, 'https': args.proxy}))
opener = urllib.request.build_opener(*handlers)
url = 'https://github.com/gmicroul/luneos-oneplus5t/releases/download/v0.1-current-fixes/'
for item in manifest['parts']:
    target = parts / item['name']
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != item['sha256']:
        print('DOWNLOAD', item['name'], flush=True)
        with opener.open(url + item['name'], timeout=1800) as response, target.open('wb') as out:
            while True:
                block = response.read(4 * 1024 * 1024)
                if not block:
                    break
                out.write(block)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == item['sha256'], item['name']
output = base / 'userdata.sparse.img'
with output.open('wb') as out:
    for item in manifest['parts']:
        with (parts / item['name']).open('rb') as source:
            while True:
                block = source.read(4 * 1024 * 1024)
                if not block:
                    break
                out.write(block)
print(output, output.stat().st_size)
print(hashlib.sha256(output.read_bytes()).hexdigest())
