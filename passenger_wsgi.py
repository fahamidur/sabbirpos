import os
import sys
import logging

# Configure logging
logging.basicConfig(
    filename='passenger_wsgi.log',
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

try:
    # Add your project directory to the sys.path
    project_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, project_dir)
    logging.info(f"Added project directory to path: {project_dir}")

    # Set the Django settings module
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')
    logging.info("Set DJANGO_SETTINGS_MODULE to main.settings")

    # Import the Django WSGI application
    from main.wsgi import application
    logging.info("Successfully imported WSGI application")

except Exception as e:
    logging.error(f"Error in passenger_wsgi.py: {str(e)}")
    raise
