from django.core.validators import RegexValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0220_new_ioi_hidden_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contestcategory',
            name='slug',
            field=models.CharField(
                max_length=128,
                unique=True,
                verbose_name='category slug',
                validators=[
                    RegexValidator(
                        '^([a-z0-9_]+)(/[a-z0-9_]+)*$',
                        'Category slug must be path-like: ^([a-z0-9_]+)(/[a-z0-9_]+)*$',
                    ),
                ],
            ),
        ),
    ]
