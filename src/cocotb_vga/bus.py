"""Signal-binding adapters: turn DUT handles into per-cycle VGA samples.

A *bus* object only needs a ``sample()`` method returning either

* ``(hs, vs, r, g, b)`` — sync levels as 0/1 and colors scaled to 8 bit, or
* ``None`` — when a signal is unresolvable (``x``/``z``), e.g. before reset.

The adapters read plain ``handle.value`` attributes, so they work with both
cocotb 1.x (BinaryValue) and 2.x (LogicArray) and can be unit-tested with
fake signal objects.
"""

from __future__ import annotations


def bit_slice(value: int, width: int) -> int:
    """ Map the value based on how many bits are sliced from it.
        quick and easy method of dealing with DAC vs RGB bit depth.
    """
    if width <= 0:
        raise ValueError("channel width must be >= 1")
    if width >= 8:
        return value >> (width - 8)
    return value << (8 - width)


class TinyVGA:
    """The `Tiny VGA Pmod <https://github.com/mole99/tiny-vga>`_ pinout,
    packed on a single 8-bit output (``uo_out``).

    On the Tiny Tapeout board, ``uo_out[0..3]`` drive Pmod pins 1-4 and
    ``uo_out[4..7]`` drive Pmod pins 7-10, so the Tiny VGA spec maps to:

    ==========  ==  ==  ==  ==  ==  ==  ==  ==
    uo_out bit   0   1   2   3   4   5   6   7
    Pmod pin     1   2   3   4   7   8   9  10
    signal      R1  G1  B1  VS  R0  G0  B0  HS
    ==========  ==  ==  ==  ==  ==  ==  ==  ==

    R1/G1/B1 are the most significant and R0/G0/B0 the least significant
    color bits. Equivalent to the Verilog
    ``assign uo_out = {hsync, b[0], g[0], r[0], vsync, b[1], g[1], r[1]};``
    used by the TT VGA playground.
    """

    def __init__(self, signal):
        self._signal = signal
        lut = []
        for v in range(256):
            r = (((v >> 0) & 1) << 1) | ((v >> 4) & 1)
            g = (((v >> 1) & 1) << 1) | ((v >> 5) & 1)
            b = (((v >> 2) & 1) << 1) | ((v >> 6) & 1)
            lut.append((
                (v >> 7) & 1,           # hsync level
                (v >> 3) & 1,           # vsync level
                (r * 255) // ((1 << 2) - 1),
                (g * 255) // ((1 << 2) - 1),
                (b * 255) // ((1 << 2) - 1),
            ))
        self._lut = lut

    def sample(self):
        try:
            return self._lut[int(self._signal.value)]
        except ValueError:
            return None  # x/z on the bus


class VGASignals:
    """Generic adapter for designs with separate hsync/vsync/r/g/b signals.

    Channel widths are taken from ``len(signal)`` and can be overridden with
    ``red_width``/``green_width``/``blue_width`` (useful when a channel is a
    slice of a wider bus). Value mapping can be customized with a function
    that takes in the value, and width and returns an integer. Default
    is bit slice.
    """

    def __init__(self, *, hsync, vsync, red, green, blue,
                 red_width=None, green_width=None, blue_width=None, value_map=bit_slice):
        self._hsync = hsync
        self._vsync = vsync
        self._channels = []
        for sig, width in ((red, red_width), (green, green_width), (blue, blue_width)):
            w = width if width is not None else len(sig)
            lut = tuple(value_map(v, w) for v in range(1 << w))
            self._channels.append((sig, lut))

    def sample(self):
        try:
            hs = int(self._hsync.value)
            vs = int(self._vsync.value)
            rgb = tuple(lut[int(sig.value)] for sig, lut in self._channels)
        except ValueError:
            return None  # x/z on at least one signal
        return (hs, vs) + rgb
