import difflib
import logging
import uuid, copy
import os
import subprocess
import random
from mimetypes import guess_type

import toml as hjson
from django.conf import settings
from django.contrib import messages
from django.contrib.messages.storage import fallback
from django.db.models import Q
from django.template import Template, Context
from django.template import loader
from django.test import RequestFactory
from django.utils.safestring import mark_safe
from django.utils.timezone import now

from biostar.recipes import models
from biostar.recipes import util
from biostar.recipes.const import *
from biostar.recipes.models import Data, Analysis, Job, Project, Access

logger = logging.getLogger("engine")

JOB_COLORS = {Job.SPOOLED: "spooled",
              Job.ERROR: "errored", Job.QUEUED: "queued",
              Job.RUNNING: "running", Job.COMPLETED: "completed"
              }

def get_uuid(limit=32):
    return str(uuid.uuid4())[:limit]


def generate_uuid(prefix, suffix):
    uid = f"{prefix}-{suffix}"

    return uid


def join(*args):
    return os.path.abspath(os.path.join(*args))


def access_denied_message(user, needed_access):
    """
    Generates the access denied message
    """
    tmpl = loader.get_template('widgets/access_denied_message.html')

    # Get the string format of the access.
    needed_access = dict(Access.ACCESS_CHOICES).get(needed_access)

    context = dict(user=user, needed_access=needed_access)
    return tmpl.render(context=context)


def clipboard_timestamp(item):
    """
    Parse the timestamp out of a clipboard item

   clipboard item is structured as such: ( 'key', [[value-1 ...] , <time stamp>] )
    """
    # item = ('key',[ ['value-1' ...], time stamp ]) -- >
    # --> vals = ['value-1' ...], time_stamp
    vals = item[-1] if len(item[-1]) else []
    # vals = ['value-1' ...], time_stamp --> timestamp = time_stamp
    timestamp = vals[-1] if vals else 0

    return timestamp


def most_recent(request):
    """
    Return most recent item copied in the clipboard.
    """

    board = request.session.get(settings.CLIPBOARD_NAME, {})
    # Sort board by the most recent time stamp
    board = sorted(board.items(), key=clipboard_timestamp, reverse=True)

    if len(board):
        # Drop the time stamp in returned values.
        key, vals = board[0]
        vals = vals[0] if len(vals) == 2 else vals
        return key, vals

    return "", []


def copy_file(request, fullpath):
    if not os.path.exists(fullpath):
        messages.error(request, "Path does not exist.")
        return []

    if request.user.is_anonymous:
        messages.error(request, "You need to be logged in.")
        return []

    clipboard = request.session.get(settings.CLIPBOARD_NAME, {})

    board_items, timestamp = clipboard.get(COPIED_FILES) or [[], 0]
    board_items.append(fullpath)
    board_items = list(set(board_items))
    # No duplicates in clipboard
    items = (board_items, util.now().timestamp())
    clipboard[COPIED_FILES] = items

    request.session.update({settings.CLIPBOARD_NAME: clipboard})
    return board_items


def copy_uid(request, uid, board):
    """
    Used to append instance.uid into request.session[board]
    """
    if request.user.is_anonymous:
        messages.error(request, "You need to be logged in.")
        return []

    clipboard = request.session.get(settings.CLIPBOARD_NAME, {})

    board_items, timestamp = clipboard.get(board) or [[], 0]
    board_items.append(uid)
    board_items = list(set(board_items))
    # No duplicates in clipboard
    clipboard[board] = (board_items, util.now().timestamp())

    request.session.update({settings.CLIPBOARD_NAME: clipboard})

    return board_items


def authorize_run(user, recipe):
    """
    Returns runnable.
    """
    # An anonymous user cannot run recipes.
    if user.is_anonymous:
        return False

    # Only users with access can run recipes
    readable = is_readable(user=user, project=recipe.project)

    if not readable:
        return False

    # A trusted user can run recipes that they have access to.
    if user.profile.trusted and recipe.runnable():
        return True

    # A superuser can run all recipes.
    if user.is_superuser:
        return True

    return False


