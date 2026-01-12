# Generated migration to add class test fields to CAMark

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0054_add_semester_centre_coordinator'),
    ]

    operations = [
        migrations.AddField(
            model_name='camark',
            name='first_class_test_mark',
            field=models.DecimalField(decimal_places=2, default=0, help_text='First Class Test mark (for old curriculum)', max_digits=5),
        ),
        migrations.AddField(
            model_name='camark',
            name='second_class_test_mark',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Second Class Test mark (for old curriculum)', max_digits=5),
        ),
        migrations.AddField(
            model_name='camark',
            name='class_test_mark',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Best Class Test mark (auto-calculated, best of first and second)', max_digits=5),
        ),
    ]

