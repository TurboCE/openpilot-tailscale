"""AGNOS /data-only installer; embedded with assets into install.sh."""
import argparse
import datetime
import difflib
import fcntl
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

VERSION = "1.104.5"
ARM64_SHA256 = "e900b0e6e25023a1e504b2c237ce2a32ea0535e006f8c1a1097a490886493b6c"
BASE = pathlib.Path("/data/tailscale")
HOOK = pathlib.Path("/data/continue.sh")
BEGIN = "# BEGIN TurboCE/openpilot-tailscale"
END = "# END TurboCE/openpilot-tailscale"
BLOCK = BEGIN + "\n/data/tailscale/start.sh >> /data/tailscale-start.log 2>&1 &\n" + END + "\n"


def remove_block(text):
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        raise ValueError("Malformed managed startup block; inspect /data/continue.sh")
    return re.sub(r"(?m)^" + re.escape(BEGIN) + r"\n.*?^" + re.escape(END) + r"\n?", "", text, flags=re.S)


def add_block(text):
    text = remove_block(text)
    if not text.startswith("#!") or "\n" not in text:
        raise ValueError("Expected a shell script with a shebang in /data/continue.sh")
    # Refuse a second, unmanaged Tailscale hook rather than start it twice.
    if re.search(r"(?m)^[^#\n]*tailscale", text):
        raise ValueError("Existing unmanaged Tailscale startup hook; migrate it explicitly first")
    head, rest = text.split("\n", 1)
    return head + "\n" + BLOCK + rest


def atomic_write(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".install-tmp")
    if path.is_symlink() or tmp.is_symlink():
        raise ValueError("Refusing to overwrite a symlink: " + str(path))
    tmp.write_text(content)
    tmp.chmod(mode)
    os.replace(str(tmp), str(path))


