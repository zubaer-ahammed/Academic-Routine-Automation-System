# Generated manually

from django.db import migrations, models
import django.db.models.deletion


def migrate_contact_person_to_coordinator(apps, schema_editor):
    """
    Migrate existing contact person data from Semester to ProgramCoordinator
    """
    Semester = apps.get_model('bou_routines_app', 'Semester')
    ProgramCoordinator = apps.get_model('bou_routines_app', 'ProgramCoordinator')
    Teacher = apps.get_model('bou_routines_app', 'Teacher')
    Centre = apps.get_model('bou_routines_app', 'Centre')
    
    # Group semesters by centre and contact person details to create coordinators
    coordinator_map = {}  # Key: (centre_id, contact_person, designation, phone, email), Value: coordinator_id
    
    for semester in Semester.objects.all():
        if not semester.centre:
            continue
            
        # Create a unique key based on contact person details
        contact_name = semester.contact_person or ''
        designation = semester.contact_person_designation or ''
        secondary_designation = semester.contact_person_secondary_designation or ''
        phone = semester.contact_person_phone or ''
        email = semester.contact_person_email or ''
        
        # Try to find a matching teacher by name
        teacher = None
        if contact_name:
            # Try exact match first
            teacher = Teacher.objects.filter(name__iexact=contact_name).first()
            # If not found, try partial match
            if not teacher:
                teacher = Teacher.objects.filter(name__icontains=contact_name.split()[0] if contact_name.split() else '').first()
        
        # If no teacher found, create a placeholder or use first teacher from centre
        if not teacher:
            teacher = Teacher.objects.filter(centre=semester.centre).first()
        
        if not teacher:
            print(f"Warning: No teacher found for semester {semester.name}, skipping coordinator creation")
            continue
        
        # Create coordinator key
        coord_key = (semester.centre.id, contact_name, designation, secondary_designation, phone, email)
        
        if coord_key not in coordinator_map:
            # Create new ProgramCoordinator
            coordinator, created = ProgramCoordinator.objects.get_or_create(
                teacher=teacher,
                centre=semester.centre,
                defaults={
                    'designation': designation,
                    'secondary_designation': secondary_designation,
                    'phone': phone,
                    'email': email,
                    'is_active': True
                }
            )
            coordinator_map[coord_key] = coordinator.id
            print(f"Created coordinator: {coordinator.teacher.name} for {semester.centre.name}")
        else:
            coordinator = ProgramCoordinator.objects.get(id=coordinator_map[coord_key])
        
        # Assign coordinator to semester
        semester.program_coordinator = coordinator
        semester.save()
    
    print(f"Migrated {len(coordinator_map)} unique coordinators")


def reverse_migrate(apps, schema_editor):
    """
    Reverse migration - copy coordinator data back to semester fields
    """
    Semester = apps.get_model('bou_routines_app', 'Semester')
    ProgramCoordinator = apps.get_model('bou_routines_app', 'ProgramCoordinator')
    
    for semester in Semester.objects.all():
        if semester.program_coordinator:
            coordinator = semester.program_coordinator
            semester.contact_person = coordinator.teacher.name if coordinator.teacher else ''
            semester.contact_person_designation = coordinator.designation or ''
            semester.contact_person_secondary_designation = coordinator.secondary_designation or ''
            semester.contact_person_phone = coordinator.phone or ''
            semester.contact_person_email = coordinator.email or ''
            semester.save()


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0040_add_secondary_designation'),
    ]

    operations = [
        # Step 1: Create ProgramCoordinator model
        migrations.CreateModel(
            name='ProgramCoordinator',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('designation', models.CharField(blank=True, help_text="Primary designation (e.g., 'Professor and Program Coordinator')", max_length=100, null=True)),
                ('secondary_designation', models.CharField(blank=True, help_text="Secondary designation (e.g., 'School of Science and Technology')", max_length=100, null=True)),
                ('phone', models.CharField(blank=True, help_text='Contact phone number', max_length=30, null=True)),
                ('email', models.EmailField(blank=True, help_text='Contact email address', max_length=254, null=True)),
                ('is_active', models.BooleanField(default=True, help_text='Whether this coordinator is currently active')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('centre', models.ForeignKey(help_text='Centre this coordinator belongs to (required)', on_delete=django.db.models.deletion.PROTECT, to='bou_routines_app.centre')),
                ('teacher', models.ForeignKey(help_text='Teacher who is the program coordinator', on_delete=django.db.models.deletion.CASCADE, to='bou_routines_app.teacher')),
            ],
            options={
                'verbose_name': 'Program Coordinator',
                'verbose_name_plural': 'Program Coordinators',
                'ordering': ['centre', 'teacher__name'],
            },
        ),
        # Step 2: Add program_coordinator field to Semester (nullable for now)
        migrations.AddField(
            model_name='semester',
            name='program_coordinator',
            field=models.ForeignKey(blank=True, help_text='Program Coordinator for this semester', null=True, on_delete=django.db.models.deletion.SET_NULL, to='bou_routines_app.programcoordinator'),
        ),
        # Step 3: Migrate data from contact_person fields to ProgramCoordinator
        migrations.RunPython(migrate_contact_person_to_coordinator, reverse_migrate),
        # Step 4: Remove old contact_person fields
        migrations.RemoveField(
            model_name='semester',
            name='contact_person',
        ),
        migrations.RemoveField(
            model_name='semester',
            name='contact_person_designation',
        ),
        migrations.RemoveField(
            model_name='semester',
            name='contact_person_email',
        ),
        migrations.RemoveField(
            model_name='semester',
            name='contact_person_phone',
        ),
        migrations.RemoveField(
            model_name='semester',
            name='contact_person_secondary_designation',
        ),
    ]
