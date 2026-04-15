from django.core.validators import RegexValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0215_add_sample_testcase_field'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContestCategory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='category name')),
                ('slug', models.SlugField(max_length=64, unique=True, validators=[RegexValidator('^[a-z0-9_]+$', 'Category slug must be ^[a-z0-9_]+$')], verbose_name='category slug')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('contests', models.ManyToManyField(blank=True, related_name='categories', to='judge.contest', verbose_name='contests')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_contest_categories', to='judge.profile', verbose_name='created by')),
            ],
            options={
                'verbose_name': 'contest category',
                'verbose_name_plural': 'contest categories',
                'ordering': ('name',),
            },
        ),
    ]
