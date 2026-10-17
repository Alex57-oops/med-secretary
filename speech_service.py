"""
Распознавание речи через Vosk + конвертация через ffmpeg напрямую.
"""

import wave
import json
import os
import subprocess
from vosk import Model, KaldiRecognizer, SetLogLevel
import imageio_ffmpeg

SetLogLevel(-1)

MODEL_PATH = "vosk-model-small-ru-0.22"
_model = None
_ffmpeg_path = None


def _get_model():
    global _model
    if _model is None:
        _model = Model(MODEL_PATH)
    return _model


def _get_ffmpeg():
    global _ffmpeg_path
    if _ffmpeg_path is None:
        _ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    return _ffmpeg_path


def convert_to_wav(input_path, output_path):
    ffmpeg = _get_ffmpeg()
    cmd = [
        ffmpeg, '-y',
        '-i', input_path,
        '-ar', '16000',
        '-ac', '1',
        '-acodec', 'pcm_s16le',
        '-f', 'wav',
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr[-500:]}")


def recognize_wav(wav_path):
    model = _get_model()
    wf = wave.open(wav_path, "rb")
    rec = KaldiRecognizer(model, wf.getframerate())
    result_text = []

    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            res = json.loads(rec.Result())
            if res.get("text"):
                result_text.append(res["text"])

    final = json.loads(rec.FinalResult())
    if final.get("text"):
        result_text.append(final["text"])

    wf.close()
    return " ".join(result_text).strip()


def recognize_audio(input_path):
    wav_path = os.path.splitext(input_path)[0] + "_converted.wav"
    try:
        convert_to_wav(input_path, wav_path)
        text = recognize_wav(wav_path)
        return text
    finally:
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass