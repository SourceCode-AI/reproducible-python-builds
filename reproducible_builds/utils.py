import gzip
import subprocess
import shutil
import logging
import tempfile
import contextlib
from pathlib import Path

import requests


DEFAULT_OUTPUT_DIR = "reproducible_dataset"
DOWNLOAD_STATS_URL = "https://cdn.sourcecode.ai/aura/pypi_download_stats.gz"

logger = logging.getLogger(__name__)


def download_stats(pth: Path):
    if pth.is_dir():
        pth /= "pypi_download_stats.json"

    logger.info(f"Downloading `{DOWNLOAD_STATS_URL}`")
    resp = requests.get(DOWNLOAD_STATS_URL)
    if resp.status_code != 200:
        raise ValueError("Something went wrong when downloading the pypi download stats")

    pth.write_bytes(gzip.decompress(resp.content))
    logger.info(f"PyPI download stats written to `{str(pth)}`")


def check_command(bin: str, *args):
    location = shutil.which(bin)
    if not location:
        raise RuntimeError(f"Could not find executable `{bin}`")

    logger.info(f"Executable `{bin}` located in `{location}`")

    if args:
        subprocess.check_call([bin, *args])

    return True


@contextlib.contextmanager
def with_tmp_dir(original: Path, modified: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="reproducible-builds-tmpdir-") as tdir:
        tdir_pth = Path(tdir)
        orig_dir = (tdir_pth / "original")
        orig_dir.mkdir()
        mod_dir = (tdir_pth / "modified")
        mod_dir.mkdir()
        (tdir_pth / "output").mkdir()
        shutil.copy(original, (orig_dir/original.name))
        shutil.copy(modified, (mod_dir/modified.name))
        yield tdir
