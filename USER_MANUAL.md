# BOU Routine Generator - User Manual

**Complete Guide to Using the Academic Routine Automation System**

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [System Overview](#system-overview)
3. [Admin Panel Guide](#admin-panel-guide)
4. [Routine Generation](#routine-generation)
5. [Interactive Routine Management](#interactive-routine-management)
6. [Export Functions](#export-functions)
7. [Troubleshooting](#troubleshooting)
8. [Best Practices](#best-practices)

---

## Getting Started

### System Requirements
- **Web Browser**: Chrome, Firefox, Safari, or Edge (latest versions)
- **Internet Connection**: Required for web-based access
- **Permissions**: Admin access for full functionality

### Accessing the System
1. Open your web browser
2. Navigate to the BOU Routine Generator URL
3. Login with your credentials (if required)
4. You'll see the main navigation menu

### Navigation Menu
- **Generate Routine**: Main routine generation interface
- **Semester Courses**: Manage course assignments
- **Download Routines**: Access generated reports

---

## System Overview

### Main Dashboard
The system provides three main areas of functionality:

#### 1. Generate Routine
- Create and manage academic schedules
- Real-time conflict detection
- Interactive editing capabilities

#### 2. Semester Courses
- Assign courses to semesters
- Manage teacher-course relationships
- Configure class counts

#### 3. Download Routines
- Export schedules as PDF or Excel
- Access historical routines
- Generate reports

---

## Admin Panel Guide

### Accessing Admin Panel
1. Navigate to `/admin/` in your browser
2. Login with superuser credentials
3. You'll see the Django admin interface

### Managing Teachers

#### Adding a New Teacher
1. Click on "Teachers" in the admin panel
2. Click "Add Teacher" button
3. Fill in the required fields:
   - **Name**: Full name of the teacher
   - **Short Name**: Abbreviated name (optional)
4. Click "Save"

#### Editing Teacher Information
1. Click on "Teachers" in the admin panel
2. Click on the teacher's name
3. Modify the required fields
4. Click "Save"

### Managing Courses

#### Adding a New Course
1. Click on "Courses" in the admin panel
2. Click "Add Course" button
3. Fill in the required fields:
   - **Code**: Course code (e.g., CSE101)
   - **Name**: Full course name
   - **Teacher**: Select from available teachers
4. Click "Save"

#### Assigning Teachers to Courses
1. Navigate to the course you want to modify
2. Click on the course name
3. Change the "Teacher" field
4. Click "Save"

### Managing Semesters

#### Creating a New Semester
1. Click on "Semesters" in the admin panel
2. Click "Add Semester" button
3. Fill in the required fields:
   - **Name**: Semester name (e.g., "Fall 2024")
   - **Order**: Display order (optional)
   - **Semester Full Name**: Complete semester name
   - **Term**: Academic term
   - **Session**: Academic session
   - **Study Center**: Study center information
4. Configure optional settings:
   - **Lunch Break Start**: Start time for lunch break
   - **Lunch Break End**: End time for lunch break
   - **Start Date**: Semester start date
   - **End Date**: Semester end date
   - **Holidays**: Comma-separated holiday dates
5. Click "Save"

#### Configuring Semester Settings
1. Click on the semester name
2. Modify the required settings:
   - **Contact Information**: Add contact person details
   - **Date Range**: Set semester start and end dates
   - **Holidays**: Add government holidays
   - **Lunch Break**: Configure break times
3. Click "Save"

### Managing Semester Courses

#### Assigning Courses to Semesters
1. Click on "Semester Courses" in the admin panel
2. Click "Add Semester Course" button
3. Fill in the required fields:
   - **Semester**: Select the target semester
   - **Course**: Select the course to assign
   - **Number of Classes**: Set the number of classes per week
4. Click "Save"

#### Bulk Course Assignment
1. Navigate to "Semester Courses"
2. Use the bulk actions to assign multiple courses
3. Select the courses and semester
4. Apply the changes

---

## Routine Generation

### Step-by-Step Process

#### Step 1: Select Semester
1. Navigate to "Generate Routine"
2. Select a semester from the dropdown menu
3. The system will load existing semester data
4. Review the displayed information:
   - Lunch break times
   - Holiday dates
   - Existing course assignments

#### Step 2: Configure Date Range
1. Click on the "Date Range" field
2. Select start and end dates for the semester
3. The date picker will show a calendar interface
4. Click "Apply" to confirm the selection

#### Step 3: Set Government Holidays
1. Click on the "Holidays" field
2. Select multiple dates for government holidays
3. Selected dates will appear as badges below the field
4. Click the "X" on any badge to remove a holiday

#### Step 4: Configure Lunch Break
1. Set the lunch break start time
2. Set the lunch break end time
3. The system will automatically enforce this break
4. No classes can be scheduled during this time

#### Step 5: Add Course Schedule
1. Select a course from the dropdown menu
2. Choose the day (Friday or Saturday)
3. Set the start time using the time picker
4. Set the end time using the time picker
5. The system will check for conflicts automatically

#### Step 6: Add More Courses
1. Click the "+ Add Another Course" button
2. Repeat the process for additional courses
3. The system will validate each entry
4. Resolve any conflicts before proceeding

#### Step 7: Generate Routine
1. Review all course schedules
2. Ensure no conflicts are shown
3. Click "Generate Routine" button
4. The system will create the schedule

### Conflict Resolution

#### Understanding Conflict Messages
- **Time Overlap**: Two courses scheduled at the same time
- **Teacher Conflict**: Same teacher assigned to overlapping times
- **Lunch Break Conflict**: Course scheduled during lunch break

#### Resolving Conflicts
1. **Time Overlap**: Adjust start or end times
2. **Teacher Conflict**: Assign different teachers or change times
3. **Lunch Break Conflict**: Move course outside break time

#### Real-time Validation
- The system checks for conflicts as you type
- Red highlighting indicates conflicts
- Green highlighting indicates valid entries
- Warning messages appear below conflicting entries

---

## Interactive Routine Management

### Viewing Generated Routines

#### Routine Calendar View
1. After generating a routine, you'll see a calendar view
2. Each cell represents a time slot
3. Course information is displayed in each cell
4. Lunch breaks are highlighted in yellow

#### Understanding the Layout
- **Date Column**: Shows the date for each row
- **Day Column**: Shows the day of the week
- **Time Slots**: Each column represents a time period
- **Course Cells**: Blue cells contain course information

### Editing Existing Routines

#### Modifying Course Assignments
1. **Click on a Course Cell**: The cell will enter edit mode
2. **Select New Course**: Choose from the dropdown menu
3. **Save Changes**: Click the "Save" button
4. **Cancel Changes**: Click the "Cancel" button

#### Visual Indicators
- **Edit Icon**: Pen icon in top-right corner
- **Remove Icon**: Trash icon in top-left corner
- **Edit Controls**: Dropdown and buttons appear when editing

### Adding New Courses

#### Adding to Empty Slots
1. **Click on Empty Cell**: Gray cells are available for new courses
2. **Select Course**: Choose from available courses
3. **Save Entry**: Click "Save" to create the entry
4. **Cell Updates**: Empty cell becomes a course cell

#### Understanding Empty Cells
- **Gray Background**: Indicates available time slots
- **"Click to add course"**: Text indicates the cell is empty
- **Edit Icon**: Available for adding new courses

### Removing Courses

#### Deleting Course Entries
1. **Click Trash Icon**: Located in top-left corner of course cells
2. **Confirm Deletion**: Click "OK" in the confirmation dialog
3. **Cell Reset**: Course cell becomes empty again
4. **Slot Available**: Time slot is now available for new courses

#### Safety Features
- **Confirmation Dialog**: Prevents accidental deletions
- **Visual Feedback**: Clear indication of what will be deleted
- **Undo Option**: Can add the course back if needed

---

## Export Functions

### PDF Export

#### Generating PDF Reports
1. Navigate to the generated routine
2. Click "Download Routine as PDF" button
3. The PDF will download automatically
4. Open the PDF to view the report

#### PDF Features
- **Professional Layout**: Clean, organized design
- **BOU Branding**: Official university branding
- **Course Details**: Complete course information
- **Time Slots**: Clear time slot organization
- **Teacher Information**: Teacher names included

#### PDF Content
- **Header**: BOU logo and title
- **Semester Information**: Semester details and dates
- **Schedule Table**: Complete routine in table format
- **Footer**: Contact information and page numbers

### Excel Export

#### Generating Excel Reports
1. Navigate to the generated routine
2. Click "Download Routine as Excel" button
3. The Excel file will download automatically
4. Open the file in Microsoft Excel or similar

#### Excel Features
- **Spreadsheet Format**: Standard Excel format
- **Multiple Sheets**: Organized by date or day
- **Filtering**: Sort and filter capabilities
- **Formulas**: Calculated fields where applicable
- **Formatting**: Professional cell formatting

#### Excel Content
- **Summary Sheet**: Overview of all schedules
- **Daily Sheets**: Individual day schedules
- **Teacher Sheets**: Teacher-specific schedules
- **Course Sheets**: Course-specific schedules

### Report Customization

#### Available Options
- **Date Range**: Select specific date ranges
- **Format Options**: Choose PDF or Excel
- **Content Selection**: Include/exclude specific information
- **Layout Options**: Different table layouts

#### Custom Report Generation
1. Navigate to "Download Routines"
2. Select the desired options
3. Choose the semester and date range
4. Select the export format
5. Click "Generate Report"

---

## Troubleshooting

### Common Issues and Solutions

#### 1. Time Overlap Detection Not Working
**Problem**: System doesn't detect overlapping times
**Solutions**:
- Check time format (HH:MM)
- Verify lunch break settings
- Clear browser cache
- Check JavaScript console for errors

#### 2. Routine Generation Fails
**Problem**: Error when generating routine
**Solutions**:
- Fill in all required fields
- Resolve time conflicts
- Ensure semester has courses
- Check date range settings

#### 3. Export Functions Not Working
**Problem**: PDF/Excel export fails
**Solutions**:
- Check file permissions
- Verify required libraries
- Ensure sufficient disk space
- Check server configuration

#### 4. Performance Issues
**Problem**: Slow loading or hanging
**Solutions**:
- Clear browser cache
- Check internet connection
- Close other browser tabs
- Restart the browser

### Error Messages

#### Understanding Error Codes
- **400 Bad Request**: Invalid form data
- **403 Forbidden**: Missing permissions
- **404 Not Found**: Invalid URL
- **500 Internal Server Error**: Server problem

#### Common Error Messages
- **"Please select a semester"**: Choose a semester first
- **"Time overlap detected"**: Resolve scheduling conflicts
- **"Course not found"**: Verify course exists
- **"Invalid date range"**: Check date selections

### Getting Help

#### Support Resources
- **System Documentation**: This user manual
- **Admin Panel**: Django admin for data management
- **Error Logs**: Check browser console and server logs
- **Contact Support**: Reach out to development team

#### Reporting Issues
1. Note the exact error message
2. Record the steps that caused the issue
3. Include browser and system information
4. Contact the development team

---

## Best Practices

### Data Management

#### Teacher Management
- **Use Consistent Names**: Standardize teacher name formats
- **Short Names**: Use abbreviations for display
- **Regular Updates**: Keep teacher information current
- **Backup Data**: Export teacher data regularly

#### Course Management
- **Unique Codes**: Ensure course codes are unique
- **Descriptive Names**: Use clear, descriptive course names
- **Teacher Assignment**: Assign teachers promptly
- **Regular Review**: Review course assignments periodically

#### Semester Management
- **Clear Naming**: Use descriptive semester names
- **Date Planning**: Plan semester dates in advance
- **Holiday Updates**: Keep holiday lists current
- **Contact Information**: Maintain current contact details

### Routine Generation

#### Planning Phase
- **Review Requirements**: Understand course requirements
- **Teacher Availability**: Consider teacher schedules
- **Time Constraints**: Account for lunch breaks and holidays
- **Conflict Prevention**: Plan to avoid scheduling conflicts

#### Generation Process
- **Start Early**: Begin routine generation well in advance
- **Test Scenarios**: Try different scheduling options
- **Validate Results**: Check generated routines carefully
- **Iterate**: Make adjustments as needed

#### Quality Assurance
- **Conflict Checking**: Verify no time overlaps
- **Teacher Load**: Ensure balanced teacher assignments
- **Student Impact**: Consider student schedule conflicts
- **Resource Utilization**: Optimize time slot usage

### System Usage

#### Performance Optimization
- **Regular Maintenance**: Clear cache and cookies
- **Efficient Navigation**: Use direct links when possible
- **Batch Operations**: Use bulk operations for efficiency
- **Data Backup**: Export important data regularly

#### Security Practices
- **Secure Login**: Use strong passwords
- **Logout**: Always logout when finished
- **Access Control**: Limit admin access appropriately
- **Data Protection**: Protect sensitive information

#### Collaboration
- **Communication**: Coordinate with other users
- **Documentation**: Document changes and decisions
- **Training**: Train new users on system features
- **Feedback**: Provide feedback for improvements

### Maintenance

#### Regular Tasks
- **Data Backup**: Backup database regularly
- **User Management**: Review and update user accounts
- **System Updates**: Keep system updated
- **Performance Monitoring**: Monitor system performance

#### Seasonal Tasks
- **Semester Preparation**: Prepare for new semesters
- **Data Cleanup**: Clean up old data
- **User Training**: Train new semester users
- **System Review**: Review and optimize system

---

## Conclusion

The BOU Routine Generator provides a comprehensive solution for academic schedule management. By following this user manual, you can effectively:

- **Manage Academic Data**: Teachers, courses, and semesters
- **Generate Schedules**: Create conflict-free academic routines
- **Edit Routines**: Modify schedules interactively
- **Export Reports**: Generate professional PDF and Excel reports
- **Resolve Issues**: Troubleshoot common problems
- **Optimize Usage**: Follow best practices for efficiency

### Key Takeaways
- **Start with Planning**: Plan your routine generation process
- **Use Interactive Features**: Take advantage of real-time editing
- **Validate Results**: Always check for conflicts and errors
- **Export Regularly**: Generate reports for distribution
- **Maintain Data**: Keep information current and accurate
- **Seek Help**: Use available support resources

### Next Steps
1. **Explore Features**: Try all system features
2. **Practice**: Generate test routines
3. **Customize**: Adapt to your specific needs
4. **Train Others**: Share knowledge with colleagues
5. **Provide Feedback**: Help improve the system

For additional support or questions, please contact the development team or refer to the technical documentation.

---

**Manual Version**: 1.0  
**Last Updated**: January 2025  
**For Technical Support**: Contact the development team through GitHub profiles 