import http.client
import unittest
from app.core.text import database_text, error_text
class TextTests(unittest.TestCase):
    def test_original_scan45_error_is_safe_for_postgres(self):
        message=error_text(http.client.BadStatusLine('\x15\x03\x03\x00\x02\x02'))
        self.assertNotIn('\x00',message)
        self.assertIn('BadStatusLine',message)
        self.assertIn('\\x00',message)
    def test_normal_strings_are_preserved(self):
        self.assertEqual(database_text('Обычная ошибка'),'Обычная ошибка')
        self.assertEqual(database_text('hello\x00world'), 'hello\\x00world')
        self.assertIsNone(database_text(None))
