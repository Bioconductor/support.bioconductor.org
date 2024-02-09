import logging
from biostar.forum.settings import *
import boto3
#from biostar.recipes.settings import *

logger = logging.getLogger("biostar")

# Debugging flag.
DEBUG = True

AWS_PARAMETER_PATH = '/bioc/biostar/site_secrets'

if AWS_PARAMETER_PATH:
    ssm_client = boto3.client('ssm')
    plist = ssm_client.get_parameters_by_path(Path=AWS_PARAMETER_PATH, Recursive=True)
    param_dict = {item["Name"][len(AWS_PARAMETER_PATH) + 1:]: item["Value"] for item in plist["Parameters"]}


# Set your known secret key here.
SECRET_KEY = param_dict.get("SECRET_KEY")

# Admin users will be created automatically with DEFAULT_ADMIN_PASSWORD.
ADMINS = [
    ("Admin User", "admin@localhost")
]

# Set the default admin password.
DEFAULT_ADMIN_PASSWORD = SECRET_KEY

# Set the site domain.
SITE_DOMAIN = param_dict.get("SITE_DOMAIN")


SITE_ID = 1
HTTP_PORT = ''
PROTOCOL = 'http'

ALLOWED_HOSTS = param_dict.get("ALLOWED_HOSTS")

DATABASE_NAME = "biostardb"

DATABASES = {

    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': DATABASE_NAME,
        'USER': '',
        'PASSWORD': '',
        'HOST': '/var/run/postgresql/',
        'PORT': '',
    },
}

WSGI_APPLICATION = 'conf.run.site_wsgi.application'

# Valid options; block, disable, threaded, uwsgi, celery.
TASK_RUNNER = 'block'

SESSION_COOKIE_SECURE = True

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

try:
    # Attempts to load site secrets.
    from .site_secrets import *

    logger.info("Imported settings from .site_secrets")
except ImportError as exc:
    logger.warn(f"No secrets module could be imported: {exc}")

logger.debug(f"SITE_DOMAIN: {SITE_DOMAIN}")