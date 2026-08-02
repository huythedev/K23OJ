import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0223_testcase_download_log'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExamCategory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=64, unique=True, verbose_name='category name')),
                ('sort_order', models.IntegerField(db_index=True, default=0, verbose_name='sort order')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='active')),
            ],
            options={
                'verbose_name': 'exam category',
                'verbose_name_plural': 'exam categories',
                'ordering': ('sort_order', 'name'),
            },
        ),
        migrations.CreateModel(
            name='ExamProvince',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=64, unique=True, verbose_name='province name')),
                ('sort_order', models.IntegerField(db_index=True, default=0, verbose_name='sort order')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='active')),
            ],
            options={
                'verbose_name': 'exam province',
                'verbose_name_plural': 'exam provinces',
                'ordering': ('sort_order', 'name'),
            },
        ),
        migrations.CreateModel(
            name='ExamTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.CharField(db_index=True, max_length=64, unique=True, validators=[django.core.validators.RegexValidator('^[a-z0-9-]+$', 'Exam slug must contain lowercase letters, numbers, and hyphens only.')], verbose_name='exam slug')),
                ('name', models.CharField(db_index=True, max_length=200, verbose_name='exam name')),
                ('expected_count', models.PositiveIntegerField(default=0, verbose_name='expected problems')),
                ('year', models.PositiveIntegerField(blank=True, db_index=True, null=True, verbose_name='year')),
                ('exam_date', models.DateField(blank=True, db_index=True, null=True, verbose_name='exam date')),
                ('exam_type', models.CharField(blank=True, db_index=True, max_length=64, verbose_name='exam type')),
                ('province', models.CharField(blank=True, db_index=True, max_length=64, verbose_name='province')),
                ('status_note', models.CharField(blank=True, max_length=128, verbose_name='status note')),
                ('is_public', models.BooleanField(db_index=True, default=True, verbose_name='public')),
                ('sort_order', models.IntegerField(db_index=True, default=0, verbose_name='sort order')),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='exam_tags', to='judge.examcategory', verbose_name='category')),
            ],
            options={
                'verbose_name': 'exam tag',
                'verbose_name_plural': 'exam tags',
                'ordering': ('-year', 'sort_order', 'name', 'slug'),
            },
        ),
        migrations.AddField(
            model_name='problem',
            name='exam_tags',
            field=models.ManyToManyField(blank=True, help_text='Attach this problem to one or more exam progress tags.', related_name='problems', to='judge.ExamTag', verbose_name='exam tags'),
        ),
        migrations.CreateModel(
            name='ExamTagProblemPoint',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('points', models.FloatField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name='exam points')),
                ('sort_order', models.IntegerField(db_index=True, default=0, verbose_name='sort order')),
                ('exam_tag', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='problem_points', to='judge.examtag', verbose_name='exam tag')),
                ('problem', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_point_links', to='judge.problem', verbose_name='problem')),
            ],
            options={
                'verbose_name': 'exam tag problem point',
                'verbose_name_plural': 'exam tag problem points',
                'ordering': ('sort_order', 'problem__code'),
                'unique_together': {('exam_tag', 'problem')},
            },
        ),
        migrations.CreateModel(
            name='ExamUserProgress',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('earned_points', models.FloatField(default=0, verbose_name='earned points')),
                ('total_points', models.FloatField(default=0, verbose_name='total points')),
                ('percent', models.FloatField(default=0, verbose_name='percent')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('exam_tag', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_progress', to='judge.examtag', verbose_name='exam tag')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_progress', to='judge.profile', verbose_name='user')),
            ],
            options={
                'verbose_name': 'exam user progress',
                'verbose_name_plural': 'exam user progress',
                'unique_together': {('user', 'exam_tag')},
            },
        ),
    ]
