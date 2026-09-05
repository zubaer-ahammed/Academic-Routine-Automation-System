from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0077_clear_legacy_zero_final_exam_qs'),
    ]

    operations = [
        migrations.AddField(
            model_name='semester',
            name='cse_tech_carnival_date',
            field=models.DateField(
                blank=True,
                help_text='CSE Tech Carnival date (New curriculum). Placed after makeup/review classes; pushes SEFE back.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='semester',
            name='cultural_fest_date',
            field=models.DateField(
                blank=True,
                help_text='Cultural Fest date (New curriculum). Placed after makeup/review classes; pushes SEFE back.',
                null=True,
            ),
        ),
    ]
