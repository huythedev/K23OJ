from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0228_logos_use_local_storage'),
    ]

    operations = [
        migrations.AddField(
            model_name='contestcategory',
            name='is_public',
            field=models.BooleanField(
                default=True,
                help_text='Used only when no organizations are selected. Private categories are visible to their creator.',
                verbose_name='publicly visible',
            ),
        ),
        migrations.AddField(
            model_name='contestcategory',
            name='organizations',
            field=models.ManyToManyField(
                blank=True,
                help_text='When selected, only members of these organizations may view this category.',
                to='judge.Organization',
                verbose_name='organizations',
            ),
        ),
    ]
