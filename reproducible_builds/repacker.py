from __future__ import annotations

import enum
import dataclasses
import json
import tempfile
import tarfile
import zipfile
import logging
import time
from pathlib import Path
from contextlib import contextmanager, nullcontext
import traceback
import typing as t

from . import docker_environment
from . import common


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
            common.normalize_zip(in_zip=src_arch, out_zip=dest_arch)
            dest_arch.close()
        else:
            src_arch = tarfile.open(self.path.absolute(), "r:*")
            dest_arch = tarfile.open(dest, "w:gz")
            common.normalize_tar(in_tar=src_arch, out_tar=dest_arch)
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


def repack(package: Package, source_dir=None):
    start = time.monotonic()
    if source_dir is not None:
        logger.info(f"Source dir for `{str(package)}` already provided, skipping")
        cm = nullcontext(source_dir)
    elif package.package_type == PackageType.WHEEL:
        sdist = package.find_sdist()
        if not sdist:
            raise FileNotFoundError("Could not found an appropriate sdist for rebuilding the package")
        logger.info(f"Found `{str(sdist)}` as source for repacking `{str(package)}")
        cm = sdist.as_source()
    elif package.package_type == PackageType.SDIST:
        logger.info(f"Using itself (sdist) to repack `{package}")
        cm = package.as_source()
    else:
        raise RuntimeError("Could not locate the source code for rebuilding the package")

    with cm as src_dir_location:
        src_path = Path(src_dir_location)
        docker_env = docker_environment.get_environment_version(package.path.name)
        pkg_name = str(package)

        repack_dir = package.repack_dir
        new_package_pth = repack_dir / pkg_name
        repack_dir.mkdir(exist_ok=True)

        if new_package_pth.exists():
            logger.warning(f"Repacked package `{pkg_name}` already exists, skipping")
            return False

        existing_files = set(x.name for x in repack_dir.iterdir() if x.is_file())

        if package.package_type == PackageType.SDIST:
            build_mode = "--sdist"
        else:
            build_mode = "--wheel"

        logger.info("Spawning docker container")

        stdout = repack_dir / "repack.stdout.txt"
        stderr = repack_dir / "repack.stderr.txt"

        out_p = docker_environment.run_in_docker(
            ["python", "-m", "build", build_mode, "--no-isolation", "--outdir", "/output_dir"],
            docker_env=docker_env,
            source_dir=src_path,
            output_dir=repack_dir,
            stdout=stdout, stderr=stderr
        )

        new_files = set(x.name for x in repack_dir.iterdir() if x.is_file()) - existing_files
        new_files -= {"repack.stdout.txt", "repack.stderr.txt"}

        if out_p.returncode != 0:
            logger.error(f"Failed to repack `{pkg_name}`, check repack.stderr.txt logs")
            return False

        if pkg_name not in new_files:
            logger.error(f"Unable to locate output file `{pkg_name}`, content: {', '.join(new_files)}")
            return False


        new_pkg = Package.from_file(new_package_pth)

        common.run_diffoscope(original=package.path, target=new_package_pth)

        with tempfile.TemporaryDirectory(prefix="normalized_reproducible_packages_") as norm_temp_dir:
            norm_temp_pth = Path(norm_temp_dir)
            (norm_temp_pth/"original").mkdir(exist_ok=True)
            (norm_temp_pth/"repacked").mkdir(exist_ok=True)
            orig_archive_pth = norm_temp_pth / "original" / pkg_name
            repacked_archive_pth = norm_temp_pth / "repacked" / pkg_name
            logger.info(f"Normalizing original package `{pkg_name}`")
            package.normalize(orig_archive_pth)
            logger.info(f"Normalizing repacked package `{pkg_name}`")
            new_pkg.normalize(repacked_archive_pth)
            logger.info(f"Diffing normalized packages `{pkg_name}`")
            common.run_diffoscope(
                original=orig_archive_pth,
                target=repacked_archive_pth,
                out_dir=repack_dir,
                suffix="_normalized",
            )

    end = time.monotonic()
    logger.info(f"Repacking of {pkg_name} finished in {(end-start):.2f} s")
    return True


def repack_all(dataset_dir: Path):
    for idx, pkg in enumerate(Package.enumerate(dataset_dir)):
        repack_dir = pkg.repack_dir
        # Skip if the repacked archive already exists
        if (repack_dir / pkg.path.name).exists():
            continue

        docker_env = docker_environment.get_environment_version(pkg.path.name)
        if docker_env is None:
            logger.info(f"Unsupported package type: `{pkg.path.name}`, skipping repacking... #{idx+1}")
            continue

        logger.info(f"Starting repack for package `{pkg.path.name}` #{idx+1}")
        try:
            repack(pkg)
        except Exception:
            traceback.print_exc()
