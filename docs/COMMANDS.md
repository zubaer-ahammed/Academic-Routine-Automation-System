# Commands to Run BOUSST CSE Routine Generator

## Initial Setup (First Time Only)

### 1. Navigate to Project Directory
```bash
cd "/Volumes/General/Y3S1/CSE31P8 [OOP-II Lab]/New Project/bou_routines_generator"
```

### 2. Activate Virtual Environment
```bash
source venv/bin/activate
```

### 3. Install Dependencies (if not already installed)
```bash
pip install -r requirements.txt
```

### 4. Run Database Migrations
```bash
python manage.py migrate
```

### 5. Create Superuser (Admin Account)
```bash
python manage.py createsuperuser
```

## Running the Development Server

### Start the Server
```bash
python manage.py runserver
```

The application will be available at: **http://localhost:8000/**

### Run Server on Specific Port
```bash
python manage.py runserver 8080
```

### Run Server Accessible from Network
```bash
python manage.py runserver 0.0.0.0:8000
```

## Useful Management Commands

### Database Management
```bash
# Create new migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Show migration status
python manage.py showmigrations
```

### Data Setup Commands
```bash
# Setup centres (DRC, DUET)
python manage.py setup_centres

# Setup curricula (OLD, NEW)
python manage.py setup_curricula

# Setup teacher users
python manage.py setup_teacher_users

# Copy courses from DRC to DUET
python manage.py copy_courses_to_duet

# Update semester course teachers
python manage.py update_semester_course_teachers

# Verify and update teachers
python manage.py verify_and_update_teachers
```

### Django Admin
```bash
# Access admin panel at: http://localhost:8000/admin/
# Login with superuser credentials created above
```

### Check for Errors
```bash
# Check for system issues
python manage.py check

# Check for deployment issues
python manage.py check --deploy
```

### Collect Static Files (for production)
```bash
python manage.py collectstatic
```

## Quick Start (After Initial Setup)

```bash
# 1. Navigate to project
cd "/Volumes/General/Y3S1/CSE31P8 [OOP-II Lab]/New Project/bou_routines_generator"

# 2. Activate virtual environment
source venv/bin/activate

# 3. Run server
python manage.py runserver
```

## Access Points

- **Main Application**: http://localhost:8000/
- **Admin Panel**: http://localhost:8000/admin/
- **Generate Routine**: http://localhost:8000/generate/
- **Semester Courses**: http://localhost:8000/semester-courses/
- **Marks Management**: http://localhost:8000/marks/
- **Download Routines**: http://localhost:8000/download-routines/

## Stop the Server

Press `Ctrl + C` in the terminal where the server is running.

