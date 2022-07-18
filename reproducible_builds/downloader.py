import json
import logging
from pathlib import Path

import requests


logger = logging.getLogger(__name__)


def download_project(name: str, out_dir: Path) -> bool:
    json_resp = requests.get(f"https://pypi.org/pypi/{name}/json")
    proj_json = json_resp.json()

    proj_root_dir = (out_dir / name)
    proj_root_dir.mkdir(exist_ok=True, parents=True)
    (proj_root_dir / "pypi_metadata.json").write_text(json_resp.text)

    proj_dir = proj_root_dir / proj_json["info"]["version"]
    proj_dir.mkdir(exist_ok=True)

    for url in proj_json["urls"]:
        pkg_path = proj_dir/url["filename"]

        if pkg_path.exists() and pkg_path.stat().st_size == url["size"]:  # Already downloaded
            continue

        logger.info(f"Downloading `{url['url']}`")
        pkg_resp = requests.get(url["url"])

        if pkg_resp.status_code != 200:
            logger.warning(f"Error downloading `{url['url']}`: HTTP {pkg_resp.status_code}")
            continue

        pkg_path.write_bytes(pkg_resp.content)


def download_top_projects(out_dir: Path, top_k: int=100):
    with open("pypi_download_stats.json", "r") as fd:
        for idx, stat in enumerate(fd):
            if idx >= top_k:
                return

            if not (stat:=stat.strip()):
                continue

            stat = json.loads(stat)
            logger.info(f"Processing package `{stat['package_name']}` #{idx+1}")
            download_project(stat["package_name"], out_dir)
