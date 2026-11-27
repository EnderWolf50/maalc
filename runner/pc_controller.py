"""The PC window controller (#940, spec #922 D4-D6) as MaaFramework's custom controller: runner/pc.py's Controller,
whose methods answer MaaFramework's callbacks. Its own module, for it imports MaaFramework: runner/framework.py imports
it once the install's maafw/ is known."""
from __future__ import annotations

from maa.controller import CustomController

from runner.pc import Controller, win32_controller


class PcController(Controller, CustomController):
    def __init__(self, hwnd, windows, inner=win32_controller):
        CustomController.__init__(self)
        Controller.__init__(self, hwnd, windows, inner)
