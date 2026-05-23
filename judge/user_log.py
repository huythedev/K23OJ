import logging

from django.db import OperationalError
from django.utils.timezone import now

from judge.models import Profile

logger = logging.getLogger(__name__)


class LogUserAccessMiddleware(object):
    def __init__(self, get_response=None):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (hasattr(request, 'user') and request.user.is_authenticated and
                not getattr(request, 'no_profile_update', False)):
            updates = {'last_access': now()}

            # Decided on using REMOTE_ADDR as nginx will translate it to the external IP that hits it.
            if request.META.get('REMOTE_ADDR'):
                updates['ip'] = request.META.get('REMOTE_ADDR')
            try:
                Profile.objects.filter(user_id=request.user.pk).update(**updates)
            except OperationalError as exc:
                # Avoid 500s if the profile row is locked by another transaction.
                if getattr(exc, 'args', None) and exc.args[0] == 1205:
                    logger.warning('Profile update skipped due to lock wait timeout')
                else:
                    raise

        return response