def generate_script(job):
    """
    Generates a script from a job.
    """
    work_dir = job.path
    json_data = hjson.loads(job.json_text)

    # The base url to the site.
    url_base = f'{settings.PROTOCOL}://{settings.SITE_DOMAIN}{settings.HTTP_PORT}'

    # Extra context added to the script.
    runtime = dict(
        media_root=settings.MEDIA_ROOT,
        media_url=settings.MEDIA_URL,
        work_dir=work_dir, local_root=settings.LOCAL_ROOT,
        user_id=job.owner.id, user_email=job.owner.email,
        job_id=job.id, job_name=job.name,
        job_url=f'{url_base}{settings.MEDIA_URL}{job.get_url()}'.rstrip("/"),
        project_id=job.project.id, project_name=job.project.name,
        analyis_name=job.analysis.name,
        analysis_id=job.analysis.id,
        domain=settings.SITE_DOMAIN, protocol=settings.PROTOCOL,
    )

    # Add the runtime context to the data.
    json_data['runtime'] = runtime
    try:
        # Generate the script.
        template = Template(job.template)
    except Exception as exc:
        template = Template(f"Error loading script template : \n{exc}.")

    context = Context(json_data)
    script = template.render(context)

    return json_data, script


def detect_cores(request):
    # Check if the Origin in the request is allowed
    origin = request.headers.get('Origin', '')
    if origin in settings.CORS_ORIGIN_WHITELIST:
        return origin

    return ''


def link_file(source, target_dir):
    base, filename = os.path.split(source)
    target = os.path.join(target_dir, filename)

    # Link the file if it do
    if not os.path.exists(target):
        # Ensure base dir exists in target
        os.makedirs(target_dir, exist_ok=True)
        os.symlink(source, target)

    return target


def add_file(target_dir, source):
    """
    Deposit file stream into a target directory.
    """

    # Link an existing file
    if isinstance(source, str) and os.path.exists(source):
        return link_file(source=source, target_dir=target_dir)

    # Write a stream to a new file
    if hasattr(source, 'read'):
        # Get the absolute path
        dest = os.path.abspath(target_dir)

        # Create the directory
        os.makedirs(dest, exist_ok=True)

        # Get the name
        fname = source.name

        path = os.path.abspath(os.path.join(dest, fname))
        # Write the stream into file.
        util.write_stream(stream=source, dest=path)

        return path

    return


def get_project_list(user, include_public=True, include_deleted=False):
    """
    Return projects visible to a user.
    """
    privacy = None
    if include_public:
        privacy = Project.PUBLIC

    if user.is_anonymous:
        # Unauthenticated users see public projects.
        cond = Q(privacy=Project.PUBLIC)
    else:
        # Authenticated users see public projects and private projects with access rights.
        cond = Q(owner=user, privacy=Project.PRIVATE) | Q(privacy=privacy) | Q(access__user=user,
                                                                               access__access__in=[Access.READ_ACCESS,
                                                                                                   Access.WRITE_ACCESS,
                                                                                                   Access.SHARE_ACCESS])
    # Generate the query.
    if include_deleted:
        query = Project.objects.filter(cond).distinct()
    else:
        query = Project.objects.filter(cond, deleted=False).distinct()

    return query


def create_project(user, name="", uid=None, summary='', text='', stream=None, label=None,
                   privacy=Project.PRIVATE, update=False):

    name = name or "My New Project"
    # Set or create the project uid.
    uid = uid or util.get_uuid(8)

    # Attempts to select the project.
    project = Project.objects.filter(uid=uid)

    # If it is not an update request return the project unchanged.
    if project and not update:
        return project.first()

    if project:
        # Update existing project.
        current = project.first()
        text = text or current.text
        name = name or current.name
        project.update(text=text, name=name)
        project = project.first()
        logger.info(f"Updated project: {project.name} uid: {project.uid}")
    else:
        # Create a new project.
        project = Project.objects.create(label=label, name=name, uid=uid, text=text,
                                         owner=user, privacy=privacy)

        logger.info(f"Created project: {project.name} uid: {project.uid}")

    # Update the image for the project.
    if stream:
        project.image.save(stream.name, stream, save=True)

    return project


