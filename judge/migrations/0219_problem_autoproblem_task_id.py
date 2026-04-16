from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0218_problem_is_test_ready'),
    ]

    operations = [
        migrations.AddField(
            model_name='problem',
            name='autoproblem_task_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=36),
        ),
    ]
