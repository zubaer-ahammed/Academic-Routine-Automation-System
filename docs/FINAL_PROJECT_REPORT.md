# BOU Routine Generator - Final Project Report & User Manual

**Academic Routine Automation System for School of Science and Technology (SST), Bangladesh Open University (BOU)**

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [System Architecture](#system-architecture)
3. [Features & Functionality](#features--functionality)
4. [Technical Specifications](#technical-specifications)
5. [Installation & Setup](#installation--setup)
6. [User Guide](#user-guide)
7. [Admin Guide](#admin-guide)
8. [API Documentation](#api-documentation)
9. [Performance Optimizations](#performance-optimizations)
10. [Troubleshooting](#troubleshooting)
11. [Future Enhancements](#future-enhancements)
12. [Contributors](#contributors)

---

## Project Overview

### Purpose
The BOU Routine Generator is a comprehensive web-based application designed to automate the creation and management of academic class schedules for the School of Science and Technology at Bangladesh Open University. The system eliminates manual scheduling conflicts, ensures optimal resource utilization, and provides a user-friendly interface for routine management.

### Key Objectives
- **Automate Routine Generation**: Automatically create class schedules based on course requirements and teacher availability
- **Conflict Prevention**: Prevent time overlaps and scheduling conflicts
- **Resource Optimization**: Efficiently utilize available time slots and classroom resources
- **User-Friendly Interface**: Provide intuitive web interface for routine management
- **Export Capabilities**: Generate PDF and Excel reports for distribution
- **Real-time Updates**: Enable dynamic editing and modification of generated routines

### Target Users
- **Academic Administrators**: Manage semester courses and teacher assignments
- **Faculty Members**: View and access class schedules
- **Students**: Access class timetables
- **System Administrators**: Maintain and configure the system

---

## System Architecture

### Technology Stack
- **Backend Framework**: Django 4.2.20 (Python)
- **Database**: SQLite (Development) / PostgreSQL (Production)
- **Frontend**: HTML5, CSS3, JavaScript, Bootstrap 5.3.0
- **PDF Generation**: ReportLab 4.4.1
- **Excel Export**: XlsxWriter 3.2.3
- **Date/Time Handling**: Moment.js, Flatpickr
- **UI Components**: MDTimePicker, DateRangePicker

### System Components

#### 1. Data Models
```
Teacher → Course → SemesterCourse → CurrentRoutine → NewRoutine
```

#### 2. Core Modules
- **Routine Management**: Handle current and new routine generation
- **Course Management**: Manage semester-specific course assignments
- **Conflict Detection**: Real-time overlap checking and validation
- **Export System**: PDF and Excel report generation
- **Admin Interface**: Django admin for data management

#### 3. User Interface Layers
- **Admin Panel**: Django admin interface for data management
- **Web Interface**: Bootstrap-based responsive web application
- **API Endpoints**: AJAX-based real-time interactions

---

## Features & Functionality

### 1. Semester Management
- **Semester Creation**: Create and configure academic semesters
- **Date Range Management**: Set semester start and end dates
- **Holiday Configuration**: Define government holidays and breaks
- **Lunch Break Settings**: Configure mandatory lunch break times
- **Contact Information**: Store semester-specific contact details

### 2. Course & Teacher Management
- **Teacher Profiles**: Manage teacher information with short names
- **Course Registration**: Create courses with assigned teachers
- **Semester Course Assignment**: Assign courses to specific semesters
- **Class Count Configuration**: Set number of classes per course

### 3. Routine Generation
- **Automated Scheduling**: Generate routines based on course requirements
- **Time Slot Management**: Flexible time slot configuration
- **Day Selection**: Friday and Saturday class scheduling
- **Conflict Prevention**: Real-time overlap detection and prevention
- **Lunch Break Enforcement**: Automatic lunch break integration

### 4. Interactive Routine Management
- **Real-time Editing**: Click-to-edit routine cells
- **Dynamic Course Assignment**: Add/remove courses from time slots
- **Visual Feedback**: Color-coded conflict indicators
- **Inline Validation**: Immediate feedback on scheduling conflicts

### 5. Export & Reporting
- **PDF Generation**: Professional PDF reports with BOU branding
- **Excel Export**: Spreadsheet format for further analysis
- **Customizable Layouts**: Configurable report formats
- **Batch Processing**: Export multiple semesters simultaneously

### 6. Advanced Features
- **Performance Optimization**: Caching and request throttling
- **Responsive Design**: Mobile-friendly interface
- **Real-time Updates**: AJAX-based dynamic content updates
- **Error Handling**: Comprehensive error management and user feedback

---

## Technical Specifications

### Database Schema

#### Teacher Model
```python
class Teacher(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    short_name = models.CharField(max_length=50, blank=True, null=True, unique=True)
```

#### Semester Model
```python
class Semester(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=10, unique=True)
    order = models.IntegerField(default=0)
    semester_full_name = models.CharField(max_length=100, blank=True, null=True)
    lunch_break_start = models.TimeField(null=True, blank=True)
    lunch_break_end = models.TimeField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    holidays = models.TextField(null=True, blank=True)
```

#### Course Model
```python
class Course(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, default="", unique=True)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
```

#### Routine Models
```python
class CurrentRoutine(models.Model):
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    day = models.CharField(max_length=10, choices=DAYS)

class NewRoutine(models.Model):
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    day = models.CharField(max_length=10, choices=DAYS)
    class_date = models.DateField()
```

### API Endpoints

#### Core Endpoints
- `GET /generate/` - Main routine generation interface
- `POST /generate/` - Process routine generation
- `GET /semester-courses/` - Semester course management
- `POST /semester-courses/` - Update semester courses
- `GET /download-routines/` - Download routines interface

#### AJAX Endpoints
- `GET /get-semester-courses/` - Fetch semester courses
- `POST /check-time-overlap/` - Check for time conflicts
- `POST /update-routine-course/` - Update routine course
- `POST /remove-routine-course/` - Remove course from routine
- `GET /export-to-pdf/<semester_id>/` - Export PDF
- `GET /export-to-excel/<semester_id>/` - Export Excel

### Performance Optimizations

#### Frontend Optimizations
- **Request Throttling**: Prevent multiple simultaneous AJAX requests
- **Debouncing**: Delay bulk operations to reduce server load
- **Queue Processing**: Sequential processing of pending requests
- **Visual Feedback**: Loading indicators and progress states

#### Backend Optimizations
- **Database Query Optimization**: Select only required fields
- **Caching**: In-memory cache for frequently accessed data
- **Efficient Relationships**: Optimized foreign key queries
- **Batch Processing**: Handle multiple operations efficiently

---

## Installation & Setup

### Prerequisites
- Python 3.8 or higher
- pip (Python package installer)
- Git (for version control)

### Installation Steps

#### 1. Clone the Repository
```bash
git clone <repository-url>
cd bou_routines_generator
```

#### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

#### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 4. Database Setup
```bash
python manage.py makemigrations
python manage.py migrate
```

#### 5. Create Superuser
```bash
python manage.py createsuperuser
```

#### 6. Run Development Server
```bash
python manage.py runserver
```

### Production Deployment

#### 1. Environment Configuration
```bash
# Set environment variables
export DEBUG=False
export SECRET_KEY='your-secret-key'
export ALLOWED_HOSTS='your-domain.com'
```

#### 2. Database Configuration
```python
# settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'your_db_name',
        'USER': 'your_db_user',
        'PASSWORD': 'your_db_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

#### 3. Static Files Configuration
```bash
python manage.py collectstatic
```

#### 4. Web Server Setup
- Configure Nginx or Apache
- Set up WSGI application
- Configure SSL certificates

---

## User Guide

### Getting Started

#### 1. Access the System
- Open web browser and navigate to the application URL
- Login with admin credentials (if required)

#### 2. Navigation
- **Generate Routine**: Main routine generation interface
- **Semester Courses**: Manage course assignments
- **Download Routines**: Access generated reports

### Routine Generation Process

#### Step 1: Select Semester
1. Choose semester from dropdown menu
2. System loads existing semester data (if any)
3. Review lunch break and holiday settings

#### Step 2: Configure Date Range
1. Set semester start and end dates
2. Select government holidays (optional)
3. Verify lunch break times

#### Step 3: Add Course Schedule
1. Select course from dropdown
2. Choose day (Friday/Saturday)
3. Set start and end times
4. Add additional courses as needed

#### Step 4: Generate Routine
1. Review all course schedules
2. Resolve any time conflicts
3. Click "Generate Routine" button
4. Review generated schedule

### Interactive Routine Management

#### Editing Existing Routines
1. **Click on Course Cell**: Opens edit mode
2. **Select New Course**: Choose from dropdown
3. **Save Changes**: Click save button
4. **Cancel Changes**: Click cancel button

#### Adding New Courses
1. **Click on Empty Cell**: Opens add mode
2. **Select Course**: Choose from available courses
3. **Save Entry**: Creates new routine entry

#### Removing Courses
1. **Click Trash Icon**: Removes course from slot
2. **Confirm Action**: Confirm removal
3. **Cell Becomes Empty**: Available for new courses

### Export Functions

#### PDF Export
1. Navigate to generated routine
2. Click "Download Routine as PDF"
3. PDF downloads with BOU branding
4. Professional layout with course details

#### Excel Export
1. Navigate to generated routine
2. Click "Download Routine as Excel"
3. Excel file downloads
4. Spreadsheet format for analysis

---

## Admin Guide

### Django Admin Interface

#### Access Admin Panel
- Navigate to `/admin/`
- Login with superuser credentials

#### Managing Teachers
1. **Add Teacher**: Create new teacher profiles
2. **Edit Teacher**: Update teacher information
3. **Assign Short Names**: For display purposes

#### Managing Courses
1. **Create Course**: Add new courses with codes
2. **Assign Teachers**: Link courses to teachers
3. **Update Information**: Modify course details

#### Managing Semesters
1. **Create Semester**: Add new academic semesters
2. **Configure Settings**: Set dates, breaks, holidays
3. **Order Management**: Control display order

#### Managing Semester Courses
1. **Assign Courses**: Link courses to semesters
2. **Set Class Count**: Configure number of classes
3. **Review Assignments**: Verify course-semester relationships

### Data Management

#### Bulk Operations
- Import/Export data via Django admin
- Batch updates for multiple records
- Data validation and integrity checks

#### Backup and Recovery
- Regular database backups
- Export data to JSON/CSV formats
- Restore procedures for data recovery

---

## API Documentation

### Authentication
Most endpoints require CSRF token for POST requests:
```javascript
headers: {
    'X-CSRFToken': $('[name=csrfmiddlewaretoken]').val()
}
```

### Core API Endpoints

#### Get Semester Courses
```javascript
GET /get-semester-courses/?semester_id=<id>
Response: {
    "courses": [...],
    "lunch_break": {...},
    "date_range": {...},
    "holidays": "..."
}
```

#### Check Time Overlap
```javascript
POST /check-time-overlap/
Data: {
    day: "Friday",
    start_time: "09:00",
    end_time: "10:30",
    teacher_id: 1,
    semester_id: 1
}
Response: {
    "overlaps": [...],
    "success": true
}
```

#### Update Routine Course
```javascript
POST /update-routine-course/
Data: {
    course_id: 1,
    routine_id: 1,  // for updates
    date: "2024-01-01",  // for new entries
    day: "Friday",
    time_slot: 0
}
Response: {
    "success": true,
    "course_code": "CSE101",
    "teacher_name": "Dr. Smith"
}
```

### Error Handling
All API endpoints return consistent error responses:
```javascript
{
    "success": false,
    "error": "Error message description"
}
```

---

## Performance Optimizations

### Frontend Optimizations

#### Request Management
```javascript
// Throttled overlap checking
function throttledCheckTimeOverlap(row) {
    if (isCheckingOverlap) {
        pendingOverlapChecks.push({ row: row, rowId: rowId });
        return;
    }
    isCheckingOverlap = true;
    checkTimeOverlap(row);
}

// Debounced bulk operations
function debouncedCheckAllOverlaps() {
    if (overlapCheckTimeout) {
        clearTimeout(overlapCheckTimeout);
    }
    overlapCheckTimeout = setTimeout(function() {
        $('.course-row').each(function() {
            checkTimeOverlap($(this));
        });
    }, 500);
}
```

#### Visual Feedback
- Loading indicators for individual operations
- Global progress indicators for bulk operations
- Smooth animations and transitions
- Responsive design for mobile devices

### Backend Optimizations

#### Database Query Optimization
```python
# Optimized queries with select_related and only
routines = CurrentRoutine.objects.filter(
    semester_id=semester_id
).select_related('course', 'course__teacher').only(
    'course__id', 'course__code', 'course__name', 
    'course__teacher__name', 'course__teacher__id',
    'day', 'start_time', 'end_time'
)
```

#### Caching Implementation
```python
# In-memory cache for semester data
_semester_routines_cache = {}
_cache_timeout = 30  # seconds

def get_cached_semester_routines(semester_id):
    cache_key = f"semester_routines_{semester_id}"
    if cache_key in _semester_routines_cache:
        cache_data, timestamp = _semester_routines_cache[cache_key]
        if time.time() - timestamp < _cache_timeout:
            return cache_data
    return None
```

### Performance Monitoring
- Request response time tracking
- Database query optimization monitoring
- Memory usage analysis
- User experience metrics

---

## Troubleshooting

### Common Issues

#### 1. Time Overlap Detection Not Working
**Symptoms**: Overlaps not detected or false positives
**Solutions**:
- Check time format consistency (HH:MM)
- Verify lunch break configuration
- Clear browser cache and reload
- Check JavaScript console for errors

#### 2. Routine Generation Fails
**Symptoms**: Error during routine generation
**Solutions**:
- Verify all required fields are filled
- Check for time conflicts
- Ensure semester has assigned courses
- Review date range configuration

#### 3. Export Functions Not Working
**Symptoms**: PDF/Excel export fails
**Solutions**:
- Check file permissions
- Verify required libraries installed
- Ensure sufficient disk space
- Review server configuration

#### 4. Performance Issues
**Symptoms**: Slow loading or hanging
**Solutions**:
- Clear browser cache
- Check network connectivity
- Monitor server resources
- Review database performance

### Error Messages

#### Common Error Codes
- **400 Bad Request**: Invalid form data
- **403 Forbidden**: CSRF token missing
- **404 Not Found**: Invalid URL or resource
- **500 Internal Server Error**: Server-side error

#### Debugging Steps
1. Check browser console for JavaScript errors
2. Review Django logs for backend errors
3. Verify database connectivity
4. Test with different browsers
5. Check network connectivity

### Maintenance Procedures

#### Regular Maintenance
- Database backup and optimization
- Log file rotation and cleanup
- Cache clearing and refresh
- Performance monitoring and tuning

#### Emergency Procedures
- System backup restoration
- Database recovery procedures
- Service restart protocols
- Emergency contact procedures

---

## Future Enhancements

### Planned Features

#### 1. Advanced Scheduling
- **Room Assignment**: Automatic classroom allocation
- **Teacher Preferences**: Individual teacher scheduling preferences
- **Load Balancing**: Distribute teaching load evenly
- **Conflict Resolution**: Automated conflict resolution suggestions

#### 2. Enhanced Reporting
- **Analytics Dashboard**: Performance metrics and insights
- **Custom Reports**: User-defined report templates
- **Email Notifications**: Automated schedule notifications
- **Mobile App**: Native mobile application

#### 3. Integration Capabilities
- **LMS Integration**: Connect with learning management systems
- **Calendar Sync**: Export to Google Calendar, Outlook
- **API Extensions**: RESTful API for external integrations
- **Data Import**: Bulk data import from external sources

#### 4. User Experience Improvements
- **Drag & Drop Interface**: Visual routine editing
- **Real-time Collaboration**: Multi-user editing capabilities
- **Advanced Search**: Enhanced filtering and search options
- **Accessibility**: WCAG compliance improvements

### Technical Improvements

#### 1. Performance Enhancements
- **Redis Caching**: Distributed caching system
- **Database Optimization**: Advanced query optimization
- **CDN Integration**: Content delivery network
- **Load Balancing**: Horizontal scaling capabilities

#### 2. Security Enhancements
- **Role-based Access**: Granular permission system
- **Audit Logging**: Comprehensive activity tracking
- **Data Encryption**: Enhanced data protection
- **API Security**: OAuth2 authentication

#### 3. Scalability Improvements
- **Microservices Architecture**: Service-oriented design
- **Containerization**: Docker deployment support
- **Cloud Integration**: AWS/Azure deployment options
- **Auto-scaling**: Dynamic resource allocation

---

## Contributors

### Development Team
- **Md. Zubaer Ahammed** - Lead Developer
  - GitHub: [zubaer-ahammed](https://github.com/zubaer-ahammed/)
  - Role: Backend Development, System Architecture

- **Mojahidul Alam** - Co-Developer
  - GitHub: [Mojahidul21](https://github.com/Mojahidul21)
  - Role: Frontend Development, UI/UX Design

### Project Information
- **Institution**: Bangladesh Open University (BOU)
- **School**: School of Science and Technology (SST)
- **Project Type**: Academic Routine Automation System
- **Development Period**: 2024-2025
- **Technology Stack**: Django, Python, JavaScript, Bootstrap

### Acknowledgments
- **BOU Administration**: For project requirements and feedback
- **SST Faculty**: For domain expertise and testing
- **Open Source Community**: For libraries and frameworks used
- **Django Community**: For excellent documentation and support

---

## Conclusion

The BOU Routine Generator represents a significant advancement in academic schedule management, providing a comprehensive solution for automated routine generation and management. The system successfully addresses the challenges of manual scheduling while offering a user-friendly interface and robust functionality.

### Key Achievements
- **Automated Scheduling**: Eliminates manual scheduling conflicts
- **User-Friendly Interface**: Intuitive web-based application
- **Real-time Validation**: Prevents scheduling conflicts
- **Export Capabilities**: Professional PDF and Excel reports
- **Performance Optimized**: Efficient and responsive system
- **Scalable Architecture**: Ready for future enhancements

### Impact
- **Time Savings**: Significant reduction in manual scheduling time
- **Error Reduction**: Elimination of scheduling conflicts
- **Resource Optimization**: Better utilization of available time slots
- **User Satisfaction**: Improved experience for administrators and faculty
- **Institutional Efficiency**: Streamlined academic operations

The system is ready for production deployment and provides a solid foundation for future enhancements and integrations.

---

**Document Version**: 1.0  
**Last Updated**: January 2025  
**Contact**: For technical support or questions, please contact the development team through the provided GitHub profiles. 