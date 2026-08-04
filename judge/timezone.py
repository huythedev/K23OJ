from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection
from django.utils import timezone
from django.utils.timezone import make_aware, make_naive


# ``Asia/Saigon`` is a backwards-compatibility link in the IANA timezone
# database. It is still accepted by pytz (and is stored by older profiles),
# but some MySQL timezone-table installations only contain the canonical
# name. Django 5.2's admin date hierarchy performs timezone conversion in
# the database, where the legacy name would therefore produce NULL values.
TIMEZONE_ALIASES = {
    'Asia/Saigon': 'Asia/Ho_Chi_Minh',
}


class TimezoneMiddleware(object):
    def __init__(self, get_response=None):
        self.get_response = get_response

    def get_timezone(self, request):
        tzname = settings.DEFAULT_USER_TIME_ZONE
        if request.profile:
            tzname = request.profile.timezone
        tzname = TIMEZONE_ALIASES.get(tzname, tzname)
        return ZoneInfo(tzname)

    def __call__(self, request):
        with timezone.override(self.get_timezone(request)):
            return self.get_response(request)


def from_database_time(datetime):
    tz = connection.timezone
    if tz is None:
        return datetime
    return make_aware(datetime, tz)


def to_database_time(datetime):
    tz = connection.timezone
    if tz is None:
        return datetime
    return make_naive(datetime, tz)
