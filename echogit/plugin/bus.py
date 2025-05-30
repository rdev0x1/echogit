from collections import defaultdict
from typing import Callable


class HookBus:
    def __init__(self):
        self._hooks = defaultdict(list)

    def register(self, event: str, fn: Callable):
        self._hooks[event].append(fn)

    # return value is used on on_error
    def emit(self, event: str, **ctx):
        handled = False

        for fn in self._hooks[event]:
            try:
                result = fn(**ctx)
                handled = handled or result
            except Exception as e:
                self.emit("on_error", exception=e, **ctx)
        return handled


hook_bus = HookBus()
