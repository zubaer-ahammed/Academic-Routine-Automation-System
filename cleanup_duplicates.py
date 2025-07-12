#!/usr/bin/env python
import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bou_routines_generator.settings')
django.setup()

from bou_routines_app.models import CurrentRoutine
from django.db.models import Count

def cleanup_duplicate_routines():
    """Remove duplicate CurrentRoutine entries, keeping only the latest one."""
    print("Checking for duplicate CurrentRoutine entries...")

    # Find duplicates based on course_id and semester_id
    duplicates = CurrentRoutine.objects.values('course_id', 'semester_id').annotate(
        count=Count('id')
    ).filter(count__gt=1)

    print(f"Found {len(duplicates)} sets of duplicate entries")

    for duplicate in duplicates:
        course_id = duplicate['course_id']
        semester_id = duplicate['semester_id']

        # Get all entries for this course/semester combination
        entries = CurrentRoutine.objects.filter(
            course_id=course_id,
            semester_id=semester_id
        ).order_by('-id')  # Order by ID descending to keep the latest

        # Keep the first (latest) entry and delete the rest
        entries_to_delete = entries[1:]
        count_to_delete = len(entries_to_delete)

        if count_to_delete > 0:
            print(f"Deleting {count_to_delete} duplicate entries for course_id={course_id}, semester_id={semester_id}")
            for entry in entries_to_delete:
                entry.delete()

    print("Cleanup completed!")

if __name__ == "__main__":
    cleanup_duplicate_routines()
