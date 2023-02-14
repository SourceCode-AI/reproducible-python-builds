import sys
import shutil
import subprocess
from contextlib import nullcontext
from pathlib import Path
import typing as t


from ..utils import with_tmp_dir


# TODO: make this configurable
AURA_DIFF_IMG = "sourcecodeai/ambience:base-69b5858-dirty"


def run_aura_diff(
        original: Path,
        target: Path,
        target_path: t.Optional[Path]=None,
        stdout: t.Optional[Path]=None,
        stderr: t.Optional[Path]=None,
        suffix: str="",
    ):
    if target_path is None:
        target_path = target.parent

    diff_name = f"aura_diff{suffix}.json"

    if stdout:
        stdout_cm = stdout.open("w")
    else:
        stdout_cm = nullcontext(sys.stdout)

    if stderr:
        stderr_cm = stderr.open("w")
    else:
        stderr_cm = nullcontext(sys.stderr)

    with with_tmp_dir(original, target) as temp_dir:
        orig_path = f"/diff_data/original/{original.name}"
        mod_path = f"/diff_data/modified/{target.name}"

        cmd = [
            "docker", "run", "--rm",
            "-v", f"{str(temp_dir)}:/diff_data",
            "-v", f"{target_path}:/output_data",
            "-w", "/diff_data",
            AURA_DIFF_IMG,
            "diff",
            orig_path, mod_path,
            "-f", f"json:///output_data/{diff_name}"
        ]

        with stdout_cm as stdout_fd, stderr_cm as stderr_fd:
            return subprocess.run(cmd, stdout=stdout_fd, stderr=stderr_fd)
