# Project Evaluation System

Minimal Django project for student mini project workflow.

## Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

   - `pip install django`

3. Run migrations:

   - `python manage.py migrate`

4. Create users:

   - `python manage.py createsuperuser`

5. Set user roles in Django shell:

   - `python manage.py shell`
   - `from django.contrib.auth.models import User`
   - `from core.models import UserProfile`
   - `u = User.objects.get(username="<username>")`
   - `u.userprofile.role = "guide"  # or "student"`
   - `u.userprofile.save()`

6. Run the server:

   - `python manage.py runserver`

Login at `/login/`.
