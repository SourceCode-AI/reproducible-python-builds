import tarfile
import subprocess
import typing as t
import zipfile
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


def diffoscope(original: Path, modified: Path, target_path: t.Optional[Path]=None, suffix="") -> int:
    if target_path is None:
        target_path = modified.parent

    if suffix:
        suffix = "_" + suffix

    cmd = [
        "diffoscope",
        str(original),
        str(modified),
        "--text", str(target_path / f"diffoscope_diff{suffix}.txt"),
        "--html", str(target_path / f"diffoscope_diff{suffix}.html"),
        "--json", str(target_path / f"diffoscope_diff{suffix}.json")
    ]

    stdout = target_path / f"diffoscope_stderr{suffix}.txt"
    stderr = target_path / f"diffoscope_stdout{suffix}.txt"

    with open(stdout, "w") as stdout_fd, open(stderr, "w") as stderr_fd:
        out_p = subprocess.run(cmd, stdout=stdout_fd, stderr=stderr_fd)

    return out_p.returncode


def normalize_tar(in_tar: tarfile.TarFile, out_tar: tarfile.TarFile):
    members = list(in_tar.getmembers())
    members.sort(key=lambda x: x.name)

    for member in members:
        new_member = tarfile.TarInfo(name=member.name)
        new_member.uid = 0
        new_member.gid = 0
        new_member.mtime = 0
        new_member.uname = ""
        new_member.gname = ""
        new_member.type = member.type
        new_member.size = member.size

        if member.isfile():
            with in_tar.extractfile(member) as archive_file:
                out_tar.addfile(new_member, archive_file)
        elif new_member.isdir():
            out_tar.addfile(new_member)
        else:
            out_tar.addfile(member)


def normalize_zip(in_zip: zipfile.ZipFile, out_zip: zipfile.ZipFile):
    members = list(in_zip.infolist())
    members.sort(key=lambda x: x.filename)

    for member in members:
        new_member = zipfile.ZipInfo(
            filename=member.filename,
            date_time=(1980, 1, 1, 0, 0, 0),
        )
        new_member.external_attr = 0o770 << 16
        new_member.compress_type = member.compress_type
        data = in_zip.read(name=member.filename)
        out_zip.writestr(new_member, data=data)


def run_diffoscope(original: Path, target: Path, suffix="", out_dir: t.Optional[Path]=None) -> subprocess.CompletedProcess:
    if out_dir is None:
        out_dir = target.parent

    txt_out = str((out_dir / f"diff{suffix}.txt").absolute())
    json_out = str((out_dir / f"diff{suffix}.json").absolute())
    html_out = str((out_dir / f"diff{suffix}.html").absolute())

    cmd = [
        "diffoscope",
        str(original.absolute()),
        str(target.absolute()),
        "--text", txt_out,
        "--json", json_out,
        "--html", html_out
    ]

    stdout: Path = out_dir / f"diff{suffix}.stdout.txt"
    stderr: Path = out_dir / f"diff{suffix}.stderr.txt"

    with stdout.open("w") as stdout_fd, stderr.open("w") as stderr_fd:
        out_p = subprocess.run(cmd, stdout=stdout_fd, stderr=stderr_fd)

    return out_p
