from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0216_contest_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='contestcategory',
            name='parent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='judge.contestcategory', verbose_name='parent category'),
        ),
    ]
