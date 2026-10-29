"""Pitch atoms and a reproducible showcase for the sound world.

Notes are MIDI integers 0 through 127. Melodies are sequences of
``(pitch, duration)`` pairs; durations are positive integer beats.
"""

from __future__ import annotations

from pathlib import Path

from opulse.core.primitives import CUSTOM, register_primitive
from opulse.core.semantics import NAN

PITCH_ATOMS = (
    "pitch_transpose", "pitch_octave_up", "pitch_octave_down", "pitch_interval",
    "pitch_invert", "pitch_retrograde", "pitch_scale_step", "pitch_major_triad",
    "pitch_minor_triad", "pitch_repeat", "pitch_concat", "pitch_melody_equal",
    "pitch_note_equal",
)

_NAMES = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")
_KEYS = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
         "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
         "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
_SCALES = {"major": (0, 2, 4, 5, 7, 9, 11),
           "minor": (0, 2, 3, 5, 7, 8, 10)}


def note_name(midi: int) -> str:
    """Scientific note name, where MIDI 60 is C4."""
    if not isinstance(midi, int) or not 0 <= midi <= 127:
        raise ValueError("a MIDI note is an integer from 0 through 127")
    return f"{_NAMES[midi % 12]}{midi // 12 - 1}"


def melody_text(melody) -> str:
    """A readable melody with integer beat durations."""
    return " ".join(f"{note_name(p)}:{d}" for p, d in melody)


def _note(value):
    return value if 0 <= value <= 127 else NAN


def _melody(values):
    notes = tuple(values)
    return notes if all(0 <= p <= 127 and d > 0 for p, d in notes) else NAN


def register_pitch(key: str | int = "C", scale: str = "major") -> None:
    """Register pitch atoms. Call with the same key in each process using them."""
    if isinstance(key, str):
        if key not in _KEYS:
            raise ValueError(f"unknown pitch key {key!r}")
        tonic = _KEYS[key]
        key_label = key
    elif isinstance(key, int) and not isinstance(key, bool) and 0 <= key < 12:
        tonic = key
        key_label = note_name(60 + key)[:-1]
    else:
        raise ValueError("key must be a pitch class from 0 through 11 or a note name")
    if scale not in _SCALES:
        raise ValueError("scale must be major or minor")
    degrees = _SCALES[scale]

    def step(p):
        return next((_note(q) for q in range(p + 1, 128)
                     if (q - tonic) % 12 in degrees), NAN)

    def step_z3(p):
        z3 = __import__("z3")
        result = p + 12
        for distance in range(12, 0, -1):
            in_scale = z3.Or(*[((p + distance - tonic) % 12) == degree
                               for degree in degrees])
            result = z3.If(in_scale, p + distance, result)
        return result

    specs = (
        ("pitch_transpose", "♯", lambda p, n: _note(p + n), ("note", "int"), "note",
         "a ♯ b moves MIDI note a by b semitones; a result outside 0 through 127 gives NaN.",
         lambda p, n: p + n),
        ("pitch_octave_up", "⇈", lambda p: _note(p + 12), ("note",), "note",
         "a ⇈ raises MIDI note a by 12 semitones; a result above 127 gives NaN.",
         lambda p: p + 12),
        ("pitch_octave_down", "⇊", lambda p: _note(p - 12), ("note",), "note",
         "a ⇊ lowers MIDI note a by 12 semitones; a result below 0 gives NaN.",
         lambda p: p - 12),
        ("pitch_interval", "⟷", lambda a, b: b - a, ("note", "note"), "int",
         "a ⟷ b is the signed number of semitones from note a to note b.", lambda a, b: b - a),
        ("pitch_invert", "⇅", lambda m, p: _melody((2 * p - n, d) for n, d in m),
         ("melody", "note"), "melody",
         "a ⇅ b reflects every pitch in melody a around MIDI note b and keeps durations; an out of range pitch gives NaN.", None),
        ("pitch_retrograde", "⟲", lambda m: tuple(reversed(m)), ("melody",), "melody",
         "a ⟲ reverses the order of melody a, keeping each note with its duration.", None),
        ("pitch_scale_step", "♬", step, ("note",), "note",
         f"a ♬ is the next higher note in {key_label} {scale}; no higher MIDI note gives NaN.",
         step_z3),
        ("pitch_major_triad", "△", lambda p: _melody(((p, 1), (p + 4, 1), (p + 7, 1))),
         ("note",), "melody",
         "a △ builds a three note major triad at MIDI note a with intervals 0, 4, 7 and one beat each; an out of range pitch gives NaN.", None),
        ("pitch_minor_triad", "▽", lambda p: _melody(((p, 1), (p + 3, 1), (p + 7, 1))),
         ("note",), "melody",
         "a ▽ builds a three note minor triad at MIDI note a with intervals 0, 3, 7 and one beat each; an out of range pitch gives NaN.", None),
        ("pitch_repeat", "⥁", lambda m, n: m * n if 0 <= n <= 16 else NAN,
         ("melody", "int"), "melody",
         "a ⥁ b repeats melody a b times for b from 0 through 16; other counts give NaN.", None),
        ("pitch_concat", "⋈", lambda a, b: (*a, *b), ("melody", "melody"), "melody",
         "a ⋈ b plays melody a followed by melody b.", None),
        ("pitch_melody_equal", "≎", lambda a, b: a == b,
         ("melody", "melody"), "bool",
         "a ≎ b is true when melodies a and b have the same pitches and beat durations.", None),
        ("pitch_note_equal", "≐", lambda a, b: a == b,
         ("note", "note"), "bool",
         "a ≐ b is true when the two MIDI notes have the same pitch.", lambda a, b: a == b),
    )
    for name, symbol, compute, inputs, output, rule, encode in specs:
        # Replacing an existing registration allows a different key in a new set.
        if name in CUSTOM and name != "pitch_scale_step":
            continue
        register_primitive(name, symbol, compute, n_ary=len(inputs), rule=rule,
                           parameter_types=inputs, result_type=output, z3=encode)