def create_analysis(project, json_text='', template='# code', uid=None, user=None, summary='', rank=100,
                    name='', text='', stream=None, security=Analysis.NOT_AUTHORIZED, update=False,
                    root=None):

    owner = user or project.owner
    analysis = Analysis.objects.filter(uid=uid)

    # Only update when there is a flag
    if analysis and update:
        # Update analysis
        current = analysis.first()
        text = text or current.text
        name = name or current.name
        template = template or current.template
        json_text = json_text or current.json_text
        analysis.update(text=text, name=name, template=template, json_text=json_text, rank=rank)
        analysis = analysis.first()
        logger.info(f"Updated analysis: uid={analysis.uid} name={analysis.name}")
    else:
        # Create a new analysis
        uid = None if analysis else uid
        analysis = Analysis.objects.create(project=project, uid=uid, json_text=json_text, rank=rank,
                                           owner=owner, name=name, text=text, security=security,
                                           template=template, root=root)

        # Update the projects lastedit user when a recipe is created
        Project.objects.filter(uid=analysis.project.uid).update(lastedit_user=user,
                                                                lastedit_date=now())

        logger.info(f"Created analysis: uid={analysis.uid} name={analysis.name}")

    if stream:
        analysis.image.save(stream.name, stream, save=True)

    return analysis


def make_job_title(recipe, data):
    """
    Creates informative job title that shows job parameters.
    """
    params = data.values()

    # Extracts the field that gets displayed for a parameter
    def extract(param):
        if not param.get("display"):
            return None
        if param.get("source"):
            return param.get("name")
        if param.get('display') == UPLOAD:
            return os.path.basename(param.get('value')) if param.get('value') else None
        return param.get("value")

    vals = map(extract, params)
    vals = filter(None, vals)
    vals = map(str, vals)
    vals = ", ".join(vals)

    if vals:
        name = f"Results for {recipe.name}: {vals}"
    else:
        name = f"Results for {recipe.name}"

    return name


def validate_recipe_run(user, recipe):
    """
    Validate that a user can run a given recipe.
    """
    if user.is_anonymous:
        msg = "You must be logged in."
        return False, msg

    if not authorize_run(user=user, recipe=recipe):
        msg = "Insufficient permission to execute recipe."
        return False, msg

    if recipe.deleted:
        msg = "Can not run a deleted recipe."
        return False, msg

    # Not trusted users have job limits.
    running_jobs = Job.objects.filter(owner=user, state=Job.RUNNING)
    if not user.profile.trusted and running_jobs.count() >= settings.MAX_RUNNING_JOBS:
        msg = "Exceeded maximum amount of running jobs allowed. Please wait until some finish."
        return False, msg

    return True, ""


def recipe_paste(instance, user, project, clone=False):

    stream = None
    root = None

    # Cascade the root if the recipe is being cloned
    if clone:
        root = instance.root if instance.is_cloned else instance

    try:
        if os.path.exists(instance.image.path):
            stream = instance.image
    except Exception as exc:
        logger.error(exc)

    recipe = create_analysis(project=project, user=user, root=root,
                             json_text=instance.json_text, security=instance.security,
                             template=instance.template,
                             name=instance.name, text=instance.text, stream=stream)
    return recipe


def data_paste(user, project, instance=None, path=""):
    dtype = instance.type if isinstance(instance, Data) else None

    # Copy an existing instance
    if instance:
        return create_data(project=project, path=instance.get_data_dir(),
                           user=user, name=instance.name,
                           type=dtype, text=instance.text)
    # Link an existing file.
    elif path and os.path.exists(path):
        return create_data(project=project, path=path, user=user)


def files_paste(board, project, user):
    """
    Apply data_paste over the files found in the clip board.
    """

    key, vals = board
    # Special case when pasting files.
    if key == COPIED_FILES:
        # Add each path in clipboard as a data object.
        data = [data_paste(project=project, user=user, path=p) for p in vals]
        return data


def clear(request, key=""):
    if not key:
        # Fetches the most recent clipboard and clears it.
        board = most_recent(request=request)
        key, vals = board

    # Reset the session clipboard
    clipboard = request.session.get(settings.CLIPBOARD_NAME, {})
    clipboard[key] = []
    request.session.update({settings.CLIPBOARD_NAME: clipboard})
    return


