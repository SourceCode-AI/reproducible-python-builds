import gzip
import subprocess
import shutil
import logging
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