def _value(value, kind: str | None = None):
    if value is NAN:
        return {"t": "nan"}
    if isinstance(value, bool):
        return {"t": "bool", "v": value}
    if isinstance(value, (tuple, list)):
        return {"t": "melody", "v": [{"p": p, "d": d} for p, d in value]}
    return {"t": "note" if kind == "note" else "int", "v": value}


def showcase_registry(seed: int = 35):
    """A seeded pitch operator set grown over three layers."""
    from opulse.config import Settings
    from opulse.core.operator import Operator
    from opulse.core.presets import PRESETS
    from opulse.core.primitives import atom_records
    from opulse.core.registry import OperatorRegistry
    from opulse.worlds.showcase import grow

    register_pitch()
    settings = Settings.from_dict({"recursion": {"style": "direct", "direct_bound": 4},
                                   "operators": {"reject_dead_branches": False}})
    registry = OperatorRegistry(Operator.from_dict(r) for r in atom_records(PRESETS["pitch"], seed=seed))
    return settings, registry, grow("pitch", settings, registry, seed)


def _pitch_text(value, kind):
    if kind == "note" and isinstance(value, int) and 0 <= value <= 127:
        name = note_name(value)
        return name, name
    if kind == "melody" and isinstance(value, tuple):
        if value:
            notes = "[" + melody_text(value) + "]"
            return notes, f"旋律 {notes}"
        return "the empty melody", "空旋律"
    return None


