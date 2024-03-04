import os
import uuid
import requests
import logging
from biostar.forum.settings import *
import boto3

import os
import uuid
import requests
import platform

from biostar.settings import *
from themes.bioconductor.settings import *


logger = logging.getLogger("biostar")

# Debugging flag.
DEBUG = True

AWS_PARAMETER_PATH = '/bioc/biostar/site_secrets'

if AWS_PARAMETER_PATH:
    ssm_client = boto3.client('ssm')
    plist = ssm_client.get_parameters_by_path(Path=AWS_PARAMETER_PATH, Recursive=True)
    param_dict = {item["Name"][len(AWS_PARAMETER_PATH) + 1:]: item["Value"] for item in plist["Parameters"]}


# Set your known secret key here.
SECRET_KEY = str(uuid.uuid4())

# Admin users will be created automatically with DEFAULT_ADMIN_PASSWORD.
ADMINS = [
    ("Admin User", "admin@localhost")
]

# Set the default admin password.
DEFAULT_ADMIN_PASSWORD = SECRET_KEY

# Set the site domain.
try:
    SITE_DOMAIN = requests.get('https://checkip.amazonaws.com').text.strip()
except Exception as err:
    SITE_DOMAIN = platform.node()


SITE_ID = 1
HTTP_PORT = ''
PROTOCOL = 'http'


ALLOWED_HOSTS = [SITE_DOMAIN]

LOGIN_APPS = [

    'allauth.socialaccount.providers.twitter',
    'allauth.socialaccount.providers.persona',
    'allauth.socialaccount.providers.facebook',
    'allauth.socialaccount.providers.stackexchange',
]
INSTALLED_APPS = DEFAULT_APPS + FORUM_APPS + PAGEDOWN_APP + PLANET_APPS + ACCOUNTS_APPS + LOGIN_APPS + EMAILER_APP

STRICT_TAGS = False
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

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

try:
    # Attempts to load site secrets.
    from .site_secrets import *

    logger.info("Imported settings from .site_secrets")
except ImportError as exc:
    logger.warn(f"No secrets module could be imported: {exc}")

TEMPLATE_DIRS = [os.path.join(BASE_DIR, 'templates'), os.path.join(CUSTOM_THEME, 'templates')]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': TEMPLATE_DIRS,
        #'APP_DIRS': True,
        'OPTIONS': {
            'string_if_invalid': "**MISSING**",
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.media',
                'django.contrib.messages.context_processors.messages',
                'biostar.context.main',
                'biostar.forum.context.forum'
            ],
            'loaders': [
                ('django.template.loaders.cached.Loader', [
                   'django.template.loaders.filesystem.Loader',
                    'django.template.loaders.app_directories.Loader',
                ])
            ]
        },
    },
]


CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': '127.0.0.1:11211',
    }
}

print(DATABASE_NAME, "DATABASENAME")