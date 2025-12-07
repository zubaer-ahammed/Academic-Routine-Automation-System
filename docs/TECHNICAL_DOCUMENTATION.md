# BOU Routine Generator - Technical Documentation

**Developer Guide and Technical Reference**

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Database Design](#database-design)
3. [API Reference](#api-reference)
4. [Frontend Architecture](#frontend-architecture)
5. [Performance Optimizations](#performance-optimizations)
6. [Security Considerations](#security-considerations)
7. [Deployment Guide](#deployment-guide)
8. [Development Setup](#development-setup)
9. [Testing Strategy](#testing-strategy)
10. [Maintenance Procedures](#maintenance-procedures)

---

## System Architecture

### Technology Stack

#### Backend
- **Framework**: Django 4.2.20
- **Language**: Python 3.8+
- **Database**: SQLite (Development) / PostgreSQL (Production)
- **Template Engine**: Django Templates
- **Authentication**: Django Admin Authentication

#### Frontend
- **Framework**: Bootstrap 5.3.0
- **JavaScript**: jQuery 3.6.0, Vanilla JavaScript
- **CSS**: Bootstrap CSS, Custom CSS
- **Date/Time**: Moment.js, Flatpickr, MDTimePicker
- **AJAX**: jQuery AJAX for API calls

#### External Libraries
- **PDF Generation**: ReportLab 4.4.1
- **Excel Export**: XlsxWriter 3.2.3
- **Image Processing**: Pillow 11.2.1
- **Date Handling**: Moment.js, Flatpickr

### System Components

#### 1. Django Application Structure
```
bou_routines_generator/
├── bou_routines_app/          # Main Django app
│   ├── models.py              # Database models
│   ├── views.py               # View functions
│   ├── urls.py                # URL routing
│   ├── forms.py               # Django forms
│   ├── admin.py               # Admin interface
│   └── management/            # Custom commands
├── bou_routines_generator/    # Project settings
│   ├── settings.py            # Django settings
│   ├── urls.py                # Main URL configuration
│   └── wsgi.py                # WSGI configuration
├── templates/                 # HTML templates
├── static/                    # Static files
└── manage.py                  # Django management script
```

#### 2. Core Modules
- **Models**: Data structure definitions
- **Views**: Business logic and request handling
- **Templates**: User interface templates
- **Static Files**: CSS, JavaScript, images
- **Management Commands**: Custom Django commands

#### 3. Data Flow
```
User Request → URL Router → View Function → Model Query → Template Render → Response
```

---

## Database Design

### Entity Relationship Diagram

```
Teacher (1) ←→ (N) Course (N) ←→ (1) Semester
    ↓              ↓              ↓
    ↓              ↓              ↓
CurrentRoutine ←→ SemesterCourse ←→ NewRoutine
```

### Model Definitions

#### Teacher Model
```python
class Teacher(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    short_name = models.CharField(max_length=50, blank=True, null=True, unique=True)
    
    def __str__(self):
        return self.name
```

**Fields**:
- `id`: Primary key, auto-incrementing
- `name`: Full teacher name (unique)
- `short_name`: Abbreviated name for display

**Relationships**:
- One-to-Many with Course (one teacher can teach multiple courses)

#### Semester Model
```python
class Semester(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=10, unique=True)
    order = models.IntegerField(default=0)
    semester_full_name = models.CharField(max_length=100, blank=True, null=True)
    term = models.CharField(max_length=50, blank=True, null=True)
    session = models.CharField(max_length=50, blank=True, null=True)
    study_center = models.CharField(max_length=100, blank=True, null=True)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    contact_person_designation = models.CharField(max_length=100, blank=True, null=True)
    contact_person_phone = models.CharField(max_length=30, blank=True, null=True)
    contact_person_email = models.EmailField(blank=True, null=True)
    lunch_break_start = models.TimeField(null=True, blank=True)
    lunch_break_end = models.TimeField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    holidays = models.TextField(null=True, blank=True)
```

**Fields**:
- `id`: Primary key, auto-incrementing
- `name`: Semester identifier (unique)
- `order`: Display order for dropdowns
- `semester_full_name`: Complete semester name
- `term`, `session`: Academic period information
- `study_center`: Study center details
- `contact_person*`: Contact information fields
- `lunch_break_*`: Lunch break time configuration
- `start_date`, `end_date`: Semester date range
- `holidays`: Comma-separated holiday dates

#### Course Model
```python
class Course(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, default="", unique=True)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    
    def __str__(self):
        return self.code
```

**Fields**:
- `id`: Primary key, auto-incrementing
- `code`: Course code (unique)
- `name`: Course name (unique)
- `teacher`: Foreign key to Teacher model

#### SemesterCourse Model
```python
class SemesterCourse(models.Model):
    id = models.AutoField(primary_key=True)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    number_of_classes = models.PositiveIntegerField(default=1)
    
    class Meta:
        unique_together = ('semester', 'course')
```

**Fields**:
- `id`: Primary key, auto-incrementing
- `semester`: Foreign key to Semester model
- `course`: Foreign key to Course model
- `number_of_classes`: Number of classes per week

**Constraints**:
- Unique constraint on semester-course combination

#### CurrentRoutine Model
```python
class CurrentRoutine(models.Model):
    id = models.AutoField(primary_key=True)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    day = models.CharField(max_length=10, choices=DAYS)
    
    @property
    def teacher(self):
        return self.course.teacher
```

**Fields**:
- `id`: Primary key, auto-incrementing
- `semester`: Foreign key to Semester model
- `course`: Foreign key to Course model
- `start_time`, `end_time`: Class time slots
- `day`: Day of the week (Friday/Saturday)

#### NewRoutine Model
```python
class NewRoutine(models.Model):
    id = models.AutoField(primary_key=True)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    day = models.CharField(max_length=10, choices=DAYS)
    class_date = models.DateField()
    
    class Meta:
        ordering = ['class_date', 'start_time']
```

**Fields**:
- `id`: Primary key, auto-incrementing
- `semester`: Foreign key to Semester model
- `course`: Foreign key to Course model
- `start_time`, `end_time`: Class time slots
- `day`: Day of the week
- `class_date`: Specific date for the class

### Database Migrations

#### Migration History
- **0001_initial.py**: Initial model creation
- **0002_course_name.py**: Added course name field
- **0003_alter_course_id_alter_currentroutine_id_and_more.py**: ID field modifications
- **0004_semestercourse.py**: Added SemesterCourse model
- **0005_remove_currentroutine_time_slot_and_more.py**: Removed time slot fields
- **0006_remove_semestercourse_teacher.py**: Removed teacher from SemesterCourse
- **0007_remove_currentroutine_teacher.py**: Removed teacher from CurrentRoutine
- **0008_alter_newroutine_options.py**: Modified NewRoutine options
- **0009_semester_lunch_break_end_semester_lunch_break_start.py**: Added lunch break fields
- **0010_remove_newroutine_teacher.py**: Removed teacher from NewRoutine
- **0011_semester_date_range.py**: Added date range fields
- **0012_remove_semester_date_range_semester_end_date_and_more.py**: Cleaned up date fields
- **0013_semester_holidays.py**: Added holidays field
- **0014_semestercourse_number_of_classes.py**: Added number of classes field
- **0015_semester_contact_person_and_more.py**: Added contact person fields
- **0016_teacher_short_name.py**: Added teacher short name
- **0017_semester_order.py**: Added semester order field
- **0018_alter_course_code.py**: Modified course code field
- **0019_alter_newroutine_options_alter_course_name_and_more.py**: Various field modifications
- **0020_alter_currentroutine_unique_together.py**: Added unique constraints

---

## API Reference

### Core Endpoints

#### 1. Generate Routine
```http
GET /generate/
POST /generate/
```

**Purpose**: Main routine generation interface

**GET Parameters**:
- `semester`: Semester ID (optional)

**POST Data**:
```json
{
    "semester": "1",
    "date_range": "01/01/2024 - 05/31/2024",
    "govt_holiday_dates": "2024-01-01,2024-01-26",
    "lunch_break_start": "13:00",
    "lunch_break_end": "14:00",
    "enforce_lunch_break": "1",
    "update_semester_lunch_break": "1",
    "course_code[]": ["1", "2", "3"],
    "day[]": ["Friday", "Saturday", "Friday"],
    "start_time[]": ["09:00", "10:30", "14:00"],
    "end_time[]": ["10:30", "12:00", "15:30"]
}
```

**Response**: HTML page with generated routine

#### 2. Semester Courses Management
```http
GET /semester-courses/
POST /semester-courses/
```

**Purpose**: Manage course assignments to semesters

**GET Response**: HTML form for semester course management

**POST Data**:
```json
{
    "semester": "1",
    "courses": ["1", "2", "3"],
    "number_of_classes": ["1", "2", "1"]
}
```

#### 3. Download Routines
```http
GET /download-routines/
```

**Purpose**: Interface for downloading generated routines

**Response**: HTML page with download options

### AJAX Endpoints

#### 1. Get Semester Courses
```http
GET /get-semester-courses/
```

**Parameters**:
- `semester_id`: Semester ID

**Response**:
```json
{
    "courses": [
        {
            "id": 1,
            "code": "CSE101",
            "name": "Introduction to Computer Science",
            "teacher_id": 1,
            "teacher_name": "Dr. John Smith"
        }
    ],
    "lunch_break": {
        "start": "13:00",
        "end": "14:00"
    },
    "date_range": {
        "start_date": "01/01/2024",
        "end_date": "05/31/2024"
    },
    "holidays": "2024-01-01,2024-01-26"
}
```

#### 2. Check Time Overlap
```http
POST /check-time-overlap/
```

**Data**:
```json
{
    "day": "Friday",
    "start_time": "09:00",
    "end_time": "10:30",
    "teacher_id": 1,
    "course_id": 1,
    "semester_id": 1,
    "enforce_lunch_break": "1",
    "lunch_break_start": "13:00",
    "lunch_break_end": "14:00"
}
```

**Response**:
```json
{
    "overlaps": [
        {
            "course": "CSE101",
            "course_name": "Introduction to Computer Science",
            "teacher": "Dr. John Smith",
            "start": "09:00",
            "end": "10:30"
        }
    ],
    "success": true
}
```

#### 3. Update Routine Course
```http
POST /update-routine-course/
```

**Data** (for updates):
```json
{
    "course_id": 1,
    "routine_id": 1,
    "csrfmiddlewaretoken": "token_value"
}
```

**Data** (for new entries):
```json
{
    "course_id": 1,
    "date": "2024-01-01",
    "day": "Friday",
    "time_slot": 0,
    "semester_id": 1,
    "start_time": "09:00",
    "end_time": "10:30",
    "csrfmiddlewaretoken": "token_value"
}
```

**Response**:
```json
{
    "success": true,
    "course_code": "CSE101",
    "teacher_name": "Dr. John Smith",
    "routine_id": 1
}
```

#### 4. Remove Routine Course
```http
POST /remove-routine-course/
```

**Data**:
```json
{
    "routine_id": 1,
    "csrfmiddlewaretoken": "token_value"
}
```

**Response**:
```json
{
    "success": true
}
```

#### 5. Export to PDF
```http
GET /export-to-pdf/{semester_id}/
```

**Parameters**:
- `semester_id`: Semester ID in URL path

**Response**: PDF file download

#### 6. Export to Excel
```http
GET /export-to-excel/{semester_id}/
```

**Parameters**:
- `semester_id`: Semester ID in URL path

**Response**: Excel file download

### Error Handling

#### Standard Error Response
```json
{
    "success": false,
    "error": "Error message description"
}
```

#### Common Error Codes
- **400**: Bad Request - Invalid input data
- **403**: Forbidden - CSRF token missing or invalid
- **404**: Not Found - Resource not found
- **500**: Internal Server Error - Server-side error

---

## Frontend Architecture

### JavaScript Structure

#### Main Application Logic
```javascript
$(function() {
    // Initialize components
    initDatePickers();
    initTimePickers();
    initOverlapChecking();
    
    // Event handlers
    setupEventListeners();
    setupAJAXHandlers();
});
```

#### Key JavaScript Functions

##### 1. Time Overlap Checking
```javascript
function checkTimeOverlap(row) {
    const courseId = row.find('select[name="course_code[]"]').val();
    const day = row.find('select[name="day[]"]').val();
    const startTime = row.find('input[name="start_time[]"]').val();
    const endTime = row.find('input[name="end_time[]"]').val();
    
    // AJAX call to check overlaps
    $.ajax({
        url: "/check-time-overlap/",
        method: "POST",
        data: {
            day: day,
            start_time: startTime,
            end_time: endTime,
            teacher_id: teacherId,
            course_id: courseId,
            semester_id: semesterId
        },
        success: function(data) {
            handleOverlapResponse(data, row);
        }
    });
}
```

##### 2. Throttled Overlap Checking
```javascript
function throttledCheckTimeOverlap(row) {
    if (isCheckingOverlap) {
        pendingOverlapChecks.push({ row: row, rowId: rowId });
        return;
    }
    isCheckingOverlap = true;
    checkTimeOverlap(row);
}
```

##### 3. Interactive Routine Editing
```javascript
$(document).on('click', '.course-cell, .empty-cell', function(e) {
    if ($(e.target).closest('.edit-controls').length) {
        return;
    }
    
    const cell = $(this);
    const isEmptyCell = cell.hasClass('empty-cell');
    
    // Load courses for editing
    loadCoursesForEditing(cell, isEmptyCell);
});
```

### CSS Architecture

#### Component-Based Styling
```css
/* Course cell styles */
.course-cell {
    transition: all 0.2s ease;
}

.course-cell:hover {
    background-color: #0056b3 !important;
    transform: scale(1.02);
}

/* Empty cell styles */
.empty-cell {
    transition: all 0.2s ease;
}

.empty-cell:hover {
    background-color: #e9ecef !important;
    transform: scale(1.02);
}

/* Edit controls */
.edit-controls {
    background-color: rgba(255, 255, 255, 0.95);
    border-radius: 4px;
    padding: 8px;
}
```

#### Responsive Design
```css
/* Mobile responsiveness */
@media (max-width: 768px) {
    .container-box-bou {
        max-width: 95%;
        padding: 1rem;
    }
    
    .generate-routine-table {
        font-size: 0.7em;
    }
}
```

### Template Structure

#### Base Template
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generate New Routine</title>
    <!-- CSS and JavaScript includes -->
</head>
<body>
    <!-- Navigation -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <!-- Navigation content -->
    </nav>
    
    <!-- Main content -->
    <div class="container container-box-bou">
        <!-- Page content -->
    </div>
    
    <!-- Footer -->
    <footer class="bg-dark text-white text-center py-3 mt-5">
        <!-- Footer content -->
    </footer>
</body>
</html>
```

#### Dynamic Content Generation
```html
{% for row in routine_table_rows %}
<tr>
    <td class="text-center fw-bold align-middle" data-date="{{ row.date|date:'Y-m-d' }}">
        {{ row.date|date:"d/m/Y" }}
    </td>
    <td class="text-center fw-bold align-middle">{{ row.day }}</td>
    {% for cell in row.cells %}
        {% if cell.content %}
            <!-- Course cell -->
        {% else %}
            <!-- Empty cell -->
        {% endif %}
    {% endfor %}
</tr>
{% endfor %}
```

---

## Performance Optimizations

### Frontend Optimizations

#### 1. Request Throttling
```javascript
// Prevent multiple simultaneous requests
let isCheckingOverlap = false;
let pendingOverlapChecks = [];

function throttledCheckTimeOverlap(row) {
    if (isCheckingOverlap) {
        pendingOverlapChecks.push({ row: row, rowId: rowId });
        return;
    }
    isCheckingOverlap = true;
    checkTimeOverlap(row);
}
```

#### 2. Debouncing
```javascript
// Delay bulk operations
let overlapCheckTimeout;

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

#### 3. Queue Processing
```javascript
function processPendingChecks() {
    if (pendingOverlapChecks.length > 0) {
        const nextCheck = pendingOverlapChecks.shift();
        checkTimeOverlap(nextCheck.row);
    } else {
        isCheckingOverlap = false;
        $('#globalOverlapChecking').hide();
    }
}
```

### Backend Optimizations

#### 1. Database Query Optimization
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

#### 2. Caching Implementation
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

def set_cached_semester_routines(semester_id, data):
    cache_key = f"semester_routines_{semester_id}"
    _semester_routines_cache[cache_key] = (data, time.time())
```

#### 3. Batch Processing
```python
def bulk_create_routines(routine_data_list):
    """Create multiple routines efficiently"""
    routines = []
    for data in routine_data_list:
        routine = NewRoutine(
            semester_id=data['semester_id'],
            course_id=data['course_id'],
            start_time=data['start_time'],
            end_time=data['end_time'],
            day=data['day'],
            class_date=data['class_date']
        )
        routines.append(routine)
    
    NewRoutine.objects.bulk_create(routines)
```

### Performance Monitoring

#### 1. Response Time Tracking
```python
import time
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

def performance_monitor(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f"{func.__name__} took {end_time - start_time:.2f} seconds")
        return result
    return wrapper
```

#### 2. Database Query Monitoring
```python
from django.db import connection
from django.conf import settings

if settings.DEBUG:
    def log_queries():
        for query in connection.queries:
            print(f"Query: {query['sql']}")
            print(f"Time: {query['time']}")
```

---

## Security Considerations

### CSRF Protection
```python
# Django CSRF protection
from django.views.decorators.csrf import csrf_protect

@csrf_protect
def update_routine_course(request):
    # View implementation
    pass
```

### Input Validation
```python
from django.core.validators import validate_time
from django.core.exceptions import ValidationError

def validate_time_range(start_time, end_time):
    """Validate time range input"""
    try:
        validate_time(start_time)
        validate_time(end_time)
        if start_time >= end_time:
            raise ValidationError("Start time must be before end time")
    except ValidationError as e:
        return False, str(e)
    return True, None
```

### SQL Injection Prevention
```python
# Use Django ORM to prevent SQL injection
# Good practice
routines = CurrentRoutine.objects.filter(semester_id=semester_id)

# Avoid raw SQL queries
# Bad practice
# routines = CurrentRoutine.objects.raw(f"SELECT * FROM routines WHERE semester_id = {semester_id}")
```

### XSS Prevention
```html
<!-- Use Django template escaping -->
{{ user_input|escape }}

<!-- Or use the safe filter only when necessary -->
{{ trusted_content|safe }}
```

### File Upload Security
```python
import os
from django.core.files.storage import default_storage

def secure_file_upload(file):
    """Secure file upload handling"""
    # Validate file type
    allowed_extensions = ['.pdf', '.xlsx']
    file_extension = os.path.splitext(file.name)[1].lower()
    
    if file_extension not in allowed_extensions:
        raise ValidationError("Invalid file type")
    
    # Validate file size (max 10MB)
    if file.size > 10 * 1024 * 1024:
        raise ValidationError("File too large")
    
    return file
```

---

## Deployment Guide

### Development Environment

#### 1. Local Setup
```bash
# Clone repository
git clone <repository-url>
cd bou_routines_generator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup database
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

#### 2. Environment Variables
```bash
# .env file
DEBUG=True
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=localhost,127.0.0.1
```

### Production Environment

#### 1. Server Requirements
- **Operating System**: Ubuntu 20.04+ or CentOS 8+
- **Python**: 3.8+
- **Database**: PostgreSQL 12+
- **Web Server**: Nginx
- **Application Server**: Gunicorn
- **Process Manager**: Supervisor

#### 2. Production Settings
```python
# settings.py
DEBUG = False
ALLOWED_HOSTS = ['your-domain.com', 'www.your-domain.com']

# Database configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'bou_routines_db',
        'USER': 'db_user',
        'PASSWORD': 'secure_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Static files
STATIC_ROOT = '/var/www/bou_routines/static/'
STATIC_URL = '/static/'

# Security settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
```

#### 3. Nginx Configuration
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location /static/ {
        alias /var/www/bou_routines/static/;
    }
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### 4. Gunicorn Configuration
```python
# gunicorn.conf.py
bind = "127.0.0.1:8000"
workers = 3
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 30
keepalive = 2
```

#### 5. Supervisor Configuration
```ini
[program:bou_routines]
command=/path/to/venv/bin/gunicorn --config gunicorn.conf.py bou_routines_generator.wsgi:application
directory=/path/to/bou_routines_generator
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/bou_routines/gunicorn.log
```

### Deployment Steps

#### 1. Server Preparation
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install python3 python3-pip python3-venv nginx postgresql postgresql-contrib supervisor

# Create application user
sudo useradd -m -s /bin/bash bou_user
sudo usermod -aG www-data bou_user
```

#### 2. Database Setup
```bash
# Create database
sudo -u postgres createdb bou_routines_db
sudo -u postgres createuser bou_user
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE bou_routines_db TO bou_user;"
```

#### 3. Application Deployment
```bash
# Clone application
sudo -u bou_user git clone <repository-url> /home/bou_user/bou_routines_generator

# Setup virtual environment
sudo -u bou_user python3 -m venv /home/bou_user/venv
sudo -u bou_user /home/bou_user/venv/bin/pip install -r /home/bou_user/bou_routines_generator/requirements.txt

# Configure settings
sudo -u bou_user cp /home/bou_user/bou_routines_generator/settings.py /home/bou_user/bou_routines_generator/settings_production.py

# Run migrations
sudo -u bou_user /home/bou_user/venv/bin/python /home/bou_user/bou_routines_generator/manage.py migrate

# Collect static files
sudo -u bou_user /home/bou_user/venv/bin/python /home/bou_user/bou_routines_generator/manage.py collectstatic
```

#### 4. Service Configuration
```bash
# Configure Nginx
sudo cp nginx.conf /etc/nginx/sites-available/bou_routines
sudo ln -s /etc/nginx/sites-available/bou_routines /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Configure Supervisor
sudo cp supervisor.conf /etc/supervisor/conf.d/bou_routines.conf
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start bou_routines
```

### SSL Configuration

#### 1. Let's Encrypt Setup
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

#### 2. SSL Configuration
```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    # SSL security settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    # HSTS
    add_header Strict-Transport-Security "max-age=63072000" always;
    
    # Other location blocks...
}
```

---

## Development Setup

### IDE Configuration

#### VS Code Settings
```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true,
    "python.formatting.provider": "black",
    "editor.formatOnSave": true,
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true
    }
}
```

#### PyCharm Configuration
1. **Project Interpreter**: Set to virtual environment
2. **Django Support**: Enable Django support
3. **Database Tools**: Configure database connection
4. **Run Configuration**: Setup Django run configuration

### Code Quality Tools

#### 1. Linting
```bash
# Install linting tools
pip install flake8 pylint black

# Run linting
flake8 bou_routines_app/
pylint bou_routines_app/
black bou_routines_app/
```

#### 2. Type Checking
```bash
# Install mypy
pip install mypy

# Run type checking
mypy bou_routines_app/
```

#### 3. Testing
```bash
# Run tests
python manage.py test

# Run with coverage
pip install coverage
coverage run --source='.' manage.py test
coverage report
coverage html
```

### Git Workflow

#### 1. Branch Strategy
```bash
# Main branches
main          # Production-ready code
develop       # Development integration
feature/*     # Feature development
hotfix/*      # Emergency fixes
```

#### 2. Commit Guidelines
```bash
# Commit message format
type(scope): description

# Examples
feat(routine): add interactive editing functionality
fix(overlap): resolve time conflict detection issue
docs(api): update API documentation
test(views): add unit tests for routine generation
```

#### 3. Pull Request Process
1. Create feature branch from develop
2. Implement changes with tests
3. Run linting and tests
4. Create pull request to develop
5. Code review and approval
6. Merge to develop
7. Deploy to staging
8. Merge to main for production

---

## Testing Strategy

### Unit Testing

#### 1. Model Tests
```python
# tests/test_models.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from .models import Teacher, Course, Semester, CurrentRoutine

class TeacherModelTest(TestCase):
    def setUp(self):
        self.teacher = Teacher.objects.create(
            name="Dr. John Smith",
            short_name="JSmith"
        )
    
    def test_teacher_creation(self):
        self.assertEqual(self.teacher.name, "Dr. John Smith")
        self.assertEqual(self.teacher.short_name, "JSmith")
    
    def test_teacher_str_representation(self):
        self.assertEqual(str(self.teacher), "Dr. John Smith")
```

#### 2. View Tests
```python
# tests/test_views.py
from django.test import TestCase, Client
from django.urls import reverse
from .models import Teacher, Course, Semester

class GenerateRoutineViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = Teacher.objects.create(name="Dr. Smith")
        self.course = Course.objects.create(
            code="CSE101",
            name="Computer Science",
            teacher=self.teacher
        )
        self.semester = Semester.objects.create(name="Fall 2024")
    
    def test_generate_routine_get(self):
        response = self.client.get(reverse('generate-routine'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'bou_routines_app/generate_routine.html')
    
    def test_generate_routine_post(self):
        data = {
            'semester': self.semester.id,
            'date_range': '01/01/2024 - 05/31/2024',
            'course_code[]': [self.course.id],
            'day[]': ['Friday'],
            'start_time[]': ['09:00'],
            'end_time[]': ['10:30']
        }
        response = self.client.post(reverse('generate-routine'), data)
        self.assertEqual(response.status_code, 200)
```

#### 3. API Tests
```python
# tests/test_api.py
from django.test import TestCase
from django.urls import reverse
import json

class APITest(TestCase):
    def test_get_semester_courses(self):
        response = self.client.get(
            reverse('get-semester-courses'),
            {'semester_id': 1}
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('courses', data)
    
    def test_check_time_overlap(self):
        data = {
            'day': 'Friday',
            'start_time': '09:00',
            'end_time': '10:30',
            'teacher_id': 1,
            'semester_id': 1
        }
        response = self.client.post(
            reverse('check-time-overlap'),
            data
        )
        self.assertEqual(response.status_code, 200)
```

### Integration Testing

#### 1. End-to-End Tests
```python
# tests/test_integration.py
from django.test import TestCase
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class IntegrationTest(TestCase):
    def setUp(self):
        self.driver = webdriver.Chrome()
        self.driver.implicitly_wait(10)
    
    def test_routine_generation_flow(self):
        # Navigate to generate routine page
        self.driver.get("http://localhost:8000/generate/")
        
        # Select semester
        semester_select = self.driver.find_element(By.ID, "semester")
        semester_select.click()
        semester_option = self.driver.find_element(By.CSS_SELECTOR, "option[value='1']")
        semester_option.click()
        
        # Add course
        course_select = self.driver.find_element(By.CSS_SELECTOR, "select[name='course_code[]']")
        course_select.click()
        course_option = self.driver.find_element(By.CSS_SELECTOR, "option[value='1']")
        course_option.click()
        
        # Submit form
        submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_button.click()
        
        # Verify routine generation
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "generate-routine-table"))
        )
    
    def tearDown(self):
        self.driver.quit()
```

### Performance Testing

#### 1. Load Testing
```python
# tests/test_performance.py
import time
from django.test import TestCase
from django.urls import reverse

class PerformanceTest(TestCase):
    def test_routine_generation_performance(self):
        start_time = time.time()
        
        # Generate routine with multiple courses
        data = {
            'semester': 1,
            'date_range': '01/01/2024 - 05/31/2024',
            'course_code[]': [1, 2, 3, 4, 5],
            'day[]': ['Friday', 'Saturday', 'Friday', 'Saturday', 'Friday'],
            'start_time[]': ['09:00', '10:30', '14:00', '15:30', '16:00'],
            'end_time[]': ['10:30', '12:00', '15:30', '17:00', '17:30']
        }
        
        response = self.client.post(reverse('generate-routine'), data)
        end_time = time.time()
        
        self.assertEqual(response.status_code, 200)
        self.assertLess(end_time - start_time, 5.0)  # Should complete within 5 seconds
```

---

## Maintenance Procedures

### Regular Maintenance

#### 1. Database Maintenance
```sql
-- PostgreSQL maintenance
VACUUM ANALYZE;
REINDEX DATABASE bou_routines_db;

-- Check for orphaned records
SELECT COUNT(*) FROM new_routine WHERE course_id NOT IN (SELECT id FROM course);
SELECT COUNT(*) FROM current_routine WHERE course_id NOT IN (SELECT id FROM course);
```

#### 2. Log Management
```bash
# Rotate log files
sudo logrotate /etc/logrotate.d/bou_routines

# Monitor log sizes
du -sh /var/log/bou_routines/
```

#### 3. Backup Procedures
```bash
#!/bin/bash
# backup.sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/bou_routines"

# Database backup
pg_dump bou_routines_db > $BACKUP_DIR/db_backup_$DATE.sql

# Application backup
tar -czf $BACKUP_DIR/app_backup_$DATE.tar.gz /home/bou_user/bou_routines_generator/

# Clean old backups (keep last 30 days)
find $BACKUP_DIR -name "*.sql" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
```

### Monitoring

#### 1. System Monitoring
```bash
# Monitor system resources
htop
df -h
free -h

# Monitor application
sudo supervisorctl status bou_routines
sudo systemctl status nginx
```

#### 2. Application Monitoring
```python
# Add monitoring to views
import logging
import time
from django.core.cache import cache

logger = logging.getLogger(__name__)

def monitor_view_performance(view_func):
    def wrapper(request, *args, **kwargs):
        start_time = time.time()
        result = view_func(request, *args, **kwargs)
        end_time = time.time()
        
        execution_time = end_time - start_time
        logger.info(f"{view_func.__name__} executed in {execution_time:.2f} seconds")
        
        # Cache performance metrics
        cache_key = f"performance_{view_func.__name__}"
        cache.set(cache_key, execution_time, 3600)
        
        return result
    return wrapper
```

### Troubleshooting

#### 1. Common Issues
```bash
# Check application logs
sudo tail -f /var/log/bou_routines/gunicorn.log

# Check Nginx logs
sudo tail -f /var/log/nginx/error.log

# Check database connections
sudo -u postgres psql -c "SELECT * FROM pg_stat_activity;"

# Restart services
sudo supervisorctl restart bou_routines
sudo systemctl restart nginx
```

#### 2. Performance Issues
```python
# Debug slow queries
from django.db import connection
from django.conf import settings

if settings.DEBUG:
    for query in connection.queries:
        print(f"Query: {query['sql']}")
        print(f"Time: {query['time']}")
```

#### 3. Memory Issues
```bash
# Check memory usage
ps aux | grep gunicorn
free -h

# Restart workers if needed
sudo supervisorctl restart bou_routines
```

---

## Conclusion

This technical documentation provides a comprehensive guide for developers working with the BOU Routine Generator system. It covers:

- **System Architecture**: Complete technical overview
- **Database Design**: Detailed model definitions and relationships
- **API Reference**: Complete API documentation
- **Frontend Architecture**: JavaScript and CSS structure
- **Performance Optimizations**: Caching and optimization strategies
- **Security Considerations**: Security best practices
- **Deployment Guide**: Production deployment procedures
- **Development Setup**: Development environment configuration
- **Testing Strategy**: Comprehensive testing approach
- **Maintenance Procedures**: Ongoing maintenance tasks

### Key Technical Highlights

1. **Scalable Architecture**: Django-based MVC architecture
2. **Performance Optimized**: Caching, throttling, and query optimization
3. **Security Focused**: CSRF protection, input validation, XSS prevention
4. **Production Ready**: Comprehensive deployment and monitoring
5. **Maintainable Code**: Well-documented, tested, and structured

### Future Technical Enhancements

1. **Microservices**: Break down into smaller, focused services
2. **Containerization**: Docker deployment for easier scaling
3. **Cloud Integration**: AWS/Azure deployment options
4. **Advanced Caching**: Redis for distributed caching
5. **API Versioning**: RESTful API with versioning support
6. **Real-time Updates**: WebSocket integration for live updates

For additional technical support or questions, please contact the development team through the provided GitHub profiles.

---

**Document Version**: 1.0  
**Last Updated**: January 2025  
**Technical Contact**: Development team via GitHub profiles 