def showcase_spec():
    from opulse.worlds.showcase import WHY, WorldSpec, _literal_inputs

    melodies = (((60, 1), (64, 1), (67, 2)), ((72, 2), (71, 1), (69, 1), (67, 4)), ((55, 1),), (),
                ((62, 1), (65, 2)), ((48, 2), (55, 1), (60, 1), (64, 1), (67, 2)), ((120, 1), (127, 1)),
                ((67, 1), (67, 1), (69, 2), (67, 2), (72, 2), (71, 4)))

    def values(kind):
        if kind == "note":
            return (60, 67, 72, 48, 64, 127, 55, 0, 84, 62)
        if kind == "melody":
            return melodies
        if kind == "bool":
            return (True, False)
        return (2, 0, 5, -3, 7, 12, 1, -12, 3, 4, -4, 17)

    def settings_rows(settings):
        return [("register_pitch(key, scale)", "C, major", "The key and scale used by the scale step ♬.",
                 "音阶上行 ♬ 使用的调和音阶。"),
                ("recursion.direct_bound", settings.recursion.direct_bound,
                 "A recursive call repeats its step at most this many times; larger counts give NaN.",
                 "递归最多重复这么多步，更大的次数得 NaN。")]

    def step_extra(step, record, tools):
        value = record.get("value")
        if value and value.get("t") in ("note", "melody"):
            record["sound"] = value

    return WorldSpec(
        "pitch", "Pitch", "音高", "sound", build=showcase_registry, values=values, encode=_value,
        atom_zh={"add": "a + b 是整数加法。", "sub": "a - b 是整数减法。",
                 "mod": "a % b 是余数，符号与 a 相同，b = 0 时得 NaN。", "neg": "- a 是 a 的相反数。",
                 **_ATOM_ZH},
        atom_examples={"add": (2, 3), "sub": (4, 1), "mod": (7, 3), "neg": (3,),
                       "pitch_transpose": (60, 7), "pitch_octave_up": (60,), "pitch_octave_down": (72,),
                       "pitch_interval": (60, 67), "pitch_invert": (melodies[0], 64),
                       "pitch_retrograde": (melodies[0],), "pitch_scale_step": (64,),
                       "pitch_major_triad": (60,), "pitch_minor_triad": (57,), "pitch_repeat": (melodies[2], 3),
                       "pitch_concat": (melodies[2], melodies[4]), "pitch_melody_equal": (melodies[0], melodies[0]),
                       "pitch_note_equal": (60, 72)},
        domain=((("A note is a MIDI number from 0 to 127; 60 is C4. A melody is a list of notes with "
                 "durations in beats."), "音是 0 到 127 的 MIDI 编号，60 是 C4。旋律是一串带拍数的音。"),
                ("Integers give semitone steps, repeat counts and recursive counts.",
                 "整数用作半音数、重复次数和递归次数。")),
        settings=settings_rows, why=WHY, seed=35, value_text=_pitch_text, step_extra=step_extra,
        extra_inputs=_literal_inputs)


def export_world_showcase(world_name: str, out_path: str | Path) -> dict:
    """Write the pitch showcase (see :mod:`opulse.worlds.showcase`)."""
    if world_name != "pitch":
        raise ValueError("world_name must be 'pitch'")
    from opulse.worlds.showcase import export_spec

    return export_spec(showcase_spec(), out_path)


_ATOM_ZH = {
    "pitch_transpose": "a ♯ b 将音高 a 移动 b 个半音，超出 MIDI 范围时得到 NaN。",
    "pitch_octave_up": "a ⇈ 将音高 a 升高一个八度，超过 127 时得到 NaN。",
    "pitch_octave_down": "a ⇊ 将音高 a 降低一个八度，低于 0 时得到 NaN。",
    "pitch_interval": "a ⟷ b 是从音高 a 到 b 的有符号半音数。",
    "pitch_invert": "a ⇅ b 以音高 b 为轴翻转旋律 a 的每个音高，保留时值。",
    "pitch_retrograde": "a ⟲ 逆序排列旋律 a 的音符及其时值。",
    "pitch_scale_step": "a ♬ 是当前调式中比 a 高的下一个音。",
    "pitch_major_triad": "a △ 构成以 a 为根音、间隔为 0、4、7 个半音的大三和弦。",
    "pitch_minor_triad": "a ▽ 构成以 a 为根音、间隔为 0、3、7 个半音的小三和弦。",
    "pitch_repeat": "a ⥁ b 将旋律 a 重复 b 次，b 可取 0 到 16。",
    "pitch_concat": "a ⋈ b 依次连接旋律 a 和 b。",
    "pitch_melody_equal": "a ≎ b 在两段旋律的音高与时值完全相同时为真。",
    "pitch_note_equal": "a ≐ b 在两个 MIDI 音符的音高相同时为真。",
}