def paste(project, user, board, clone=False):
    """
    Paste items into project from clipboard.
    """

    obj_map = {COPIED_RESULTS: Job, COPIED_DATA: Data, COPIED_RECIPES: Analysis}
    key, vals = board

    # Special case function used to paste files.
    files_paste(project=project, user=user, board=board)

    def copy(instance):
        if key == COPIED_RECIPES:
            # Paste objects in clipboard as recipes
            return recipe_paste(user=user, project=project, clone=clone, instance=instance)
        else:
            # Paste objects in clipboard as data
            return data_paste(user=user, project=project, instance=instance)

    # Map the objects in the clipboard to a database class.
    klass = obj_map.get(key)
    if not klass:
        return []

    # Select valid object uids.
    objs = [klass.objects.filter(uid=uid).first() for uid in vals]
    # Only keep existing objects.
    objs = filter(None, objs)

    # Copy the objects into a list of new objects
    new = list(map(copy, objs))

    return new


def fill_json_data(project, job=None, source_data={}, fill_with={}):
    """
    Produces a filled in JSON data based on user input.
    """

    # Creates a data.id to data mapping.
    store = dict((data.id, data) for data in project.data_set.all())

    # Make a copy of the original json data used to render the form.
    json_data = copy.deepcopy(source_data)

    # Get default dictionary to fill with from json data 'value'
    default = {field: item.get('value', '') for field, item in json_data.items()}
    fill_with = fill_with or default

    # Alter the json data and fill in the extra information.
    for field, item in json_data.items():

        # If the field is a data field then fill in more information.
        if item.get("source") == "PROJECT" and fill_with.get(field, '').isalnum():
            data_id = int(fill_with.get(field))
            data = store.get(data_id)
            # This mutates the `item` dictionary!
            data.fill_dict(item)
            continue

        # The JSON value will be overwritten with the selected field value.
        if field in fill_with:
            item["value"] = fill_with[field]
            # Clean the textbox value
            if item.get('display') == TEXTBOX:
                item["value"] = util.clean_text(fill_with[field])

            if item.get('display') == UPLOAD:
                # Add uploaded file to job directory.
                upload_value = fill_with.get(field)
                if not upload_value:
                    item['value'] = ''
                    continue
                # Link or write the stream located in the fill_with
                path = add_file(target_dir=job.get_data_dir(), source=upload_value)
                item['value'] = path

    return json_data


def create_job(analysis, user=None, json_text='', json_data={}, name=None, state=Job.QUEUED, uid=None, save=True,
               fill_with={}):
    """
    Note: Parameter 'fill_with' needs to be a flat key:value dictionary.
    """
    state = state or Job.QUEUED
    owner = user or analysis.project.owner
    project = analysis.project

    if json_data:
        json_text = hjson.dumps(json_data)
    else:
        json_text = json_text or analysis.json_text

    # Needs the json_data to set the summary.
    json_data = hjson.loads(json_text)

    # Generate a meaningful job title.
    name = make_job_title(recipe=analysis, data=json_data)
    uid = uid or util.get_uuid(8)

    # Create the job instance.
    job = Job.objects.create(name=name, state=state, json_text=json_text,
                             security=Job.AUTHORIZED, project=project, analysis=analysis, owner=owner,
                             template=analysis.template, uid=uid)
    # Fill the json data.
    json_data = fill_json_data(job=job, source_data=json_data, project=project, fill_with=fill_with)

    # Generate a meaningful job title.
    name = make_job_title(recipe=analysis, data=json_data)
    # Update the json_text and name
    job.json_text = hjson.dumps(json_data)
    job.name = name

    if save:
        # Save the updated json_text and name.
        job.save()
        # Update the projects lastedit user when a job is created
        logger.info(f"Created job id={job.id} name={job.name}")

    return job


def delete_object(obj, request):
    access = is_writable(user=request.user, project=obj.project)

    # Toggle the delete state if the user has write access
    if access:
        obj.deleted = not obj.deleted
        obj.save()

    return obj.deleted


