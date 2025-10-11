# Multi-Curriculum System Guide

## Overview

The BOU Routines Generator now supports multiple curricula, allowing you to manage both current and new curriculum versions simultaneously. This system enables you to:

- **Switch between curricula** when generating routines
- **Maintain separate course catalogs** for different curriculum versions
- **Handle different CA mark distributions** and course credits
- **Generate routines for different batches** following different curricula

## System Architecture

### 1. Curriculum Model
- **Curriculum**: Represents different curriculum versions (Current, New 2024, etc.)
- **Course**: Extended with curriculum-specific fields (credits, CA distribution, etc.)
- **Semester**: Associated with specific curricula
- **SemesterCourse**: Links courses to semesters within a curriculum

### 2. Key Features
- **Curriculum Selection**: Dropdown to switch between curricula
- **Dynamic Filtering**: Courses and semesters filtered by selected curriculum
- **CA Distribution**: Different mark distributions for theory and lab courses
- **Course Credits**: Curriculum-specific credit hours
- **Prerequisites**: Course prerequisite relationships

## How to Use

### 1. Accessing the System

1. **Navigate to Generate Routine**: Go to the "Generate Routine" page
2. **Select Curriculum**: Choose from the "Curriculum" dropdown:
   - **Current Curriculum (CURR)**: For existing batches
   - **New Curriculum 2024 (NEW2024)**: For new batches
3. **Select Semester**: Choose a semester (filtered by curriculum)
4. **Generate Routine**: Proceed with routine generation as usual

### 2. Managing Courses

#### Adding Courses to a Curriculum
1. Go to **Admin Panel** → **Courses**
2. When creating/editing a course:
   - Select the **Curriculum** (Current or New 2024)
   - Set **Credits** (number of credit hours)
   - Choose **Course Type** (Core, Elective, General, Project)
   - Mark as **Theory** or **Lab** course
   - Set **CA Distribution** weights

#### CA Mark Distribution
- **Theory Courses**: Attendance (10%), Assignment (20%), Quiz (20%), Midterm (50%)
- **Lab Courses**: Attendance (10%), Assignment (30%), Practical (60%)

### 3. Managing Semesters

#### Creating Semesters for Different Curricula
1. Go to **Admin Panel** → **Semesters**
2. When creating/editing a semester:
   - Select the **Curriculum** this semester follows
   - Configure semester settings as usual

### 4. Assigning Courses to Semesters

1. Go to **Semester Courses** page
2. **Select Curriculum** from the dropdown
3. **Select Semester** (filtered by curriculum)
4. **Add Courses** that belong to the selected curriculum
5. **Set Number of Classes** per week for each course

## Curriculum-Specific Features

### 1. Course Information
- **Course Code**: Unique within curriculum
- **Course Name**: Can be same across curricula with curriculum suffix
- **Credits**: Curriculum-specific credit hours
- **CA Distribution**: Different for theory vs lab courses
- **Prerequisites**: Course dependency relationships

### 2. Routine Generation
- **Curriculum Filtering**: Only courses from selected curriculum appear
- **Semester Association**: Semesters are curriculum-specific
- **Teacher Assignment**: Teachers can teach across curricula

### 3. Data Management
- **Separate Course Catalogs**: Each curriculum has its own courses
- **Independent Semesters**: Semesters are tied to specific curricula
- **Flexible Switching**: Easy switching between curricula in UI

## Best Practices

### 1. Curriculum Setup
1. **Create Curricula First**: Set up all curriculum versions
2. **Populate Courses**: Add all courses for each curriculum
3. **Assign Teachers**: Assign teachers to courses across curricula
4. **Create Semesters**: Create semesters for each curriculum

### 2. Course Management
1. **Use Descriptive Names**: Include curriculum info in course names
2. **Set Appropriate Credits**: Match credit hours to curriculum requirements
3. **Configure CA Distribution**: Set appropriate mark distributions
4. **Define Prerequisites**: Set up course dependency relationships

### 3. Routine Generation
1. **Select Correct Curriculum**: Always select the appropriate curriculum
2. **Verify Courses**: Ensure all required courses are available
3. **Check Semesters**: Verify semester-curriculum associations
4. **Generate Routines**: Proceed with routine generation

## Troubleshooting

### Common Issues

#### 1. No Courses Available
- **Check Curriculum Selection**: Ensure correct curriculum is selected
- **Verify Course Assignment**: Check if courses are assigned to the curriculum
- **Check Semester Association**: Ensure semester belongs to the curriculum

#### 2. Missing Semesters
- **Check Curriculum Filter**: Semesters are filtered by curriculum
- **Create Semesters**: Create semesters for the selected curriculum
- **Assign Curriculum**: Ensure semesters are assigned to the curriculum

#### 3. Course Conflicts
- **Check Course Codes**: Ensure course codes are unique within curriculum
- **Verify Names**: Check for duplicate course names
- **Review Assignments**: Ensure courses are properly assigned

### Solutions

#### 1. Data Migration
```bash
# Run setup command to create default curricula
python manage.py setup_curricula

# Populate new curriculum with sample courses
python manage.py populate_new_curriculum
```

#### 2. Manual Setup
1. **Admin Panel** → **Curricula** → **Add Curriculum**
2. **Admin Panel** → **Courses** → **Add Course** (select curriculum)
3. **Admin Panel** → **Semesters** → **Add Semester** (select curriculum)

## Technical Details

### Database Schema
- **Curriculum**: id, name, code, description, is_active, effective_from
- **Course**: Extended with curriculum, credits, CA distribution, course_type
- **Semester**: Extended with curriculum association
- **SemesterCourse**: Links courses to semesters within curriculum

### API Endpoints
- **Generate Routine**: `/generate/?curriculum=X`
- **Semester Courses**: `/semester-courses/?curriculum=X`
- **Download Routines**: Curriculum-aware routine downloads

### Migration History
- **0026_add_curriculum_support**: Added curriculum support
- **setup_curricula**: Creates default curricula
- **populate_new_curriculum**: Populates new curriculum with courses

## Future Enhancements

### Planned Features
1. **Curriculum Versioning**: Track curriculum changes over time
2. **Batch Management**: Associate batches with specific curricula
3. **Advanced CA Distribution**: More flexible mark distribution options
4. **Curriculum Comparison**: Compare different curriculum versions
5. **Import/Export**: Import curriculum data from external sources

### Integration Points
1. **Student Management**: Link students to specific curricula
2. **Grade Management**: Curriculum-specific grading systems
3. **Academic Calendar**: Curriculum-specific academic calendars
4. **Reporting**: Curriculum-specific reports and analytics

## Support

For technical support or questions about the multi-curriculum system:

1. **Check Documentation**: Review this guide and technical documentation
2. **Admin Panel**: Use Django admin for data management
3. **Database Queries**: Use Django ORM for complex queries
4. **Custom Commands**: Use management commands for bulk operations

## Conclusion

The multi-curriculum system provides a robust foundation for managing different curriculum versions within a single platform. This allows for:

- **Seamless Transition**: Between old and new curricula
- **Data Integrity**: Separate data for different curriculum versions
- **Flexible Management**: Easy switching and management of curricula
- **Future Scalability**: Support for additional curriculum versions

This system ensures that your BOU Routines Generator can handle both current and new curriculum requirements efficiently and effectively.
