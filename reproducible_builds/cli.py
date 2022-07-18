import logging
import shutil
from pathlib import Path

import click

from . import utils
from . import downloader
from . import docker_environment
from . import repacker


CWD = Path.cwd()
DEFAULT_OUT_DIR = CWD / "reproducible_dataset"


@click.group()
def cli():
    pass


@cli.command()
def init():
    """
    Initialize the environment with necessary data and perform checks
    """
    check_environment()
    download_stats()
    build_docker_environment()


@cli.command()
def check_environment():
    """
    Check the environment if the necessary executables are found
    """
    utils.check_command("docker", "version")
    utils.check_command("diffoscope", "--version")


@cli.command()
def download_stats():
    """
    Fetch and store the latest download stats
    """
    utils.download_stats(CWD)


@cli.command()
@click.option("--top", type=int, default=100)
def download_top_projects(top):
    """
    Download the top K python packages based on download stats
    """
    if not (CWD/"pypi_download_stats.json").exists():
        download_stats()

    downloader.download_top_projects(DEFAULT_OUT_DIR, top_k=top)


@cli.command()
def build_docker_environment():
    """
    Build docker images from the template, needed for repacking wheels
    """
    docker_environment.build_images()


@cli.command()
@click.argument("filename", type=click.Path(exists=True))
def repack(filename):
    """
    Repack and generate data for the concrete python package
    """
    pth = Path(filename)
    pkg = repacker.Package.from_file(pth)

    repack_dir = pkg.repack_dir
    if repack_dir.exists() and click.confirm(f"Target directory `{repack_dir}` already exists, do you want to remove it and continue?", abort=True):
        shutil.rmtree(repack_dir)

    repacker.repack(pkg)


@cli.command()
def repack_all():
    """
    Automatically scan the target dataset dir and repack all packages within it
    """
    repacker.repack_all(DEFAULT_OUT_DIR)


if __name__ == "__main__":
    cli()
