# Mark Distribution Documentation

## Overview

This document describes how mark distribution works for both the **Old Curriculum** and **New Curriculum** in the BOU Routines Generator system. The mark distribution system is curriculum-specific and handles three types of courses: **Theory Courses**, **Lab Courses**, and **Project Work**.

---

## Table of Contents

1. [Theory Course Mark Distribution](#theory-course-mark-distribution)
2. [Lab Course Mark Distribution](#lab-course-mark-distribution)
3. [Project Work Mark Distribution](#project-work-mark-distribution)
4. [System Implementation](#system-implementation)
5. [Configuration](#configuration)
6. [Examples](#examples)

---

## Theory Course Mark Distribution

### Old Curriculum

**Total Marks: 100**

#### Continuous Assessment (CA) - 30%
- **Attendance**: 5% (Auto-calculated based on attendance records)
- **Assignment/Presentation**: 10% (Average of 3 assignments)
- **Quiz/Class Test**: 15%
- **Mid-Term Exam**: 0% (Midterm is part of final exam in old curriculum)

#### Semester Final Examination - 70%
- **Final Exam**: 70 marks
- **Total**: 100 marks

**Note**: In the old curriculum, quizzes are part of the CA assessment, and midterm exams are not separate from the final examination.

### New Curriculum

**Total Marks: 100**

#### Continuous Assessment (CA) - 30%
- **Attendance**: 5% (Auto-calculated based on attendance records)
- **Assignment/Presentation**: 5% (Average of 3 assignments)
- **Quiz/Class Test**: 0% (Removed in new curriculum)
- **Mid-Term Exam**: 20%

#### Semester Final Examination - 70%
- **Final Exam**: 70 marks
- **Total**: 100 marks

**Key Differences from Old Curriculum**:
- Quiz component has been removed
- Mid-Term Exam is now a significant component (20%) of CA
- Assignment weight reduced from 10% to 5%

---

## Lab Course Mark Distribution

### Old Curriculum

**Total Marks: 50**

#### Continuous Assessment (CA) - 50%
- **Attendance/Class Participation**: 10% (Auto-calculated)
- **Assignment/Lab Report**: 10% (Average of 3 lab assignments)
- **Experiment/Lab Based Project Works**: 10%
- **Quiz/Class Test**: 10%

#### Semester Final Examination - 50%
- **Problem Solving/Implementing Lab work**: 40%
- **Viva-voce**: 10%
- **Total**: 50 marks

### New Curriculum

**Total Marks: 50**

#### Continuous Assessment (CA) - 50%
- **Attendance/Class Participation**: 10% (Auto-calculated)
- **Assignment/Lab Report**: 10% (Average of 3 lab assignments)
- **Experiment/Lab Based Project Works**: 30% (Increased significantly)
- **Quiz/Class Test**: 0% (Removed in new curriculum)

#### Semester Final Examination - 50%
- **Problem Solving/Implementing Lab work**: 40%
- **Viva-voce**: 10%
- **Total**: 50 marks

**Key Differences from Old Curriculum**:
- Quiz component has been removed
- Experiment/Lab Based Project Works weight increased from 10% to 30%
- More emphasis on practical lab work in CA assessment

---

## Project Work Mark Distribution

### Old Curriculum

**Total Marks: 200**

#### Supervisor Evaluation - 30%
- **Project/Thesis/Internee work**: 30%
- **Project/Thesis/Internee report**: Included in supervisor evaluation

#### Examination Committee Evaluation - 40%
- **Evaluation Component**: 40%

#### Presentation - 30%
- **Presentation Component**: 30%

**Total**: 100% (of 200 marks)

### New Curriculum

**Total Marks: 200**

#### Supervisor Evaluation - 50%
- **Project/Thesis/Internee work**: 30% (60 marks out of 200)
- **Project/Thesis/Internee report**: 20% (40 marks out of 200)
- **Total Supervisor Marks**: 100 marks (50% of total)

#### Examination Committee Evaluation - 30%
- **Project Report**: 10% (20 marks out of 200)
- **Viva-voce**: 20% (40 marks out of 200)
- **Total Evaluation Marks**: 60 marks (30% of total)

#### Presentation - 20%
- **Presentation on the project by individual student**: 20% (40 marks out of 200)

**Total**: 100% (of 200 marks)

**Key Differences from Old Curriculum**:
- Supervisor evaluation weight increased from 30% to 50%
- More detailed breakdown of examination committee evaluation
- Presentation weight reduced from 30% to 20%
- Clear separation between supervisor's work evaluation and report evaluation

---

## System Implementation

### Database Structure

Mark distribution is stored at the **Curriculum** level in the database. Each curriculum has its own mark distribution settings:

```python
# Curriculum Model Fields
theory_ca_attendance_weight      # Attendance weight for theory courses
theory_ca_assignment_weight      # Assignment weight for theory courses
theory_ca_quiz_weight           # Quiz weight for theory courses
theory_ca_midterm_weight        # Midterm weight for theory courses

lab_ca_attendance_weight        # Attendance weight for lab courses
lab_ca_assignment_weight        # Assignment weight for lab courses
lab_ca_practical_weight        # Practical weight for lab courses
lab_ca_quiz_weight             # Quiz weight for lab courses

project_supervisor_weight       # Supervisor weight for project work
project_evaluation_weight       # Evaluation weight for project work
project_presentation_weight     # Presentation weight for project work
```

### Course Model Properties

The `Course` model has properties that retrieve the effective mark distribution from its associated curriculum:

```python
# Theory Course Properties
course.effective_ca_attendance_weight
course.effective_ca_assignment_weight
course.effective_ca_quiz_weight
course.effective_ca_midterm_weight

# Lab Course Properties
course.effective_lab_ca_attendance_weight
course.effective_lab_ca_assignment_weight
course.effective_lab_ca_practical_weight
course.effective_lab_ca_quiz_weight

# Project Work Properties
course.effective_project_supervisor_weight
course.effective_project_evaluation_weight
course.effective_project_presentation_weight
```

### Mark Calculation

#### Theory Course CA Mark Calculation

```python
total_ca_mark = (
    attendance_mark +           # Auto-calculated from attendance records
    assignment_mark +          # Average of 3 assignments
    quiz_mark +                # Quiz/Class test mark
    midterm_mark               # Mid-term exam mark
)
```

#### Lab Course CA Mark Calculation

```python
total_ca_mark = (
    attendance_mark +           # Auto-calculated from attendance records
    lab_assignment_mark +      # Average of 3 lab assignments
    lab_practical_mark         # Experiment/Lab project mark
)
```

#### Project Work CA Mark Calculation

```python
total_ca_mark = (
    project_supervisor_mark +   # Supervisor evaluation
    project_evaluation_mark +   # Examination committee evaluation
    project_presentation_mark   # Presentation mark
)
```

---

## Configuration

### Accessing Mark Distribution Settings

1. **Via Admin Panel**:
   - Navigate to: `Admin Panel → Curricula → [Select Curriculum]`
   - Edit the mark distribution fields for Theory, Lab, and Project Work

2. **Via Django Shell**:
   ```python
   from bou_routines_app.models import Curriculum
   
   # Get curriculum
   curriculum = Curriculum.objects.get(code='NEW')
   
   # Update mark distribution
   curriculum.theory_ca_attendance_weight = 5
   curriculum.theory_ca_assignment_weight = 5
   curriculum.theory_ca_midterm_weight = 20
   curriculum.save()
   ```

### Default Values

#### Old Curriculum Defaults
- **Theory CA**: Attendance=5%, Assignment=10%, Quiz=15%, Midterm=0%
- **Lab CA**: Attendance=10%, Assignment=10%, Practical=10%, Quiz=10%
- **Project**: Supervisor=30%, Evaluation=40%, Presentation=30%

#### New Curriculum Defaults
- **Theory CA**: Attendance=5%, Assignment=5%, Quiz=0%, Midterm=20%
- **Lab CA**: Attendance=10%, Assignment=10%, Practical=30%, Quiz=0%
- **Project**: Supervisor=50%, Evaluation=30%, Presentation=20%

---

## Examples

### Example 1: Theory Course (New Curriculum)

**Course**: CSE3101 - Data Structures and Algorithms

**CA Marks**:
- Attendance: 4.5/5 (90% attendance)
- Assignment 1: 4/5, Assignment 2: 4.5/5, Assignment 3: 5/5
  - Average Assignment: 4.5/5
- Mid-Term Exam: 18/20

**CA Total**: 4.5 + 4.5 + 18 = 27/30

**Final Exam**: 60/70

**Total**: 87/100

### Example 2: Lab Course (New Curriculum)

**Course**: CSE3102P - Data Structures and Algorithms Lab

**CA Marks**:
- Attendance: 9/10 (90% attendance)
- Lab Assignment 1: 9/10, Lab Assignment 2: 10/10, Lab Assignment 3: 9.5/10
  - Average Lab Assignment: 9.5/10
- Lab Practical: 28/30

**CA Total**: 9 + 9.5 + 28 = 46.5/50

**Final Exam**: 38/40 (Problem Solving) + 9/10 (Viva) = 47/50

**Total**: 93.5/100 (converted from 50-mark scale)

### Example 3: Project Work (New Curriculum)

**Course**: CSE4246 - Project/Thesis

**CA Marks**:
- Supervisor Evaluation: 48/50 (Work: 29/30, Report: 19/20)
- Examination Committee Evaluation: 27/30 (Report: 9/10, Viva: 18/20)
- Presentation: 18/20

**CA Total**: 48 + 27 + 18 = 93/100 (of 200 marks)

**Total**: 186/200

---

## Important Notes

### Auto-Calculated Components

1. **Attendance Marks**: Automatically calculated based on attendance records
   - Formula: `(attended_days / total_classes) * attendance_weight`
   - Updated when attendance is marked

2. **Assignment Marks**: Automatically calculated as average of 3 assignments
   - Formula: `(assignment1 + assignment2 + assignment3) / 3`
   - Updated when assignment marks are entered

### Course Type Selection

Courses must be marked as one of the following types:
- **Theory Course**: Uses theory CA distribution
- **Lab Course**: Uses lab CA distribution
- **Project Work**: Uses project work distribution

A course cannot be both theory and lab simultaneously.

### Curriculum-Specific Distribution

- Each curriculum maintains its own mark distribution settings
- When a course is assigned to a curriculum, it uses that curriculum's distribution
- Distribution settings can be updated per curriculum without affecting other curricula

---

## Troubleshooting

### Common Issues

1. **Marks Not Calculating Correctly**
   - Check that the course is assigned to the correct curriculum
   - Verify that the curriculum's mark distribution settings are correct
   - Ensure all required marks are entered

2. **Attendance Marks Not Updating**
   - Verify attendance records exist for the course
   - Check that `number_of_classes` is set in `SemesterCourse`
   - Ensure attendance is marked for the correct semester and course

3. **Assignment Average Not Calculating**
   - Ensure all three assignment marks are entered
   - Check that the marks are within the valid range (0 to max weight)

### Verification Commands

```python
# Check curriculum mark distribution
from bou_routines_app.models import Curriculum
curriculum = Curriculum.objects.get(code='NEW')
print(f"Theory CA: {curriculum.theory_ca_attendance_weight}% + {curriculum.theory_ca_assignment_weight}% + {curriculum.theory_ca_midterm_weight}% = {curriculum.theory_ca_attendance_weight + curriculum.theory_ca_assignment_weight + curriculum.theory_ca_midterm_weight}%")

# Check course effective weights
from bou_routines_app.models import Course
course = Course.objects.get(code='CSE3101')
print(f"Effective CA Attendance Weight: {course.effective_ca_attendance_weight}%")
```

---

## References

- **New Curriculum Document**: `new_curriculum/New-Curriculum-Exam-Regulations-and-CA.pdf`
- **Old Curriculum Regulations**: See university academic regulations
- **System Models**: `bou_routines_app/models.py` - `Curriculum` and `Course` models
- **Mark Calculation**: `bou_routines_app/models.py` - `CAMark.calculate_total_ca_mark()`

---

## Last Updated

This documentation was last updated based on the mark distribution implemented in the system as of the current version. For the most up-to-date distribution values, please check the curriculum settings in the admin panel.