def run(*args, check=True):
    return subprocess.run(args, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def fetch(url, path):
    with urllib.request.urlopen(url, timeout=90) as response, path.open("wb") as out:
        if response.status != 200:
            raise RuntimeError("Download HTTP status " + str(response.status))
        shutil.copyfileobj(response, out)


def backup_hook():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = pathlib.Path(tempfile.mkdtemp(prefix=stamp + "-", dir=str(BASE / "backups")))
    shutil.copy2(str(HOOK), str(folder / "continue.sh"))
    return folder


def preflight():
    if os.geteuid() != 0:
        raise RuntimeError("Run through sudo: curl -fsSL <install-url> | sudo -n bash")
    if platform.machine() not in ("aarch64", "arm64"):
        raise RuntimeError("This release supports ARM64 comma devices only")
    if not pathlib.Path("/VERSION").is_file() or not pathlib.Path("/data/openpilot").is_dir():
        raise RuntimeError("Expected an AGNOS openpilot device; installation cancelled")
    onroad = pathlib.Path("/data/params/d/IsOnroad")
    if not onroad.is_file() or onroad.read_bytes().strip() != b"0":
        raise RuntimeError("Device must be offroad before installation")
    if not HOOK.is_file() or HOOK.is_symlink():
        raise RuntimeError("Expected a regular /data/continue.sh")
    for program in ("systemctl", "systemd-analyze", "flock", "bash", "diff"):
        if not shutil.which(program):
            raise RuntimeError("Missing required command: " + program)
    if not pathlib.Path("/dev/net/tun").exists():
        raise RuntimeError("/dev/net/tun is missing; kernel networking support is required")


def uninstall():
    original = HOOK.read_text()
    replacement = remove_block(original)
    folder = backup_hook()
    atomic_write(HOOK, replacement, HOOK.stat().st_mode & 0o777)
    for name in ("tailscaled-delay.timer", "tailscaled.service"):
        unit = pathlib.Path("/run/systemd/system") / name
        if unit.is_symlink() and unit.resolve() == BASE / name:
            run("systemctl", "stop", name, check=False)
            unit.unlink()
    run("systemctl", "daemon-reload")
    print("Autostart removed. Login state and downloaded binaries preserved in /data/tailscale.")
    print("Startup script backup:", folder)


def install(assets):
    original = HOOK.read_text()
    replacement = add_block(original)
    # Do not take over an independently installed/package-managed daemon.
    fragment = run("systemctl", "show", "tailscaled.service", "-p", "FragmentPath", "--value", check=False).stdout.strip()
    if fragment and pathlib.Path(fragment).resolve() != BASE / "tailscaled.service":
        raise RuntimeError("Another Tailscale service exists: " + fragment)
    stem = "tailscale_" + VERSION + "_arm64"
    url = "https://dl.tailscale.com/stable/" + stem + ".tgz"
    release = BASE / "releases" / (VERSION + "-arm64")
    manifest_path = release / "verified.json"
    cached = False
    if manifest_path.is_file():
        meta = json.loads(manifest_path.read_text())
        cached = meta.get("archive_sha256") == ARM64_SHA256 and all(
            (release / name).is_file() and digest(release / name) == meta.get(name + "_sha256")
            for name in ("tailscale", "tailscaled"))
    if not cached:
        print("Downloading official Tailscale", VERSION, "and verifying SHA-256...", flush=True)
        with tempfile.TemporaryDirectory(prefix="download-", dir=str(BASE)) as temp:
            temp = pathlib.Path(temp)
            archive = temp / "tailscale.tgz"
            fetch(url, archive)
            if digest(archive) != ARM64_SHA256:
                raise RuntimeError("SHA-256 mismatch; nothing was added to the startup hook")
            if archive.read_bytes()[:2] != b"\x1f\x8b":
                raise RuntimeError("Expected gzip archive, not an HTML/error response")
            stage = temp / "unpacked"
            stage.mkdir()
            with tarfile.open(str(archive), "r:gz") as tf:
                for name in ("tailscale", "tailscaled"):
                    member = tf.getmember(stem + "/" + name)
                    if not member.isfile():
                        raise RuntimeError("Unexpected archive member type")
                    with tf.extractfile(member) as src, (stage / name).open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    (stage / name).chmod(0o755)
            if run(str(stage / "tailscale"), "version").stdout.splitlines()[0] != VERSION:
                raise RuntimeError("Downloaded binary reports the wrong version")
            release.mkdir(parents=True, exist_ok=True)
            meta = {"archive_url": url, "archive_sha256": ARM64_SHA256}
            for name in ("tailscale", "tailscaled"):
                os.replace(str(stage / name), str(release / name))
                meta[name + "_sha256"] = digest(release / name)
            atomic_write(manifest_path, json.dumps(meta, indent=2))
    # AGNOS 18.4 can ship nft frontends with a kernel lacking nf_tables.
    # Select legacy tools for this service only, after read-only probes.
    compat = BASE / "compat"
    compat.mkdir(exist_ok=True)
    for name in ("iptables", "ip6tables"):
        target = compat / name
        legacy = shutil.which(name + "-legacy")
        default = shutil.which(name)
        if (default and legacy and
                run(default, "-t", "filter", "-S", check=False).returncode != 0 and
                run(legacy, "-t", "filter", "-S", check=False).returncode == 0):
            if target.is_symlink():
                target.unlink()
            if target.exists():
                raise RuntimeError("Unexpected compatibility file: " + str(target))
            target.symlink_to(legacy)
            print("Using service-local legacy firewall frontend:", name)
        elif target.is_symlink():
            target.unlink()
    (BASE / "bin").mkdir(exist_ok=True)
    (BASE / "state").mkdir(mode=0o700, exist_ok=True)
    (BASE / "state").chmod(0o700)
    folder = backup_hook()
    for name, content in assets.items():
        target = BASE / name
        if target.is_file():
            shutil.copy2(str(target), str(folder / name))
        atomic_write(target, content, 0o755 if name.endswith(".sh") else 0o644)
    for name in ("tailscale", "tailscaled"):
        target = BASE / "bin" / name
        tmp = target.with_name(name + ".link-tmp")
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        tmp.symlink_to(release / name)
        os.replace(str(tmp), str(target))
    for name in ("start.sh", "login.sh"):
        run("bash", "-n", str(BASE / name))
    run("systemd-analyze", "verify", str(BASE / "tailscaled.service"), str(BASE / "tailscaled-delay.timer"))
    candidate = folder / "continue.sh.new"
    candidate.write_text(replacement)
    run("bash", "-n", str(candidate))
    patch = "".join(difflib.unified_diff(original.splitlines(True), replacement.splitlines(True), fromfile="a/data/continue.sh", tofile="b/data/continue.sh"))
    (folder / "continue.sh.patch").write_text(patch)
    atomic_write(HOOK, replacement, HOOK.stat().st_mode & 0o777)
    run("/usr/bin/bash", str(BASE / "start.sh"))
    print("Installed. Tailscale is scheduled at boot +90s (or now if uptime already exceeds 90s).")
    print("openpilot starts independently; current running tailscaled is not restarted.")
    print("Backup and exact device patch:", folder)
    print("One-time login: sudo /data/tailscale/login.sh")
    print("Status: sudo /data/tailscale/bin/tailscale status")


def main(assets):
    parser = argparse.ArgumentParser(description="Tailscale on AGNOS, boot +90s")
    parser.add_argument("--uninstall", action="store_true", help="remove autostart, preserve login state")
    args = parser.parse_args()
    preflight()
    BASE.mkdir(mode=0o755, exist_ok=True)
    (BASE / "backups").mkdir(exist_ok=True)
    with (BASE / ".install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.uninstall:
            uninstall()
        else:
            install(assets)
