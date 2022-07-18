from pathlib import Path


DATA_LOCATION = Path(__file__).parent.absolute().relative_to(Path.cwd())


def get_file(name: str) -> Path:
    fpath = DATA_LOCATION / name

    if not fpath.is_file():
        raise FileNotFoundError(f"No such file in the data directory: `{fpath}`")

    return fpath