def transform(root, node, path):

    # Image extension types.
    IMAGE_EXT = {"png", "jpg", "gif", "jpeg"}

    # Get the absolute path /root/node/path.
    path = os.path.abspath(os.path.join(node, path))

    # Find the relative path of the current node/path to the root.
    relative = os.path.relpath(path, root)

    # Follow symlinks and get the real path.
    real = os.path.realpath(path)

    # Get the parent directory
    parent = os.path.dirname(path)

    # Time stamp and size info.
    tstamp = os.stat(path).st_mtime
    size = os.stat(path).st_size

    # Get the elements. i.e. foo/bar.txt -> ['foo', 'bar.txt']
    elems = os.path.split(relative)
    is_dir = os.path.isdir(path)

    # Get all directories.
    dirs = elems[:-1]
    dirs = [] if dirs[0] == '' else dirs

    # Get the last node.
    last = elems[-1]
    is_image = last.split(".")[-1] in IMAGE_EXT

    return real, relative, dirs, last, tstamp, size, is_image, parent, is_dir


def listing(root, node=None, show_all=True):
    paths = []
    node = node or root

    try:
        if show_all:
            # Walk the filesystem and collect all files.
            for fpath, fdirs, fnames in os.walk(root, followlinks=True):
                paths.extend([join(fpath, fname) for fname in fnames])
        else:
            # Get the list of file in current directory node being traversed.
            paths = os.listdir(node)

        # Add metadata to each path.
        transformer = lambda path: transform(root=root, node=node, path=path)

        paths = list(map(transformer, paths))

        # Sort files by directory
        paths = sorted(paths, key=lambda x: x[-1], reverse=True)

    except Exception as exc:
        logger.error(exc)

    return paths


def job_color(job):
    try:
        if isinstance(job, Job):
            return JOB_COLORS.get(job.state, "")
    except Exception as exc:
        logger.error(exc)
        return ''

    return


def guess_mimetype(fname):
    "Return mimetype for a known text filename"

    mimetype, encoding = guess_type(fname)

    ext = os.path.splitext(fname)[1].lower()

    # Known text extensions ( .fasta, .fastq, etc.. )
    if ext in KNOWN_TEXT_EXTENSIONS:
        mimetype = 'text/plain'

    return mimetype


def create_path(fname, data):
    """
    Returns a proposed path based on fname to the storage folder of the data.
    Attempts to preserve the extension but also removes all whitespace from the filenames.
    """
    # Select the file name.

    fname = os.path.basename(fname)

    # The data storage directory.
    data_dir = data.get_data_dir()

    # Make the data directory if it does not exist.
    os.makedirs(data_dir, exist_ok=True)

    # Build the file name under the new location.
    path = os.path.abspath(os.path.join(data_dir, fname))

    return path


def new_uid(obj, objtype, default=None):
    """
    Ensure an objects uid is unique.
    """
    uid = default or obj.uid
    while objtype.objects.filter(uid=uid).exclude(uid=obj.uid).exists():
        uid = generate_uuid(prefix="data", suffix=f"{get_uuid(3)}")
    return uid


def data_link(path, data):

    dest = create_path(fname=path, data=data)

    if os.path.islink(dest):
        # Update the link to this file
        os.unlink(dest)
        os.symlink(path, dest)

    if not os.path.exists(dest):
        os.symlink(path, dest)

    return dest


def create_data_link(path, data):

    # The path is a file.
    if os.path.isfile(path):
        data_link(path=path, data=data)
        logger.info(f"Linked file: {path}")

    # The path is a directory.
    if os.path.isdir(path):
        for p in os.scandir(path):
            data_link(path=p.path, data=data)
        logger.info(f"Linked dir: {path}")


def is_readable(user, project):
    # Shareable projects can get to see the

    if project.is_public:
        return True

    if user.is_anonymous:
        return False

    query = Q(access=Access.READ_ACCESS) | Q(access=Access.WRITE_ACCESS) | Q(access=Access.SHARE_ACCESS)

    access = Access.objects.filter(query, project=project, user=user)

    return access.exists()


