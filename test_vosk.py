import wave
import json
from vosk import Model, KaldiRecognizer

MODEL_PATH = "vosk-model-small-ru-0.22"

print("Загружаю модель...")
model = Model(MODEL_PATH)
print("Модель загружена.\n")

# Тестовый звук — создадим сами
# (пока проверим только, что модель грузится)
rec = KaldiRecognizer(model, 16000)
print("Готово! Распознаватель создан.")
print("Если ты видишь это сообщение — Vosk работает.")