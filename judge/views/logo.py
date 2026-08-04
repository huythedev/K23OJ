from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404
from django.views.decorators.http import require_safe

from judge.utils.logo_storage import local_logo_storage


@require_safe
def local_logo(request, path):
    """Serve public navbar logos from their dedicated local storage."""
    try:
        logo = local_logo_storage.open(path, 'rb')
    except (OSError, SuspiciousFileOperation):
        raise Http404

    response = FileResponse(logo, content_type='image/png')
    response['Cache-Control'] = 'public, max-age=31536000, immutable'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
