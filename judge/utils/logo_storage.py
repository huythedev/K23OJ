from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.urls import reverse
from django.utils.deconstruct import deconstructible


@deconstructible
class LocalLogoStorage(FileSystemStorage):
    """Filesystem storage that never falls through to the S3 default backend."""

    def __init__(self):
        super().__init__(location=settings.LOCAL_LOGO_ROOT)

    def url(self, name):
        return reverse('local_logo', kwargs={'path': name})


local_logo_storage = LocalLogoStorage()
