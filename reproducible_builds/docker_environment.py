import sys
import os
import subprocess
from pathlib import Path
from contextlib import nullcontext
import typing as t

from packaging.utils import parse_wheel_filename

from .data import get_file


docker_tags = {
    (3, 7): "python:3.7.13-buster",
    (3, 8): "python:3.8.13-buster",
    (3, 9): "python:3.9.13-buster",
    (3, 10): "python:3.10-buster",
    (3, 11): "python:3.11.0b3-buster"
}



def build_images():
    docker_file = get_file("Dockerfile_buildenv")
    cwd = os.getcwd()

    try:
        os.chdir(docker_file.parent)

        for py_version, base_image in docker_tags.items():
            image_tag = f"reproducible_env:py{py_version[0]}.{py_version[1]}"

            cmd = [
                "docker", "build",
                "-t", image_tag,
                "--build-arg", f"BASE_IMAGE={base_image}",
                "-f", str(docker_file.name),
                "."
            ]
            subprocess.check_call(cmd, stderr=sys.stderr, stdout=sys.stdout)
    finally:
        os.chdir(cwd)


def run_in_docker(
        cmd: t.List[str],
        docker_env: t.Tuple[int, int],
        source_dir: Path,
        output_dir: Path,
        stdout: t.Optional[Path]=None,
        stderr: t.Optional[Path]=None
) -> subprocess.CompletedProcess:
    docker_tag = f"reproducible_env:py{'.'.join(map(str, docker_env))}"

    final_cmd = [
        "docker", "run", "--rm",
        # Add source dir volume mount
        "-v", f"{str(source_dir.absolute())}:/source_dir",
        # Mount output dir volume
        "-v", f"{str(output_dir)}:/output_dir",
        "-w", "/source_dir",
        docker_tag,
        *cmd
    ]

    if stdout:
        stdout_cm = stdout.open("w")
    else:
        stdout_cm = nullcontext(sys.stdout)

    if stderr:
        stderr_cm = stderr.open("w")
    else:
        stderr_cm = nullcontext(sys.stderr)

    with stdout_cm as stdout_fd, stderr_cm as stderr_fd:
        return subprocess.run(final_cmd, stdout=stdout_fd, stderr=stderr_fd)


def get_environment_version(fname: str) -> t.Optional[t.Tuple[int, int]]:
    # Return latest python for sdist
    if fname.endswith(".tar.gz"):
        return (3, 11)

    name, ver, build, tags = parse_wheel_filename(fname)

    for t in tags:
        if not t.platform in ("any", "linux_x86_64"):
            continue
        if t.interpreter in ("py3", "cp3"):
            return (3, 10)
        elif t.interpreter in ("py37", "cp37"):
            return (3, 7)
        elif t.interpreter in ("py38", "cp38"):
            return (3, 8)
        elif t.interpreter in ("py39", "cp39"):
            return (3, 9)
        elif t.interpreter in ("py310", "cp310"):
            return (3, 10)
        elif t.interpreter in ("py311", "cp311"):
            return (3, 11)

    return None


if __name__ == "__main__":
    if len(sys.argv) == 1 or sys.argv[1] == "build_images":
        build_images()
    else:
        raise RuntimeError("unknown command")
