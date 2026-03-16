from django.conf import settings

import requests

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

    verify_url = 'https://%s/recaptcha/api/siteverify' % settings.RECAPTCHA_V3_API_DOMAIN

    try:
        response = requests.post(verify_url, data=payload, timeout=5)
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError):
        return False, 'verification-unavailable'

    if not result.get('success', False):
        return False, ','.join(result.get('error-codes', [])) or 'verification-failed'

    actual_action = result.get('action')
    if expected_action and actual_action != expected_action:
        return False, 'action-mismatch:%s' % (actual_action or 'missing')

    score = result.get('score')
    if score is None:
        return False, 'missing-score'
    if score < settings.RECAPTCHA_V3_MIN_SCORE:
        return False, 'low-score:%s' % score

    return True, None
