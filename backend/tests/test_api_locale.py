import unittest
from app.core.api_locale import english_requested, translate_error, add_error_code

class ApiLocaleTests(unittest.TestCase):
    def test_language_negotiation(self):
        for header in ('en','en-GB,en;q=0.8,ru;q=0.5','ru;q=0.1,en;q=0.9'):
            self.assertTrue(english_requested(header))
        for header in ('','ru','en;q=0,ru','ru,en;q=0.9','fr','en;q=invalid','en;q=0'):
            self.assertFalse(english_requested(header))
    def test_errors_and_parameters(self):
        self.assertEqual(translate_error('Скан не найден'),'Scan not found')
        self.assertEqual(translate_error('Некорректное имя хоста: Сервер'),'Invalid hostname: Сервер')
        self.assertEqual(translate_error('Очередь сканирования недоступна. Неудачный запуск сохранён как #42'),'The scan queue is unavailable. The failed run was saved as #42')
        self.assertEqual(translate_error('Value error, Время должно включать часовой пояс'),'Value error, The time must include a time zone')
    def test_unrecognized_diagnostics_remain_intact(self):
        self.assertEqual(translate_error('Nmap: timeout 600s'),'Nmap: timeout 600s')
        self.assertEqual(translate_error('Пользовательский текст'),'Пользовательский текст')

    def test_response_has_stable_code_and_correct_length(self):
        import json
        from starlette.responses import JSONResponse
        response=add_error_code(JSONResponse({'detail':'Скан не найден'},status_code=404),404)
        self.assertEqual(json.loads(response.body)['code'],'not_found')
        self.assertEqual(int(response.headers['content-length']),len(response.body))
        self.assertEqual(json.loads(response.body)['detail'],'Скан не найден')
