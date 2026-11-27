"""MaaFramework as the runner uses it: the install's maafw/ (its patched MaaFramework.dll), imported once the install is
known. The runner's tests hand Session a fake with the same methods."""
from __future__ import annotations

import os
from pathlib import Path


class Framework:
    def __init__(self, root: Path):
        if (root / "maafw").is_dir():  # before maa loads: the agent child inherits it too (agent/main.py)
            os.environ["MAAFW_BINARY_PATH"] = str(root / "maafw")
        from maa.tasker import Tasker
        from maa.toolkit import Toolkit

        Toolkit.init_option(str(root / "debug"))
        Tasker.set_save_on_error(True)

    def devices(self) -> list:
        from maa.toolkit import Toolkit

        return Toolkit.find_adb_devices()

    def controller(self, device):
        from maa.controller import AdbController

        return AdbController(device.adb_path, device.address, device.screencap_methods, device.input_methods,
                             device.config)

    def pc_controller(self, hwnd, windows):
        """The PC window controller of the game's window hwnd (runner/pc_controller.py)."""
        from runner.pc_controller import PcController

        return PcController(hwnd, windows)

    def resource(self):
        from maa.resource import Resource

        return Resource()

    def agent_client(self):
        from maa.agent_client import AgentClient

        return AgentClient()

    def tasker(self):
        from maa.tasker import Tasker

        return Tasker()
