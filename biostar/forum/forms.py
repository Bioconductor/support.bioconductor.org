from pagedown.widgets import PagedownWidget
import os
import re
import langdetect
from django import forms
from django.utils.safestring import mark_safe
from django.core.exceptions import ValidationError
from django.shortcuts import reverse
from django.conf import settings
from snowpenguin.django.recaptcha2.fields import ReCaptchaField
from snowpenguin.django.recaptcha2.widgets import ReCaptchaWidget
from biostar.accounts.models import User
from .models import Post
from biostar.forum import models, auth

from .const import *

# Share logger with models
logger = models.logger

MIN_CHARS = 5
MAX_CONTENT = 15000
MIN_CONTENT = 5
MAX_TITLE = 400
MAX_TAGS = 5


def valid_language(text):
    supported_languages = settings.LANGUAGE_DETECTION
    if supported_languages:
        try:
            lang = langdetect.detect(text)
        except Exception as exc:
            logger.error(f"Lang detect error: {exc}")
            return

        if lang not in supported_languages:
            raise ValidationError(f'Language "{lang}" is not one of the supported languages {supported_languages}!')


def valid_title(text):
    "Validates form input for titles."
    text = text.strip()
    if not text:
        raise ValidationError('Please enter a title')

    text = text.replace(" ", '')
    if len(text) < MIN_CHARS:
        raise ValidationError(f'Too short, please add more than {MIN_CHARS} characters.')
    if len(text) > MAX_TITLE:
        raise ValidationError(f'Too Long, please add less than {MAX_TITLE} characters.')

    try:
        text.encode('utf-8')
    except Exception as exc:
        raise ValidationError(f'Title contains invalid characters: {exc}')


def valid_tag(text):
    "Validates form input for tags"

    words = text.split(",")
    if len(words) > MAX_TAGS:
        raise ValidationError('You have too many tags (5 allowed)')


def informative_choices(choices):
    """
    Map choices for post types to a more informative description.
    """
    mapper = {
        Post.QUESTION: "Ask a question", Post.TUTORIAL: "Share a Tutorial",
        Post.JOB: "Post a Job Opening", Post.FORUM: "Start a Discussion",
        Post.TOOL: "Share a Tool", Post.NEWS: "Announce News"
    }
    new_choices = []
    for c in choices:
        new_choices.append((c[0], mapper.get(c[0], c[1])))

    return new_choices


def common_elem(set_a, set_b):
    # Return True if two sets share at least one common element.
    return len(set_a.intersection(set_b)) > 0


def required_tags(lst):
    """
    Ensure at least one tag is present in the
    """
    if not os.path.isfile(settings.REQUIRED_TAGS):
        return

    # Get the tags file.
    tags = open(settings.REQUIRED_TAGS, 'r').readlines()
    tags = set([x.strip() for x in tags])

    # Create two sets from the source ( input parameter)
    # and target ( file with required tags ) .
    source_set = set(lst)
    target_set = set(tags)

    # If one common element is not found, display the required tasks
    if not common_elem(source_set, target_set):
        url = settings.REQUIRED_TAGS_URL
        msg = mark_safe(f"At least one package from <a href='{url}' target='_blank'>this list</a> is required.")
        raise forms.ValidationError(msg)

    return


class PostLongForm(forms.Form):
    choices = [opt for opt in Post.TYPE_CHOICES if opt[0] in Post.TOP_LEVEL]

    if settings.ALLOWED_POST_TYPES:
        choices = [opt for opt in choices if opt[1] in settings.ALLOWED_POST_TYPES]

    choices = informative_choices(choices=choices)

    post_type = forms.IntegerField(label="Post Type",
                                   widget=forms.Select(choices=choices, attrs={'class': "ui dropdown"}),
                                   help_text="Select a post type.")
    title = forms.CharField(label="Post Title", max_length=200, min_length=2,
                            validators=[valid_title],
                            help_text="Enter a descriptive title to promote better answers.")
    tag_val = forms.CharField(label="Post Tags", max_length=50, required=True, validators=[valid_tag],
                              help_text="""
                              Create a new tag by typing a word then adding a comma or press ENTER or SPACE.
                              """,
                              widget=forms.HiddenInput())

    content = forms.CharField(widget=forms.Textarea,
                              validators=[valid_language],
                              min_length=MIN_CONTENT, max_length=MAX_CONTENT, label="Post Content", strip=False)

    def __init__(self, post=None, user=None, *args, **kwargs):
        self.post = post
        self.user = user
        super(PostLongForm, self).__init__(*args, **kwargs)

    def edit(self):
        """
        Edit an existing post.
        """
        if self.user != self.post.author and not self.user.profile.is_moderator:
            raise forms.ValidationError("Only the author or a moderator can edit a post.")
        data = self.cleaned_data
        self.post.title = data.get('title')
        self.post.content = data.get("content")
        self.post.type = data.get('post_type')
        self.post.tag_val = data.get('tag_val')
        self.post.lastedit_user = self.user
        self.post.save()
        return self.post

    def clean_tag_val(self):
        """
        Take out duplicates
        """
        if settings.STRICT_TAGS:
            pattern = r'^[A-Za-z0-9-._]+$'
            tag_val = self.cleaned_data["tag_val"]
            tag_val = tag_val.replace(',', ' ').split()

            for tag in tag_val:
                match = re.match(pattern, tag)
                if not match:
                    raise forms.ValidationError(f'Invalid characters in tag: {tag}')
        else:
            tag_val = self.cleaned_data["tag_val"].split(',')

        tags = set(tag_val)
        tags = ",".join(tags)

        return tags

    def clean_content(self):
        content = self.cleaned_data["content"]
        length = len(content.replace(" ", ""))

        if length < MIN_CHARS:
            raise forms.ValidationError(f"Too short, place add more than {MIN_CHARS}")

        return content


class PostShortForm(forms.Form):
    MIN_LEN, MAX_LEN = 10, 10000
    parent_uid = forms.CharField(widget=forms.HiddenInput(), min_length=2, max_length=32, required=False)
    content = forms.CharField(widget=forms.Textarea,
                              min_length=MIN_LEN, max_length=MAX_LEN, strip=False)

    def __init__(self, user=None, post=None,  *args, **kwargs):
        self.user = user
        self.post = post
        super().__init__(*args, **kwargs)
        self.fields['content'].strip = False

    def clean_content(self):
        content = self.cleaned_data["content"]
        return content

    def clean(self):
        cleaned_data = super(PostShortForm, self).clean()
        if self.user.is_anonymous:
            raise forms.ValidationError("You need to be logged in.")
        return cleaned_data
