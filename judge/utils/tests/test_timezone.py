from types import SimpleNamespace

from django.test import SimpleTestCase

from judge.timezone import TimezoneMiddleware


class TimezoneMiddlewareTest(SimpleTestCase):
    def test_legacy_saigon_timezone_uses_mysql_supported_name(self):
        request = SimpleNamespace(
            profile=SimpleNamespace(timezone='Asia/Saigon'),
        )

        user_timezone = TimezoneMiddleware().get_timezone(request)

        self.assertEqual(user_timezone.key, 'Asia/Ho_Chi_Minh')

