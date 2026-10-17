from gigachat import GigaChat

CREDENTIALS = "MDFhMTNiMjAtODU0ZC03MzRjLTgwYjQtY2VhOGEzMzE1MGY1OjIwYjlmMGFjLWUwZDYtNGRlYy1iNDBmLTc5NTBiZTkxYmNlZQ=="

print("Получаю список моделей...\n")

try:
    with GigaChat(
        credentials=CREDENTIALS,
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        verify_ssl_certs=False,
        timeout=30,
    ) as client:
        models = client.get_models()
        print("=== СЫРОЙ СПИСОК ===")
        print(models)
        print()
        print("=== ПО КАЖДОЙ МОДЕЛИ ===")
        for m in models.data:
            print(m)
            print("---")
except Exception as e:
    print("=== ОШИБКА ===")
    print(type(e).__name__)
    print(e)