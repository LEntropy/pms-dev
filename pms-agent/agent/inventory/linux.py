"""Linux software inventory collection via dpkg, rpm, and snap."""
import subprocess
import logging
from dataclasses import dataclass

logger = logging.getLogger("pms-agent")


@dataclass
class InstalledPackage:
    raw_name: str
    version: str
    install_path: str | None = None
    vendor: str | None = None


def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.stdout
    except Exception as exc:
        logger.debug("Command %s failed: %s", cmd, exc)
        return ""


def collect_dpkg() -> list[InstalledPackage]:
    output = _run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Installed-Size}\n"])
    packages = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            packages.append(InstalledPackage(raw_name=parts[0], version=parts[1]))
    return packages


def collect_rpm() -> list[InstalledPackage]:
    output = _run(["rpm", "-qa", "--queryformat", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{VENDOR}\n"])
    packages = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            packages.append(InstalledPackage(
                raw_name=parts[0],
                version=parts[1],
                vendor=parts[2] if len(parts) > 2 else None,
            ))
    return packages


def collect_snap() -> list[InstalledPackage]:
    output = _run(["snap", "list"])
    packages = []
    for line in output.splitlines()[1:]:  # skip header
        parts = line.split()
        if len(parts) >= 2:
            packages.append(InstalledPackage(raw_name=parts[0], version=parts[1]))
    return packages


def collect_all() -> list[InstalledPackage]:
    packages: list[InstalledPackage] = []
    packages.extend(collect_dpkg())
    if not packages:
        packages.extend(collect_rpm())
    packages.extend(collect_snap())
    seen = set()
    deduped = []
    for pkg in packages:
        key = (pkg.raw_name, pkg.version)
        if key not in seen:
            seen.add(key)
            deduped.append(pkg)
    return deduped
