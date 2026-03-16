from django.conf import settings

import requests

VERIFY_URL = 'https://www.google.com/recaptcha/api/siteverify'


def recaptcha_v3_enabled():
    return bool(settings.RECAPTCHA_V3_SITE_KEY and settings.RECAPTCHA_V3_SECRET_KEY)


def verify_recaptcha_v3(token, remoteip=None, expected_action=None):
    if not recaptcha_v3_enabled():
        return True, None

    if not token:
        return False, 'missing-input-response'

    payload = {
        'secret': settings.RECAPTCHA_V3_SECRET_KEY,
        'response': token,
    }
    if remoteip:
        payload['remoteip'] = remoteip

    try:
        response = requests.post(VERIFY_URL, data=payload, timeout=5)
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError):
        return False, 'verification-unavailable'

    if not result.get('success', False):
        return False, ','.join(result.get('error-codes', [])) or 'verification-failed'

    if expected_action and result.get('action') != expected_action:
        return False, 'action-mismatch'

    if result.get('score', 0) < settings.RECAPTCHA_V3_MIN_SCORE:
        return False, 'low-score'

    return True, None
