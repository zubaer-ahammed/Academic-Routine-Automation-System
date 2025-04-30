from django.core.management.base import BaseCommand
from bou_routines_app.models import Course, Teacher, TimeSlot, Semester, CurrentRoutine
from datetime import time


class Command(BaseCommand):
    help = "Seed CurrentRoutine table with predefined data (safe against missing foreign keys)"

    def handle(self, *args, **kwargs):
        teacher_map = {
            "MAT3131": "Prof. Dr. Anamul Haque Sajib",
            "CSE3122": "Mr. Md. Rakib Hossen",
            "CSE3133": "Prof. Dr. Md. Asraf Ali",
            "CSE3134": "Prof. Dr. Md. Asraf Ali",
            "CSE31P5": "Prof. Dr. Mohammed Nasir Uddin",
            "CSE3136": "Mr. Md. Mahmudul Hasan",
            "CSE31P7": "Mr. Samrat Kumar Dey",
            "CSE31P8": "Prof. Dr. Md. Manowarul Islam",
            "CSE31P9": "Prof. Dr. Md. Manowarul Islam"
        }

        slot_times = [
            (time(8, 30), time(10, 0)),
            (time(10, 0), time(11, 30)),
            (time(11, 30), time(13, 0)),
            (time(14, 0), time(16, 0)),
            (time(16, 0), time(17, 30)),
        ]

        routine_data = [
            ("Friday",   ["CSE31P8", "CSE3133", "CSE3136", "CSE31P7", "MAT3131"]),
            ("Saturday", ["CSE31P9", "CSE3134", "CSE31P5", "CSE3122"]),
        ]

        semester, _ = Semester.objects.get_or_create(name="Y3S1")

        created = 0
        skipped = 0

        for day, courses in routine_data:
            for i, course_code in enumerate(courses):
                if i >= len(slot_times):
                    continue

                teacher_name = teacher_map.get(course_code)
                start, end = slot_times[i]

                try:
                    course = Course.objects.get(code=course_code)
                except Course.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"⚠️  Course not found: {course_code}"))
                    skipped += 1
                    continue

                try:
                    teacher = Teacher.objects.get(name=teacher_name)
                except Teacher.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"⚠️  Teacher not found: {teacher_name}"))
                    skipped += 1
                    continue

                try:
                    timeslot = TimeSlot.objects.get(start_time__time=start, end_time__time=end)
                except TimeSlot.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"⚠️  TimeSlot not found: {start} – {end}"))
                    skipped += 1
                    continue

                # Prevent duplicates
                if not CurrentRoutine.objects.filter(course=course, teacher=teacher, time_slot=timeslot, day=day, semester=semester).exists():
                    CurrentRoutine.objects.create(
                        course=course,
                        teacher=teacher,
                        time_slot=timeslot,
                        day=day,
                        semester=semester
                    )
                    created += 1

        self.stdout.write(self.style.SUCCESS(f"✅ Seeded {created} CurrentRoutine entries. Skipped: {skipped}"))
