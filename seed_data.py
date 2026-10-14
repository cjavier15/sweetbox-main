import os
import django

# Initialize Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sweetbox_backend.settings')
django.setup()

from django.core.management import call_command

def seed_database():
    print("Executing official Sweet Box seed_data management command...")
    call_command('seed_data')

if __name__ == "__main__":
    seed_database()