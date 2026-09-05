from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('judge', '0230_contest_category_groups'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contestcategory',
            name='contests',
            field=models.ManyToManyField(
                blank=True,
                help_text='Selected organization and group members can view assigned private or unpublished contests. '
                          'Making the category public does not publish its contests.',
                related_name='categories',
                to='judge.contest',
                verbose_name='contests',
            ),
        ),
    ]
