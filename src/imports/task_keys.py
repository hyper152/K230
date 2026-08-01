"""K0/K1/K2 debouncing and single/double-click event detection."""

from machine import Pin, FPIOA
from time import ticks_ms, ticks_diff, ticks_add
from .config import (
    key0_pin, key1_pin, key2_pin,
    key_debounce_ms, key_double_click_ms,
)


class TaskKeyController:
    """Non-blocking K0/K1/K2 single/double-click reader."""

    def __init__(self):
        fpioa = FPIOA()
        pins = (key0_pin, key1_pin, key2_pin)
        active_levels = (0, 0, 1)
        pulls = (Pin.PULL_UP, Pin.PULL_UP, Pin.PULL_DOWN)
        self.keys = []
        now = ticks_ms()
        for index in range(3):
            pin_num = pins[index]
            fpioa.set_function(pin_num, getattr(FPIOA, "GPIO{}".format(pin_num)))
            pin = Pin(pin_num, Pin.IN, pull=pulls[index], drive=7)
            pressed = pin.value() == active_levels[index]
            self.keys.append({
                "pin": pin,
                "active": active_levels[index],
                "raw": pressed,
                "stable": pressed,
                "changed": now,
                "clicks": 0,
                "deadline": now,
            })

    def poll(self, now):
        event = None
        for index in range(3):
            key = self.keys[index]
            pressed = key["pin"].value() == key["active"]
            if pressed != key["raw"]:
                key["raw"] = pressed
                key["changed"] = now

            if (pressed != key["stable"] and
                    ticks_diff(now, key["changed"]) >= key_debounce_ms):
                key["stable"] = pressed
                if (pressed and key["clicks"] == 1 and
                        ticks_diff(now, key["deadline"]) <= 0):
                    key["clicks"] = 2
                if not pressed:
                    if key["clicks"] == 2:
                        event = (index, 2)
                        key["clicks"] = 0
                    elif key["clicks"] == 0:
                        key["clicks"] = 1
                        key["deadline"] = ticks_add(now, key_double_click_ms)

            if (key["clicks"] == 1 and not key["stable"] and
                    ticks_diff(now, key["deadline"]) > 0):
                event = (index, 1)
                key["clicks"] = 0
        return event
