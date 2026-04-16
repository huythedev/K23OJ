from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0219_problem_autoproblem_task_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemtestcase',
            name='is_hidden',
            field=models.BooleanField(default=False, verbose_name='hidden subtask?'),
        ),
        migrations.AddField(
            model_name='contestsubmission',
            name='hidden_points',
            field=models.FloatField(default=0.0, verbose_name='hidden points'),
        ),
        migrations.AddField(
            model_name='contestsubmission',
            name='visible_points',
            field=models.FloatField(default=0.0, verbose_name='visible points'),
        ),
    ]
