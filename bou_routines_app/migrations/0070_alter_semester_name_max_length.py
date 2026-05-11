from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bou_routines_app", "0069_midtermexammark"),
    ]

    operations = [
        migrations.AlterField(
            model_name="semester",
            name="name",
            field=models.CharField(max_length=64),
        ),
    ]