def is_writable(user, project, owner=None):
    """
    Returns True if a user has write access to an instance
    """

    # Anonymous user may not have write access.
    if user.is_anonymous:
        return False

    # Users that may access a project.
    cond1 = user.is_staff or user.is_superuser

    # User has been given write access to the project
    cond2 = models.Access.objects.filter(user=user, project=project,
                                         access=models.Access.WRITE_ACCESS).first()

    # User owns this project.
    owner = owner or project.owner
    cond3 = user == owner

    # One of the conditions has to be true.
    access = cond1 or cond2 or cond3

    return access


def writeable_recipe(user, source, project=None):
    """
    Check if a user can write to a 'source' recipe.
    """
    if user.is_anonymous:
        return False

    if source.is_cloned:
        # Check write access using root recipe information for clones.
        target_owner = source.root.owner
        project = source.root.project

    else:
        target_owner = source.owner
        project = project or source.project

    access = is_writable(user=user, project=project, owner=target_owner)
    return access


def fill_data_by_name(project, json_data):
    """
    Fills json information by name.
    Used when filling in demonstration data and not user selection.
    """

    json_data = copy.deepcopy(json_data)
    # A mapping of data by name

    for field, item in json_data.items():
        # If the field is a data field then fill in more information.
        val = item.get("value", '')
        if item.get("source") == "PROJECT":
            name = item.get("value")

            item['toc'] = "FILE-LIST"
            item['file_list'] = "FILE-LIST"
            item['value'] = name or 'FILENAME'
            item['data_dir'] = "DATA_DIR"
            item['id'] = "DATA_ID"
            item['name'] = "DATA_NAME"
            item['uid'] = "DATA_UID"
            item['project_dir'] = project.get_data_dir()
            item['data_url'] = "/"

            continue

        # Give a placeholder so templates do not have **MISSING**.
        if val is None or len(str(val)) == 0:
            item['value'] = f'{str(field).upper()}'

    return json_data


def create_data(project, user=None, stream=None, path='', name='', text='', type='', uid=None):

    # We need absolute paths with no trailing slashes.
    path = os.path.abspath(path).rstrip("/") if path else ""

    # Create the data.
    dtype = type or "DATA"

    # The owner of the data will be the first admin user if not set otherwise.
    owner = user or models.User.objects.filter(is_staff=True).first()

    # Create the data object.
    data = Data.objects.create(name=name, owner=owner, state=Data.PENDING,
                               project=project, type=dtype, text=text, uid=uid)

    # Set the uid.
    uid = new_uid(obj=data, objtype=Data, default=uid)
    data.uid = uid

    # Write this stream into a path then link that into the data.
    if stream:
        name = name or stream.name
        fname = '_'.join(name.split())
        # Create path for the stream
        path = create_path(data=data, fname=fname)

        # Write stream into newly created path.
        util.write_stream(stream=stream, dest=path)

        # Mark incoming file as uploaded
        data.method = Data.UPLOAD

    # Link path to this data object.
    create_data_link(path=path, data=data)

    # Invalid paths and empty streams still create the data
    # but set the data state will be set to error.
    missing = not (path or stream or os.path.isdir(path) or os.path.isfile(path))

    # An invalid entry here.
    if path and missing:
        state = Data.ERROR
        logger.error(f"Invalid data path: {path}")
    else:
        state = Data.READY

    # Set updated attributes
    data.state = state
    data.name = name or os.path.basename(path) or 'Data'

    # Trigger another save to remake the toc file.
    data.save()

    # Set log for data creation.
    logger.info(f"Added data type={data.type} name={data.name} pk={data.pk}")

    return data


def get_or_create(fname, project, user=None, uid=None, name="", text="", dtype=""):
    """
    Get or create a data object associated with a file.
    """

    # Get the data if it exists.
    data = Data.objects.filter(uid=uid).first()

    if data and data.deleted:
        logger.warning("Can not update deleted data.")
        return data

    if data:
        create_data_link(path=fname, data=data)
        logger.info("Updated data file, name, and text.")
    else:
        # Create new data.
        data = create_data(project=project, path=fname, user=user, uid=uid)

    # Update the name, text, and type.
    data.name = name or data.name
    data.text = text or data.text
    data.type = dtype.upper() or data.type or "DATA"

    # Trigger save to update the toc file, last edit date, etc.
    data.save()
    return data
