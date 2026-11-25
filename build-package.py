#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import time

package = Path(__file__).resolve().parent
base = package.parent / "phase4-native-desktop-repack"
directory = package
rootfs = directory / "rootfs.ext4"
userdata = directory / "userdata.img"
sparse = directory / "userdata.sparse.img"
overlay = directory / "overlay"


def event(stage, **details):
    print(json.dumps({"stage": stage, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **details}), flush=True)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_fs(path, name):
    result = subprocess.run(["e2fsck", "-f", "-n", str(path)], capture_output=True, text=True)
    (directory / (name + "-e2fsck.log")).write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr


def quoted(path):
    path = str(path)
    assert '"' not in path and "\n" not in path
    return '"' + path + '"'


if not rootfs.exists():
    shutil = importlib.util.find_spec("shutil")
    source = base / "rootfs.ext4"
    subprocess.run(["cp", "--reflink=auto", str(source), str(rootfs)], check=True)
assert rootfs.is_file()
boot = directory / "boot.img"
if not boot.exists():
    subprocess.run(["cp", str(base / "boot.img"), str(boot)], check=True)

files = []
links = []
directories = []
for folder, subdirs, names in os.walk(overlay, followlinks=False):
    for name in subdirs + names:
        source_path = Path(folder) / name
        relative = source_path.relative_to(overlay).as_posix()
        assert re.fullmatch(r"[A-Za-z0-9_./+@:-]+", relative), relative
        target = "/" + relative
        mode = source_path.lstat().st_mode
        if stat.S_ISDIR(mode):
            directories.append((target, mode))
        elif stat.S_ISLNK(mode):
            links.append((target, os.readlink(source_path)))
        elif stat.S_ISREG(mode):
            files.append((target, source_path, mode))
        else:
            raise ValueError("Unexpected overlay entry: " + relative)

commands = []
for target, mode in sorted(directories, key=lambda item: (item[0].count("/"), item[0])):
    commands.append("mkdir " + quoted(target))
for target, source_path, mode in files:
    commands.extend([
        "rm " + quoted(target),
        "write " + quoted(source_path) + " " + quoted(target),
        "set_inode_field " + quoted(target) + " mode 0" + format(stat.S_IFREG | stat.S_IMODE(mode), "o"),
        "set_inode_field " + quoted(target) + " uid 0",
        "set_inode_field " + quoted(target) + " gid 0",
    ])
for target, destination in links:
    commands.extend(["rm " + quoted(target), "symlink " + quoted(target) + " " + quoted(destination)])
batch = directory / "overlay.debugfs"
batch.write_text("\n".join(commands) + "\n")
event("apply_overlay", files=len(files), links=len(links), directories=len(directories))
result = subprocess.run(["debugfs", "-w", "-f", str(batch), str(rootfs)], capture_output=True, text=True)
(directory / "overlay-debugfs.log").write_text(result.stdout + result.stderr)
assert result.returncode == 0, result.stdout + result.stderr

