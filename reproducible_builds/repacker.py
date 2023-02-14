from __future__ import annotations

import hashlib
import json
import tempfile
import logging
import time
from pathlib import Path
from contextlib import nullcontext
import traceback
import typing as t

from . import docker_environment
from . import common
from . import postprocessing
from .tools import aura_diff


logger = logging.getLogger(__name__)



def repack(package: common.Package, source_dir=None):
    start = time.monotonic()
    if source_dir is not None:
        logger.info(f"Source dir for `{str(package)}` already provided, skipping")
        cm = nullcontext(source_dir)
    elif package.package_type == common.PackageType.WHEEL:
        sdist = package.find_sdist()
        if not sdist:
            raise FileNotFoundError("Could not found an appropriate sdist for rebuilding the package")
        logger.info(f"Found `{str(sdist)}` as source for repacking `{str(package)}")
        cm = sdist.as_source()
    elif package.package_type == common.PackageType.SDIST:
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

        if package.package_type == common.PackageType.SDIST:
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


        new_pkg = common.Package.from_file(new_package_pth)

        common.run_diffoscope(original=package.path, target=new_package_pth)
        aura_diff.run_aura_diff(original=package.path, target=new_package_pth)

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

            original_normalized_md5 = hashlib.md5(orig_archive_pth.read_bytes()).hexdigest()
            repacked_normalized_md5 = hashlib.md5(repacked_archive_pth.read_bytes()).hexdigest()

            logger.info(f"Diffing normalized packages `{pkg_name}`")
            common.run_diffoscope(
                original=orig_archive_pth,
                target=repacked_archive_pth,
                out_dir=repack_dir,
                suffix="_normalized",
            )
            aura_diff.run_aura_diff(
                original=orig_archive_pth,
                target=repacked_archive_pth,
                target_path=repack_dir,
                suffix="_normalized"
            )

        original_md5 = hashlib.md5(package.path.read_bytes()).hexdigest()
        repacked_md5 = hashlib.md5(new_package_pth.read_bytes()).hexdigest()

        checksums = {
            "original": original_md5,
            "repacked": repacked_md5,
            "normalized_original": original_normalized_md5,
            "normalized_repacked": repacked_normalized_md5
        }
        with (new_package_pth.parent / "checksums.json").open("w") as fd:
            fd.write(json.dumps(checksums))

    results = common.ReproducibleResults.from_package(package)
    postprocessing.combine_results(results)

    end = time.monotonic()
    logger.info(f"Repacking and processing of {pkg_name} finished in {(end-start):.2f} s")
    return True


def repack_all(dataset_dir: Path):
    for idx, pkg in enumerate(common.Package.enumerate(dataset_dir)):
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
