#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import select
import struct
import subprocess
import time

BASE = Path(__file__).resolve().parent
IDENTITY = '9da1f1b31b2ef601fa7b29c87d1300b48d8bf2a573b18649f96630e8ea2680bd'


def event(stage, **details):
    print(json.dumps({'stage': stage, 'utc': datetime.now(timezone.utc).isoformat(), **details}), flush=True)


def sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def verify_sparse(path, manifest):
    header = struct.Struct('<I4H4I')
    chunk_header = struct.Struct('<2H2I')
    encoded = hashlib.sha256()
    expanded = hashlib.sha256()
    expanded_bytes = 0
    with path.open('rb') as source:
        raw = source.read(header.size)
        encoded.update(raw)
        fields = header.unpack(raw)
        assert fields[:6] == (0xED26FF3A, 1, 0, 28, 12, 4096)
        assert fields[7] == manifest['sparse_chunks'] and fields[8] == 0
        assert fields[6] * 4096 == manifest['userdata_expanded_bytes']
        for _ in range(fields[7]):
            raw = source.read(chunk_header.size)
            encoded.update(raw)
            kind, reserved, count, total = chunk_header.unpack(raw)
            assert reserved == 0 and count > 0
            length = count * 4096
            if kind == 0xCAC1:
                assert total == length + chunk_header.size
                while length:
                    block = source.read(min(length, 4 * 1024 * 1024))
                    assert block
                    encoded.update(block)
                    expanded.update(block)
                    expanded_bytes += len(block)
                    length -= len(block)
            elif kind == 0xCAC2:
                assert total == chunk_header.size + 4
                fill = source.read(4)
                encoded.update(fill)
                assert fill == b'\0' * 4
                buffer = fill * (1024 * 1024)
                while length:
                    step = min(length, len(buffer))
                    expanded.update(buffer[:step])
                    expanded_bytes += step
                    length -= step
            else:
                raise ValueError('Only RAW and explicit zero FILL chunks are allowed')
        assert not source.read(1), 'Trailing sparse bytes'
    assert expanded_bytes == manifest['userdata_expanded_bytes']
    assert encoded.hexdigest() == manifest['userdata_sparse_sha256']
    assert expanded.hexdigest() == manifest['userdata_expanded_sha256']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload-only', action='store_true', help='Verify the payload files without fastboot')
    parser.add_argument('--flash', action='store_true', help='Write only boot and userdata after all checks pass')
    args = parser.parse_args()
    manifest = json.loads((BASE / 'manifest.json').read_text())
    assert manifest['kind'] == 'dumpling-luneos-volte-audio-statusbar-fixes'
    assert manifest['wrapped_rootfs_verified'] and manifest['sparse_expansion_verified']
    boot = BASE / 'boot.img'
    userdata = BASE / 'userdata.sparse.img'
    assert boot.stat().st_size == manifest['boot']['bytes']
    assert sha256(boot) == manifest['boot']['sha256']
    with boot.open('rb') as image:
        assert image.read(8) == b'ANDROID!'
    assert userdata.stat().st_size == manifest['userdata_sparse_bytes']
    event('verify_payload_on_host', boot_sha256=sha256(boot), sparse_bytes=userdata.stat().st_size)
    verify_sparse(userdata, manifest)
    if args.payload_only:
        event('payload_only_verified', boot_sha256=sha256(boot), sparse_sha256=sha256(userdata))
        return

    def device():
        result = subprocess.run(['fastboot', 'devices'], capture_output=True, text=True, timeout=10, check=True)
        devices = [line.split()[0] for line in result.stdout.splitlines() if line.strip()]
        assert len(devices) == 1, 'Expected exactly one fastboot device'
        serial = devices[0]
        assert hashlib.sha256(serial.encode()).hexdigest() == IDENTITY, 'Device identity changed'
        return serial

    serial = device()

    def getvar(key):
        result = subprocess.run(['fastboot', '-s', serial, 'getvar', key], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, 'getvar failed: ' + key
        match = re.search(re.escape(key) + r':\s*(\S+)', result.stdout + result.stderr)
        assert match, 'Missing fastboot variable: ' + key
        return match.group(1)

    assert getvar('product') == 'msm8998'
    assert getvar('unlocked') == 'yes'
    boot_size = int(getvar('partition-size:boot'), 0)
    userdata_size = int(getvar('partition-size:userdata'), 0)
    assert boot_size == 67108864 and boot.stat().st_size <= boot_size
    assert userdata_size == 121568473088 and manifest['userdata_expanded_bytes'] < userdata_size
    maximum = int(getvar('max-download-size'), 0)
    assert maximum >= 64 * 1024 * 1024
    state_path = BASE / 'install-state.json'
    state = {'preflight_passed': True, 'manifest_sha256': sha256(BASE / 'manifest.json'),
             'flashed_partitions': [], 'flash_complete': False, 'reboot_returncode': None}
    state_path.write_text(json.dumps(state, indent=2) + '\n')
    state_path.chmod(0o600)
    event('all_preflight_checks_passed', boot_partition_bytes=boot_size, userdata_partition_bytes=userdata_size)
    if not args.flash:
        return
    assert device() == serial
    log_path = BASE / 'fastboot-install.log'
    with log_path.open('a', buffering=1) as log:
        log_path.chmod(0o600)

        def execute(arguments, timeout):
            event('fastboot_command', arguments=arguments[:3])
            log.write('COMMAND ' + ' '.join(arguments) + '\n')
            process = subprocess.Popen(['fastboot', '-s', serial, *arguments], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            output = bytearray()
            end = time.monotonic() + timeout
            last_output = time.monotonic()
            timed_out = False
            while True:
                readable, _, _ = select.select([process.stdout], [], [], 0.5)
                if readable:
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    output.extend(chunk)
                    last_output = time.monotonic()
                    text = chunk.decode(errors='replace').replace(serial, '[device]')
                    print(text, end='', flush=True)
                    log.write(text)
                if time.monotonic() > end or time.monotonic() - last_output > 60:
                    process.kill()
                    timed_out = True
                    break
            process.wait()
            code = 124 if timed_out else process.returncode
            log.flush()
            os.fsync(log.fileno())
            return code, output.decode(errors='replace')

        for partition, path in [('userdata', userdata), ('boot', boot)]:
            arguments = ['-S', '16M', 'flash', partition, str(path)] if partition == 'userdata' else ['flash', partition, str(path)]
            code, output = execute(arguments, 900)
            assert code == 0 and 'FAILED' not in output, 'Flash failed: ' + partition
            state['flashed_partitions'].append(partition)
            state_path.write_text(json.dumps(state, indent=2) + '\n')
        state['flash_complete'] = True
        state_path.write_text(json.dumps(state, indent=2) + '\n')
        code, output = execute(['reboot'], 45)
        state['reboot_returncode'] = code
        state_path.write_text(json.dumps(state, indent=2) + '\n')
        event('flash_finished', flash_complete=True, flashed_partitions=state['flashed_partitions'], reboot_returncode=code)


if __name__ == '__main__':
    exit_state = {'pid': os.getpid(), 'exit_code': None}
    try:
        main()
    except BaseException as error:
        exit_state.update(exit_code=1, error_type=type(error).__name__)
        raise
    else:
        exit_state['exit_code'] = 0
    finally:
        exit_state['finished_at'] = datetime.now(timezone.utc).isoformat()
        path = BASE / 'installer-exit.json'
        path.write_text(json.dumps(exit_state, indent=2) + '\n')
        path.chmod(0o600)
