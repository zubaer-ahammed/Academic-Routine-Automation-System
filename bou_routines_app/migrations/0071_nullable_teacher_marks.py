from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bou_routines_app", "0070_alter_semester_name_max_length"),
    ]

    operations = [
        migrations.AlterField(
            model_name="camark",
            name="first_assignment_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="First Assignment/Presentation mark",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="camark",
            name="second_assignment_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Second Assignment/Presentation mark",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="camark",
            name="third_assignment_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Third Assignment/Presentation mark",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="camark",
            name="first_class_test_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="First Class Test mark (for old curriculum)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="camark",
            name="second_class_test_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Second Class Test mark (for old curriculum)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="camark",
            name="midterm_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Midterm mark (for new curriculum)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="camark",
            name="first_lab_assignment_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="First Lab Assignment/Report mark",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="camark",
            name="second_lab_assignment_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Second Lab Assignment/Report mark",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="camark",
            name="third_lab_assignment_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Third Lab Assignment/Report mark",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="camark",
            name="lab_practical_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Lab practical / first experiment mark",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="camark",
            name="second_lab_practical_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Second experiment / lab project mark (new curriculum split)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="camark",
            name="project_supervisor_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Project supervisor mark",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="camark",
            name="project_evaluation_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Project evaluation mark",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="camark",
            name="project_presentation_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Project presentation mark",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="midtermexammark",
            name="q1",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AlterField(
            model_name="midtermexammark",
            name="q2",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AlterField(
            model_name="midtermexammark",
            name="q3",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AlterField(
            model_name="midtermexammark",
            name="q4",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AlterField(
            model_name="midtermexammark",
            name="q5",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AlterField(
            model_name="midtermexammark",
            name="q6",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher1_q1",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 1 - Question Set 1 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher1_q2",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 1 - Question Set 2 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher1_q3",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 1 - Question Set 3 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher1_q4",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 1 - Question Set 4 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher1_q5",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 1 - Question Set 5 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher1_q6",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 1 - Question Set 6 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher1_q7",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 1 - Question Set 7 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher2_q1",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 2 - Question Set 1 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher2_q2",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 2 - Question Set 2 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher2_q3",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 2 - Question Set 3 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher2_q4",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 2 - Question Set 4 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher2_q5",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 2 - Question Set 5 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher2_q6",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 2 - Question Set 6 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher2_q7",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 2 - Question Set 7 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher3_q1",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 3 - Question Set 1 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher3_q2",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 3 - Question Set 2 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher3_q3",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 3 - Question Set 3 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher3_q4",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 3 - Question Set 4 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher3_q5",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 3 - Question Set 5 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher3_q6",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 3 - Question Set 6 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher3_q7",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Teacher 3 - Question Set 7 (max 14)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher1_lab_final_exam_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Internal examiner — problem solving / old curriculum final",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher1_lab_viva_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Internal examiner — viva (new curriculum)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher2_lab_final_exam_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="External examiner — problem solving / old curriculum final",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="teacher2_lab_viva_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="External examiner — viva (new curriculum)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="lab_final_exam_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Lab course: denormalized avg problem solving / old curriculum (legacy readers)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="finalexammark",
            name="lab_viva_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Lab viva: denormalized average (legacy readers)",
                max_digits=5,
                null=True,
            ),
        ),
    ]
