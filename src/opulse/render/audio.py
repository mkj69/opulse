"""Notes and melodies as sound: a small additive synthesiser, WAV and MIDI writers.

A note is a MIDI number 0 to 127 (``{"t": "note", "v": 60}``; 60 is C4). A melody is a
sequence of pitches with positive integer beat durations
(``{"t": "melody", "v": [{"p": 60, "d": 1}, ...]}``). One beat lasts
``round(sample_rate * 60 / bpm)`` samples, so a melody of ``n`` beats has exactly
``n`` times that many samples. The synthesis uses fixed float64 arithmetic and no
randomness, so equal inputs give equal bytes.
"""

from __future__ import annotations

import io
import struct
import wave

import numpy as np

SAMPLE_RATE = 16000
BPM = 120


def melody_notes(value) -> list[tuple[int, int]]:
    """``(pitch, beats)`` pairs from a melody payload (dicts with p and d, or pairs)."""
    notes = []
    for item in value:
        pitch, beats = (item["p"], item["d"]) if isinstance(item, dict) else item
        if type(pitch) is not int or not 0 <= pitch <= 127:
            raise ValueError("a pitch is a MIDI integer from 0 through 127")
        if type(beats) is not int or beats < 1:
            raise ValueError("a duration is a positive integer number of beats")
        notes.append((pitch, beats))
    return notes


def beat_samples(sample_rate: int = SAMPLE_RATE, bpm: float = BPM) -> int:
    return round(sample_rate * 60.0 / bpm)


def frequency(pitch: int) -> float:
    return 440.0 * 2.0 ** ((pitch - 69) / 12.0)


def _tone(pitch: int, length: int, sample_rate: int) -> np.ndarray:
    """One soft note: three harmonics, a short attack, a gentle decay and a release to silence."""
    t = np.arange(length, dtype=np.float64) / sample_rate
    f = frequency(pitch)
    wave_ = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t)
             + 0.12 * np.sin(6 * np.pi * f * t)) / 1.47
    envelope = 0.55 + 0.45 * np.exp(-3.0 * t)
    attack = min(length, int(0.01 * sample_rate))
    release = min(length, int(0.06 * sample_rate))
    if attack:
        envelope[:attack] *= np.arange(attack) / attack
    if release:
        envelope[length - release:] *= np.arange(release, 0, -1) / release
    return wave_ * envelope


def melody_samples(value, sample_rate: int = SAMPLE_RATE, bpm: float = BPM,
                   volume: float = 0.4) -> np.ndarray:
    """Signed 16-bit mono samples for a melody payload."""
    step = beat_samples(sample_rate, bpm)
    parts = [_tone(pitch, beats * step, sample_rate) for pitch, beats in melody_notes(value)]
    signal = np.concatenate(parts) if parts else np.zeros(0)
    return np.round(np.clip(signal * volume, -1.0, 1.0) * 32767).astype("<i2")


def wav_bytes(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as sink:
        sink.setnchannels(1)
        sink.setsampwidth(2)
        sink.setframerate(sample_rate)
        sink.writeframes(np.asarray(samples, dtype="<i2").tobytes())
    return buffer.getvalue()


def melody_wav(value, sample_rate: int = SAMPLE_RATE, bpm: float = BPM) -> bytes:
    """WAV bytes (mono, 16-bit) for a melody payload."""
    return wav_bytes(melody_samples(value, sample_rate, bpm), sample_rate)


def note_wav(pitch: int, beats: int = 1, sample_rate: int = SAMPLE_RATE, bpm: float = BPM) -> bytes:
    """WAV bytes for a single note held for ``beats`` beats."""
    return melody_wav([(pitch, beats)], sample_rate, bpm)


def _varlen(number: int) -> bytes:
    out = [number & 0x7F]
    number >>= 7
    while number:
        out.append((number & 0x7F) | 0x80)
        number >>= 7
    return bytes(reversed(out))


def melody_midi(value, bpm: float = BPM, ticks_per_beat: int = 480, velocity: int = 80) -> bytes:
    """A format 0 standard MIDI file playing the melody on channel 1."""
    track = b"\x00\xff\x51\x03" + round(60_000_000 / bpm).to_bytes(3, "big")
    for pitch, beats in melody_notes(value):
        track += b"\x00" + bytes((0x90, pitch, velocity))
        track += _varlen(beats * ticks_per_beat) + bytes((0x80, pitch, 0))
    track += b"\x00\xff\x2f\x00"
    return (b"MThd" + struct.pack(">IHHH", 6, 0, 1, ticks_per_beat)
            + b"MTrk" + struct.pack(">I", len(track)) + track)
