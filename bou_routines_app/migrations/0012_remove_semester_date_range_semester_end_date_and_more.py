# Generated by Django 4.2.20 on 2025-05-18 01:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0011_semester_date_range'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='semester',
            name='date_range',
        ),
        migrations.AddField(
            model_name='semester',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='semester',
            name='start_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
