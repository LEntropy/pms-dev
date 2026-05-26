import platform
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.inventory.linux import InstalledPackage


def collect_software() -> list:
    if platform.system() == "Windows":
        from agent.inventory.windows import collect_all
    else:
        from agent.inventory.linux import collect_all
    return collect_all()
