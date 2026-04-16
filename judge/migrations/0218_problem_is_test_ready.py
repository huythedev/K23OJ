from django.db import migrations, models



def mark_existing_problems_ready(apps, schema_editor):
    Problem = apps.get_model('judge', 'Problem')
    Problem.objects.all().update(is_test_ready=True)


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0217_contest_category_parent'),
    ]

    operations = [
        migrations.AddField(
            model_name='problem',
            name='is_test_ready',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.RunPython(mark_existing_problems_ready, migrations.RunPython.noop),
    ]
