import json
import typing as t


from .common import ReproducibleResults


def combine_results(
    results: ReproducibleResults
):
    version_root = results.original_package.path.parent
    version = version_root.name
    pkg_root = version_root.parent
    name = pkg_root.name

    combined = {
        "package_name": name,
        "version": version,
        "package_type": results.original_package.package_type.value,
        "checksums": None,
        "results": {},
        "normalization_removed_tags": None,
        "original_tags": None,
        "original_diffoscope": None,
        "original_aura_diff": None,
        "normalized_tags": None,
        "normalized_diffoscope": None,
        "normalized_aura_diff": None,
        "package_metadata": json.loads((pkg_root / "pypi_metadata.json").read_text())
    }

    n_tags = None
    o_tags = None

    if (orig_diff:=results.original_diffoscope):
        combined["original_diffoscope"] = json.loads(orig_diff.read_text())

    if (orig_adiff:=results.aura_diff):
        combined["original_aura_diff"] = json.loads(orig_adiff.read_text())
        o_tags = extract_tags(combined["original_aura_diff"])
        combined["original_tags"] = list(o_tags)
        combined["results"]["original"] = extract_reasons_from_tags(o_tags)

    if (norm_diff:=results.normalized_diffoscope):
        combined["normalized_diffoscope"] = json.loads(norm_diff.read_text())

    if (norm_adiff:=results.normalized_aura_diff):
        combined["normalized_aura_diff"] = json.loads(norm_adiff.read_text())
        n_tags = extract_tags(combined["normalized_aura_diff"])
        combined["normalized_tags"] = list(n_tags)
        combined["results"]["normalized"] = extract_reasons_from_tags(n_tags)

    if (md5s:=results.checksums):
        combined["checksums"] = (checksums:=json.loads(md5s.read_text()))

        combined["results"]["reproducible"] = (checksums["original"] == checksums["repacked"])
        combined["results"]["normalized_reproducible"] = (checksums["normalized_original"] == checksums["normalized_repacked"])
    else:
        combined["results"]["reproducible"] = None
        combined["results"]["normalized_reproducible"] = None

    if n_tags is not None and o_tags is not None:
        diff_tags = o_tags - n_tags

        combined["normalization_removed_tags"] = list(diff_tags)
        combined["results"]["normalization_effects"] = extract_reasons_from_tags(diff_tags)

    with (results.data_dir / "reproducible_results.json").open("w") as fd:
        fd.write(json.dumps(combined))


def extract_reasons_from_tags(tags: t.Set[str]) -> dict:
    reasons = {
        "archive_metadata": False,
        "packaging_tools": False,
        "timestamps": False,
        "permissions": False,
        "unknown": False,
        "distribution_metadata": False,
        "distribution_description": False,
        "distribution_headers": False
    }

    if "non-reproducibility:tooling" in tags:
        reasons["packaging_tools"] = True

    if "non-reproducibility:metadata:payload:normalization" in tags:
        reasons["distribution_metadata"] = True
        reasons["distribution_description"] = True

    if "non-reproducibility:metadata:key-value" in tags:
        reasons["distribution_metadata"] = True
        reasons["distribution_headers"] = True

    if "non-reproducibility:metadata" in tags:
        reasons["archive_metadata"] = True

    if "non-reproducibility:zip:timestamp" in tags:
        reasons["timestamps"] = True

    if "non-reproducibility:zip:external-attributes" in tags:
        reasons["permissions"] = True

    if "non-reproducibility:metadata:payload:unknown" in tags:
        reasons["distribution_metadata"] = True

    if "non-reproducibility:unknown" in tags:
        reasons["unknown"] = True

    return reasons


def extract_tags(aura_diff: dict) -> t.Set[str]:
    tags = set()

    for detections in aura_diff["detections"]:
        for tag in detections["tags"]:
            tags |= unwind_tag(tag)

    return tags


def unwind_tag(tag) -> t.Set[str]:
    tags = set()
    split_tag = tag.split(":")

    for idx in range(1, len(split_tag)+1):
        tags.add(":".join(split_tag[:idx]))

    return tags
