"""File-based model registry with versions and aliases. Local stand-in for Vertex Model Registry.

Layout: <root>/<model>/v<N>/{model.joblib,metrics.json} and <root>/<model>/aliases.json
"""
import json
import os
import shutil
import sys
from pathlib import Path

# Overridable so tests and the smoke script never touch the real registry.
ROOT = Path(os.environ.get("REGISTRY_DIR", "registry"))
DEPLOY = Path(os.environ.get("DEPLOY_DIR", "deployed"))  # what Compose mounts and serves


def _aliases_path(root, model):
    return Path(root) / model / "aliases.json"


def get_aliases(model, root=ROOT):
    p = _aliases_path(root, model)
    return json.loads(p.read_text()) if p.exists() else {}


def set_alias(model, alias, version, root=ROOT):
    if not (Path(root) / model / version).is_dir():
        raise ValueError(f"{model} has no version {version}")
    aliases = get_aliases(model, root)
    if alias == "champion" and aliases.get("champion") not in (None, version):
        aliases["previous_champion"] = aliases["champion"]  # remembered so rollback is one step
    aliases[alias] = version
    path = _aliases_path(root, model)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(aliases, indent=2))
    os.replace(tmp, path)  # atomic, so a reader never sees a truncated file


def promote(model, version=None, root=ROOT):
    """Make a version champion. With no version, promote the current candidate."""
    if version is None:
        version = get_aliases(model, root).get("candidate")
        if version is None:
            raise ValueError(f"{model} has no candidate to promote")
    set_alias(model, "champion", version, root)


def rollback(model, root=ROOT):
    """Point champion back at the previous champion."""
    previous = get_aliases(model, root).get("previous_champion")
    if previous is None:
        raise ValueError(f"{model} has no previous champion to roll back to")
    set_alias(model, "champion", previous, root)


def register(model, artifact_dir, root=ROOT):
    """Copy artifacts in as the next version. Returns the version string."""
    base = Path(root) / model
    base.mkdir(parents=True, exist_ok=True)
    n = 1 + max([int(p.name[1:]) for p in base.glob("v*") if p.is_dir() and p.name[1:].isdigit()], default=0)
    version = f"v{n}"
    shutil.copytree(artifact_dir, base / version)
    return version


def deploy(model, root=ROOT, target=DEPLOY):
    """Copy the champion into <target>/<model> with a VERSION file. Containers must be recreated to pick it up."""
    version = get_aliases(model, root).get("champion")  # read once so files and VERSION agree
    if version is None:
        raise ValueError(f"{model} has no champion to deploy")
    dest, staging, old = Path(target) / model, Path(target) / f"{model}.tmp", Path(target) / f"{model}.old"
    for p in (staging, old):
        shutil.rmtree(p, ignore_errors=True)
    shutil.copytree(Path(root) / model / version, staging)
    (staging / "VERSION").write_text(version)
    if dest.exists():
        dest.rename(old)
    try:
        staging.rename(dest)
    except OSError:
        if old.exists():
            old.rename(dest)  # put the previous deployment back
        raise
    shutil.rmtree(old, ignore_errors=True)
    return version


def get_metrics(model, alias, root=ROOT):
    """Metrics of the version an alias points at, or None if the alias is unset."""
    version = get_aliases(model, root).get(alias)
    return json.loads((Path(root) / model / version / "metrics.json").read_text()) if version else None


def model_dir(model, alias, root=ROOT):
    return Path(root) / model / get_aliases(model, root)[alias]


if __name__ == "__main__":
    usage = "usage: python -m src.registry promote <model> [version] | rollback <model> | deploy <model> | show <model>"
    if len(sys.argv) < 3 or sys.argv[1] not in {"promote", "rollback", "deploy", "show"}:
        print(usage, file=sys.stderr)
        sys.exit(2)
    cmd, model, *rest = sys.argv[1:]
    try:
        if cmd == "promote":
            promote(model, *rest)
        elif cmd == "rollback":
            rollback(model)
        elif cmd == "deploy":
            print(f"{model}: deployed champion {deploy(model)}")
        print(json.dumps(get_aliases(model), indent=2))
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
