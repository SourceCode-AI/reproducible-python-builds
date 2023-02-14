from __future__ import annotations

import json
import subprocess
import logging
import enum
import tarfile
import zipfile
import tempfile
import dataclasses
from contextlib import contextmanager
from pathlib import Path
import typing as t


logger = logging.getLogger(__name__)


@enum.unique
class PackageType(enum.Enum):
    SDIST = "sdist"
    WHEEL = "wheel"

    @staticmethod
    def detect(filename: str) -> t.Optional[PackageType]:
        if filename.endswith(".whl"):
            return PackageType.WHEEL
        elif filename.endswith(".tar.gz"):
            return PackageType.SDIST
        else:
            return None


@dataclasses.dataclass
class Package:
    package_type: PackageType
    path: Path

    @classmethod
    def from_file(cls, path: Path) -> Package:
        if not (pkg_type:=PackageType.detect(path.name)):
            raise ValueError(f"`{path.name}` does not appear to be a valid/supported package file")

        return cls(
            package_type=pkg_type,
            path=path
        )

    @classmethod
    def enumerate(cls, location: Path):
        for pypi_stats in location.glob("*/pypi_metadata.json"):
            metadata = json.loads(pypi_stats.read_text())

            for version, releases in metadata["releases"].items():
                version_path = pypi_stats.parent / version
                if not version_path.exists():
                    continue

                for release in releases:
                    pkg_path = version_path / release["filename"]
                    if not pkg_path.is_file():
                        continue
                    elif not (pkg_type:=PackageType.detect(release["filename"])):
                        continue
                    yield cls(
                        package_type=pkg_type,
                        path = pkg_path
                    )

    @property
    def repack_dir(self) -> Path:
        name = self.path.name.replace(".", "_") + "_repacked"
        return (self.path.parent / name).absolute()

    def find_sdist(self) -> t.Optional[Package]:
        location = self.path.parent

        for pkg in location.glob("*"):
            pkg_type = PackageType.detect(pkg.name)

            if pkg_type == PackageType.SDIST:
                return Package(package_type=pkg_type, path=pkg)

    def normalize(self, dest: Path):
        if self.path.name.endswith(".whl"):
            src_arch = zipfile.ZipFile(self.path.absolute(), "r")
            dest_arch = zipfile.ZipFile(dest, "w")
            normalize_zip(in_zip=src_arch, out_zip=dest_arch)
            dest_arch.close()
        else:
            src_arch = tarfile.open(self.path.absolute(), "r:*")
            dest_arch = tarfile.open(dest, "w:gz")
            normalize_tar(in_tar=src_arch, out_tar=dest_arch)
            dest_arch.close()

    @contextmanager
    def as_source(self):
        with tempfile.TemporaryDirectory(prefix="reproducible_src_dir_") as tmpdir:
            logger.info(f"Created temporary directory for sources: `{tmpdir}`")
            tmp_path = Path(tmpdir)

            if self.path.name.endswith(".tar.gz"):
                with tarfile.open(self.path, "r:*") as archive:
                    logger.info(f"Extracting `{self.path.name}` to `{tmpdir}`")
                    archive.extractall(tmpdir)

                    for x in tmp_path.glob("*/PKG-INFO"):
                        yield x.parent
                        break
            elif self.path.name.endswith(".whl"):
                archive = zipfile.ZipFile(self.path, "r")
                logger.info(f"Extracting `{self.path.name}` to `{tmpdir}`")
                archive.extractall(tmpdir)
                yield tmpdir
            else:
                raise ValueError("Unknown archive format for this file")

    def __str__(self):
        return self.path.name


@dataclasses.dataclass
class ReproducibleResults:
    original_package: Package
    repacked_package: Package

    @classmethod
    def from_package(cls, original: Package) -> ReproducibleResults:
        repacked = original.repack_dir / original.path.name
        repacked_pkg = Package.from_file(repacked)
        return cls(
            original_package=original,
            repacked_package=repacked_pkg
        )

    @property
    def build_successful(self) -> bool:
        pth = self.original_package.repack_dir / self.original_package.path.name
        return pth.is_file()

    @property
    def data_dir(self) -> Path:
        return self.repacked_package.path.parent

    @property
    def original_diffoscope(self) -> t.Optional[Path]:
        return self._check_file(self.data_dir / "diff.json")

    @property
    def normalized_diffoscope(self) -> t.Optional[Path]:
        return self._check_file(self.data_dir / "diff_normalized.json")

    @property
    def aura_diff(self) -> t.Optional[Path]:
        return self._check_file(self.data_dir / "aura_diff.json")

    @property
    def normalized_aura_diff(self) -> t.Optional[Path]:
        return self._check_file(self.data_dir / "aura_diff_normalized.json")

    @property
    def checksums(self) -> t.Optional[Path]:
        return self._check_file(self.data_dir / "checksums.json")

    def _check_file(self, location: Path) -> t.Optional[Path]:
        if location.exists() and location.stat().st_size > 1:
            return location
        return None



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
