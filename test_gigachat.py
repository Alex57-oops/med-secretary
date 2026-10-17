from gigachat import GigaChat

CREDENTIALS = "MDFhMTNiMjAtODU0ZC03MzRjLTgwYjQtY2VhOGEzMzE1MGY1OjIwYjlmMGFjLWUwZDYtNGRlYy1iNDBmLTc5NTBiZTkxYmNlZQ=="

print("Подключаюсь к GigaChat-3-Pro...\n")

try:
    with GigaChat(
        credentials=CREDENTIALS,
        scope="GIGACHAT_API_PERS",
        model="GigaChat-3-Pro",
        verify_ssl_certs=False,
        timeout=60,
    ) as client:
        response = client.chat("Скажи одним предложением: ты работаешь?")
        print("=== ОТВЕТ ===")
        print(response.choices[0].message.content)
        print("=== КОНЕЦ ===")
except Exception as e:
    print("=== ОШИБКА ===")
    print(type(e).__name__)
    print(e)