spec = importlib.util.spec_from_file_location("rootfs_validator", package.parent.parent / "oneplus5t-luneos/scripts/verify-rootfs-login.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
filesystem = validator.Rootfs(rootfs)
for target, source_path, mode in files:
    assert filesystem.read(target) == source_path.read_bytes(), target
for target, destination in links:
    kind, mode, value = filesystem.stat(target)
    assert kind == "symlink", target
    assert value == destination, target
check_fs(rootfs, "rootfs")
rootfs_hash = digest(rootfs)
event("rootfs_verified", bytes=rootfs.stat().st_size, sha256=rootfs_hash)

seed = directory / "userdata-seed"
seed.mkdir(exist_ok=True)
seed_file = seed / "rootfs.img"
if not seed_file.exists() or not os.path.samefile(seed_file, rootfs):
    if seed_file.exists():
        seed_file.unlink()
    os.link(rootfs, seed_file)
size = (rootfs.stat().st_size + 512 * 1024 * 1024 + 4095) // 4096 * 4096
with userdata.open("wb") as stream:
    stream.truncate(size)
event("create_userdata", bytes=size)
result = subprocess.run([
    "mke2fs", "-q", "-t", "ext4", "-b", "4096", "-I", "256",
    "-m", "0", "-N", "4096", "-L", "userdata", "-J", "size=32",
    "-E", "lazy_itable_init=0,lazy_journal_init=0",
    "-d", str(seed), str(userdata)
], capture_output=True, text=True)
(directory / "userdata-mke2fs.log").write_text(result.stdout + result.stderr)
assert result.returncode == 0, result.stdout + result.stderr
for field, value in (("uid", "0"), ("gid", "0"), ("mode", "0100644")):
    result = subprocess.run(
        ["debugfs", "-w", "-R", "set_inode_field /rootfs.img " + field + " " + value, str(userdata)],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
check_fs(userdata, "userdata")

error_file = directory / "userdata-rootfs-readback.log"
with error_file.open("wb") as errors:
    process = subprocess.Popen(["debugfs", "-R", "cat /rootfs.img", str(userdata)],
                               stdout=subprocess.PIPE, stderr=errors)
    wrapped_hash = hashlib.sha256()
    copied = 0
    while True:
        block = process.stdout.read(4 * 1024 * 1024)
        if not block:
            break
        wrapped_hash.update(block)
        copied += len(block)
    assert process.wait() == 0
assert copied == rootfs.stat().st_size
assert wrapped_hash.hexdigest() == rootfs_hash, "Wrapped rootfs differs"
event("wrapped_rootfs_verified", sha256=rootfs_hash)

blocksize = 4096
zero = b"\0" * blocksize
chunks = 0
raw_hash = hashlib.sha256()
header = struct.Struct("<I4H4I")
chunk_header = struct.Struct("<2H2I")
last_event = time.monotonic()
with userdata.open("rb") as source, sparse.open("wb") as output:
    output.write(b"\0" * header.size)
    raw_data = bytearray()
    zeros = 0

    def flush_raw():
        global chunks
        if raw_data:
            output.write(chunk_header.pack(0xCAC1, 0, len(raw_data) // blocksize, len(raw_data) + chunk_header.size))
            output.write(raw_data)
            raw_data.clear()
            chunks += 1

    def flush_zeros():
        global zeros, chunks
        if zeros:
            output.write(chunk_header.pack(0xCAC2, 0, zeros, chunk_header.size + 4))
            output.write(b"\0" * 4)
            zeros = 0
            chunks += 1

    event("encode_sparse_userdata")
    completed = 0
    while True:
        data = source.read(4 * 1024 * 1024)
        if not data:
            break
        assert len(data) % blocksize == 0
        raw_hash.update(data)
        for offset in range(0, len(data), blocksize):
            block = data[offset:offset + blocksize]
            if block == zero:
                flush_raw()
                zeros += 1
            else:
                flush_zeros()
                raw_data.extend(block)
                if len(raw_data) >= 4 * 1024 * 1024:
                    flush_raw()
        completed += len(data)
        if time.monotonic() - last_event >= 30:
            event("sparse_encoding_progress", expanded_bytes=completed, total_bytes=size)
            last_event = time.monotonic()
    flush_raw()
    flush_zeros()
    assert completed == size
    output.seek(0)
    output.write(header.pack(0xED26FF3A, 1, 0, header.size, chunk_header.size,
                             blocksize, size // blocksize, chunks, 0))

decoded_hash = hashlib.sha256()
decoded_bytes = 0
zero_buffer = b"\0" * (4 * 1024 * 1024)
with sparse.open("rb") as stream:
    fields = header.unpack(stream.read(header.size))
    assert fields[:7] == (0xED26FF3A, 1, 0, 28, 12, 4096, size // blocksize)
    assert fields[7] == chunks
    for _ in range(chunks):
        kind, reserved, count, total = chunk_header.unpack(stream.read(chunk_header.size))
        assert reserved == 0
        length = count * blocksize
        if kind == 0xCAC1:
            assert total == length + chunk_header.size
            while length:
                data = stream.read(min(4 * 1024 * 1024, length))
                assert data
                decoded_hash.update(data)
                decoded_bytes += len(data)
                length -= len(data)
        elif kind == 0xCAC2:
            assert total == chunk_header.size + 4 and stream.read(4) == b"\0" * 4
            while length:
                step = min(length, len(zero_buffer))
                decoded_hash.update(zero_buffer[:step])
                decoded_bytes += step
                length -= step
        else:
            raise ValueError("Unexpected sparse chunk type")
    assert not stream.read(1)
assert decoded_bytes == size
assert decoded_hash.digest() == raw_hash.digest(), "Sparse expansion changed content"
event("verify_sparse_expansion", sparse_bytes=sparse.stat().st_size, chunks=chunks)

boot_manifest = json.loads((base / "manifest.json").read_text())
result = {
    "kind": "dumpling-luneos-volte-audio-statusbar-fixes",
    "base": "phase4-native-desktop-repack",
    "boot": boot_manifest["boot"],
    "rootfs_bytes": rootfs.stat().st_size,
    "rootfs_sha256": rootfs_hash,
    "userdata_expanded_bytes": size,
    "userdata_expanded_sha256": raw_hash.hexdigest(),
    "userdata_sparse_bytes": sparse.stat().st_size,
    "userdata_sparse_sha256": digest(sparse),
    "sparse_chunks": chunks,
    "wrapped_rootfs_verified": True,
    "sparse_expansion_verified": True,
    "runtime_verified": False,
    "overlay": [
        {
            "path": "/" + source_path.relative_to(overlay).as_posix(),
            "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        }
        for target, source_path, mode in files
    ],
    "links": [
        {"path": target, "target": destination} for target, destination in links
    ],
}
(directory / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
event("desktop_install_payload_verified", **result)
