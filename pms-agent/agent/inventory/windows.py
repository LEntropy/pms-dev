"""Windows software inventory collection via registry and WMI."""
import logging
from dataclasses import dataclass

logger = logging.getLogger("pms-agent")


@dataclass
class InstalledPackage:
    raw_name: str
    version: str
    install_path: str | None = None
    vendor: str | None = None


def collect_registry() -> list[InstalledPackage]:
    """Read installed software from Windows Uninstall registry keys."""
    try:
        import winreg
    except ImportError:
        logger.warning("winreg not available (not running on Windows)")
        return []

    packages = []
    uninstall_keys = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]

    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key_path in uninstall_keys:
            try:
                with winreg.OpenKey(root, key_path) as key:
                    count = winreg.QueryInfoKey(key)[0]
                    for i in range(count):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                def _get(name):
                                    try:
                                        return winreg.QueryValueEx(subkey, name)[0]
                                    except OSError:
                                        return None

                                display_name = _get("DisplayName")
                                version = _get("DisplayVersion")
                                if display_name and version:
                                    packages.append(InstalledPackage(
                                        raw_name=display_name,
                                        version=version,
                                        install_path=_get("InstallLocation"),
                                        vendor=_get("Publisher"),
                                    ))
                        except OSError:
                            continue
            except OSError:
                continue

    return packages


def collect_wmi() -> list[InstalledPackage]:
    """Collect via WMI Win32_Product (slower, more complete)."""
    try:
        import wmi
    except ImportError:
        return []

    packages = []
    try:
        c = wmi.WMI()
        for product in c.Win32_Product():
            if product.Name and product.Version:
                packages.append(InstalledPackage(
                    raw_name=product.Name,
                    version=product.Version,
                    vendor=product.Vendor,
                ))
    except Exception as exc:
        logger.debug("WMI collection failed: %s", exc)
    return packages


def collect_all() -> list[InstalledPackage]:
    packages = collect_registry()
    seen = {(p.raw_name, p.version) for p in packages}
    for p in collect_wmi():
        if (p.raw_name, p.version) not in seen:
            packages.append(p)
            seen.add((p.raw_name, p.version))
    return packages
