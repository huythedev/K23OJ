from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0222_merge_20260505_1433'),
    ]

    operations = [
        migrations.CreateModel(
            name='TestcaseDownloadLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('testcase_number', models.PositiveIntegerField(verbose_name='test case number')),
                ('file_type', models.CharField(choices=[('input', 'Input (.inp)'), ('output', 'Output (.out)')], max_length=6, verbose_name='downloaded file')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP address')),
                ('downloaded_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='download time')),
                ('problem', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='testcase_download_logs', to='judge.problem', verbose_name='problem')),
                ('requester', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='testcase_download_logs', to='judge.profile', verbose_name='downloaded by')),
                ('submission', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='testcase_download_logs', to='judge.submission', verbose_name='submission')),
                ('testcase', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='download_logs', to='judge.problemtestcase', verbose_name='test case')),
            ],
            options={
                'verbose_name': 'testcase download log',
                'verbose_name_plural': 'testcase download logs',
                'ordering': ('-downloaded_at',),
            },
        ),
    ]
