Reproducible Python Builds
==========================

This project aims to provide a framework for researching and monitoring reproducible builds for the Python Packages ecosystem.


Requirements & Installation
---------------------------

This project requires `diffoscope` and `docker` to be installed and accessible on the machine.

Install the reproducible pypi framework: `pip install reproducible-builds`.

This project is distributed using Poetry: https://python-poetry.org , run `poetry install` to install the framework from sources. 


Getting started
---------------

Follow these steps to generate the latest dataset that compares which packages are reproducible and their diffs:


1. Initialize the environment using `python -m reproducible_builds init`, this will check if the required executable paths are found, download the latest pypi stats and build necessary docker image templates
2. Run `python -m reproducible_builds download-top-projects` to download the top K (100 by default) projects from pypi. This is based on the download stats of each project for past 30 days (fetched from the public Aura dataset).
3. Repack all python packages to check if they are reproducible using: `python -m reproducible_builds repack-all`. This will automatically locate every package from the previous step and check for their reproducibility.


The data is stored in the current working directory under the `reproducible_dataset` dir. When the packages are downloaded, it will create a subdirectory with the package name. This subdirectory contains the `pypi_metadata.json` file which is a dump of the PyPI metadata for that package. Specific packages are then stored in subdirectories with the release/version number as the name of the directory. Output directory is automatically created at the location of the package with the package name normalized (dots replaced with underscores) and all output data is stored in there.

You can also repack a specific package instead of the whole dataset of top K packages, for example:
`python -m reproducible_builds repack reproducible_dataset/requests/2.28.1/requests-2.28.1-py3-none-any.whl`


Repacking and reproducibility checks
------------------------------------

Reproducibility check starts with a given path to the package file. Next we locate a source of data from which the package will be rebuild. This is done by trying to lookup an sdist package in the same directory as our target package. The sdist distribution is then unpacked into the temporary directory and a suitable docker image template is found using the package ABI tag to match the environment for re-recreating the package (this matters for wheels). Docker container is then spawned to re-build the package inside the choosen environment via the https://pypi.org/project/build/ frontend. Container logs are stored under the `repack.(stdout|stderr).txt` files in the output directory

After the package has been re-builded, the framework will automatically run diffoscope on the generated package and compare it to the original package. The output of that is stored under the `diff.(html|json|txt)` files. Since most of the packages are not reproducible due to archive metadata information, we also automatically generate a normalized versions from both the original package and repacked one to check if it improves the reproducibility by normalizing this metadata. Diff logs for the normalized archives have a suffix string "_normalized" in their name.


Example structure after the appropriate data has been generated:
```
reproducible_dataset/requests
├── 2.28.1
│   ├── requests-2.28.1-py3-none-any.whl  # Original package
│   ├── requests-2.28.1.tar.gz  # Original package
│   ├── requests-2_28_1-py3-none-any_whl_repacked
│   │   ├── diff.html
│   │   ├── diff.json
│   │   ├── diff.stderr.txt
│   │   ├── diff.stdout.txt
│   │   ├── diff.txt
│   │   ├── diff_normalized.html
│   │   ├── diff_normalized.json
│   │   ├── diff_normalized.stderr.txt
│   │   ├── diff_normalized.stdout.txt
│   │   ├── diff_normalized.txt
│   │   ├── repack.stderr.txt
│   │   ├── repack.stdout.txt
│   │   └── requests-2.28.1-py3-none-any.whl  # Repacked
│   └── requests-2_28_1_tar_gz_repacked
│       ├── diff.html
│       ├── diff.json
│       ├── diff.stderr.txt
│       ├── diff.stdout.txt
│       ├── diff.txt
│       ├── diff_normalized.html
│       ├── diff_normalized.json
│       ├── diff_normalized.stderr.txt
│       ├── diff_normalized.stdout.txt
│       ├── diff_normalized.txt
│       ├── repack.stderr.txt
│       ├── repack.stdout.txt
│       └── requests-2.28.1.tar.gz  # Repacked
└── pypi_metadata.json  # Dump of PyPI JSON metadata 

3 directories, 29 files
```
