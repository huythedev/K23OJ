from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0214_update_language_extensions'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemtestcase',
            name='is_sample',
            field=models.BooleanField(default=False, verbose_name='case is sample?'),
        ),
    ]
