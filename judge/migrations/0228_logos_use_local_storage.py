import django.core.validators
from django.core.files.storage import default_storage
from django.db import migrations, models

import judge.models.interface
import judge.models.profile
import judge.utils.logo_storage


def copy_existing_logos_to_local_storage(apps, schema_editor):
    """Preserve logos uploaded before the fields switched away from S3."""
    local_storage = judge.utils.logo_storage.local_logo_storage
    logo_fields = (
        (apps.get_model('judge', 'Organization'), 'logo'),
        (apps.get_model('judge', 'SiteBranding'), 'logo'),
    )

    for model, field_name in logo_fields:
        for instance in model.objects.exclude(**{field_name: ''}).iterator():
            name = getattr(instance, field_name).name
            if not name or local_storage.exists(name):
                continue
            if not default_storage.exists(name):
                continue
            with default_storage.open(name, 'rb') as source:
                local_storage.save(name, source)


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0227_site_branding'),
    ]

    operations = [
        migrations.RunPython(copy_existing_logos_to_local_storage, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='organization',
            name='logo',
            field=models.ImageField(
                blank=True,
                help_text="Upload a PNG image to use as this organization's navbar logo.",
                storage=judge.utils.logo_storage.LocalLogoStorage(),
                upload_to=judge.models.profile.organization_logo_upload_path,
                validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['png'])],
                verbose_name='organization logo',
            ),
        ),
        migrations.AlterField(
            model_name='sitebranding',
            name='logo',
            field=models.ImageField(
                blank=True,
                help_text='Upload a PNG image for the navbar. Clear it to restore the default site logo.',
                storage=judge.utils.logo_storage.LocalLogoStorage(),
                upload_to=judge.models.interface.site_logo_upload_path,
                validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['png'])],
                verbose_name='site logo',
            ),
        ),
    ]
