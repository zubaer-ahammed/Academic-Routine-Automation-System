# Generated by Django 4.2.20 on 2025-05-18 03:35

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0005_remove_currentroutine_time_slot_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='semestercourse',
            name='teacher',
        ),
    ]
