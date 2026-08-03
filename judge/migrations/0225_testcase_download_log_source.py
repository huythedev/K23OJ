from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0224_exams'),
    ]

    operations = [
        migrations.AddField(
            model_name='testcasedownloadlog',
            name='download_source',
            field=models.CharField(
                choices=[('submission', 'Submission status'), ('test_data', 'Test data editor')],
                default='submission',
                max_length=10,
                verbose_name='download source',
            ),
        ),
        migrations.AlterField(
            model_name='testcasedownloadlog',
            name='file_type',
            field=models.CharField(
                choices=[
                    ('input', 'Input (.inp)'),
                    ('output', 'Output (.out)'),
                    ('archive', 'Test data archive (.zip)'),
                ],
                max_length=7,
                verbose_name='downloaded file',
            ),
        ),
        migrations.AlterField(
            model_name='testcasedownloadlog',
            name='testcase_number',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='test case number'),
        ),
    ]
