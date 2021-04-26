from functools import wraps, partial
import logging
import json
from ratelimit.decorators import ratelimit
from urllib import request as builtin_request
# import requests
from urllib.parse import urlencode
from datetime import datetime, timedelta
from urllib.parse import quote

from django.core.cache import cache
from django.conf import settings
from django.db.models import Q, Count
from django.shortcuts import reverse, redirect
from django.template import loader
from django.http import JsonResponse

from whoosh.searching import Results

from biostar.accounts.models import Profile, User
from . import auth, util, forms, tasks, search, views, const, moderate
from .models import Post, Vote, Subscription, delete_post_cache

def ajax_msg(msg, status, **kwargs):
    payload = dict(status=status, msg=msg)
    payload.update(kwargs)
    return JsonResponse(payload)


logger = logging.getLogger("engine")
ajax_success = partial(ajax_msg, status='success')
ajax_error = partial(ajax_msg, status='error')

MIN_TITLE_CHARS = 10
MAX_TITLE_CHARS = 180

VOTE_RATE = settings.VOTE_RATE
EDIT_RATE = settings.EDIT_RATE
SUBS_RATE = settings.SUBS_RATE
DIGEST_RATE = settings.DIGEST_RATE

RATELIMIT_KEY = settings.RATELIMIT_KEY


def ajax_limited(key, rate):
    """
    Make a blocking rate limiter that does not raise an exception
    """
    def outer(func):

        @ratelimit(key=key, rate=rate)
        def inner(request, **kwargs):

            was_limited = getattr(request, 'limited', False)
            if was_limited:
                return ajax_error(msg="Too many requests from same IP address. Temporary ban.")

            return func(request, **kwargs)

        return inner

    return outer


class ajax_error_wrapper:
    """
    Used as decorator to trap/display  errors in the ajax calls
    """

    def __init__(self, method, login_required=True):
        self.method = method
        self.login_required = login_required

    def __call__(self, func, *args, **kwargs):

        @wraps(func)
        def _ajax_view(request, *args, **kwargs):

            if request.method != self.method:
                return ajax_error(f'{self.method} method must be used.')

            if not request.user.is_authenticated and self.login_required:
                return ajax_error('You must be logged in.')

            if request.user.is_authenticated and request.user.profile.is_spammer:
                return ajax_error('You must be logged in.')

            try:
                return func(request, *args, **kwargs)
            except Exception as exc:
                return ajax_error(f'Error: {exc}')

        return _ajax_view


def ajax_test(request):
    """
    Creates a commment on a top level post.
    """
    msg = "OK"
    print(f"HeRe= {request.POST} ")
    return ajax_error(msg=msg)


@ajax_error_wrapper(method="GET")
def user_image(request, username):
    user = User.objects.filter(username=username).first()

    gravatar_url = auth.gravatar(user=user)
    return redirect(gravatar_url)


@ajax_limited(key=RATELIMIT_KEY, rate=VOTE_RATE)
@ajax_error_wrapper(method="POST")
def ajax_vote(request):

    user = request.user
    type_map = dict(upvote=Vote.UP, bookmark=Vote.BOOKMARK, accept=Vote.ACCEPT)

    vote_type = request.POST.get('vote_type')

    vote_type = type_map.get(vote_type)

    post_uid = request.POST.get('post_uid')

    # Check the post that is voted on.
    post = Post.objects.filter(uid=post_uid).first()

    if post.author == user and vote_type == Vote.UP:
        return ajax_error("You can not upvote your own post.")

    if post.author == user and vote_type == Vote.ACCEPT:
        return ajax_error("You can not accept your own post.")

    not_moderator = user.is_authenticated and not user.profile.is_moderator
    if post.root.author != user and not_moderator and vote_type == Vote.ACCEPT:
        return ajax_error("Only moderators or the person asking the question may accept answers.")

    msg, vote, change = auth.apply_vote(post=post, user=user, vote_type=vote_type)

    # Expire post cache upon vote.
    delete_post_cache(post)

    return ajax_success(msg=msg, change=change)


@ajax_limited(key=RATELIMIT_KEY, rate=EDIT_RATE)
@ajax_error_wrapper(method="POST", login_required=True)
def drag_and_drop(request):

    parent_uid = request.POST.get("parent", '')
    uid = request.POST.get("uid", '')
    user = request.user
    parent = Post.objects.filter(uid=parent_uid).first()
    post = Post.objects.filter(uid=uid).first()

    # Parent is root when dropping to a new answer.
    parent = post.root if (parent_uid == "NEW" and post) else parent

    valid = auth.validate_move(user=user, source=post, target=parent)
    if not valid:
        return ajax_error(msg="Invalid Drop")

    # Dropping comment as a new answer
    if parent_uid == "NEW":
        url = auth.move_to_answer(request=request, post=post)
    else:
        url = auth.move_post(request=request, post=post, parent=parent)

    delete_post_cache(post)
    return ajax_success(msg="success", redir=url)


@ajax_limited(key=RATELIMIT_KEY, rate=SUBS_RATE)
@ajax_error_wrapper(method="POST")
def ajax_subs(request):

    type_map = dict(messages=Subscription.LOCAL_MESSAGE, email=Subscription.EMAIL_MESSAGE,
                    unfollow=Subscription.NO_MESSAGES)

    # Get the root and sub type.
    root_uid = request.POST.get('root_uid')
    sub_type = request.POST.get("sub_type")
    sub_type = type_map.get(sub_type, Subscription.NO_MESSAGES)
    user = request.user

    # Get the post that is subscribed to.
    root = Post.objects.filter(uid=root_uid).first()

    auth.create_subscription(post=root, user=user, sub_type=sub_type)

    return ajax_success(msg="Changed subscription.")


@ajax_limited(key=RATELIMIT_KEY, rate=DIGEST_RATE)
@ajax_error_wrapper(method="POST")
def ajax_digest(request):

    user = request.user

    type_map = dict(daily=Profile.DAILY_DIGEST, weekly=Profile.WEEKLY_DIGEST,
                    monthly=Profile.MONTHLY_DIGEST)
    if user.is_anonymous:
        return ajax_error(msg="You need to be logged in to edit your profile.")

    # Get the post and digest preference.
    pref = request.POST.get('pref')
    pref = type_map.get(pref, Profile.NO_DIGEST)
    Profile.objects.filter(user=user).update(digest_prefs=pref)

    return ajax_success(msg="Changed digest options.")


def get_fields(request, post=None):
    """
    Used to retrieve all fields in a request used for editing and creating posts.
    """
    user = request.user
    content = request.POST.get("content", "") or post.content
    title = request.POST.get("title", "") or post.title
    post_type = request.POST.get("type", Post.QUESTION)

    post_type = int(post_type) if str(post_type).isdigit() else Post.QUESTION
    recaptcha_token = request.POST.get("recaptcha_response")

    # Fields found in top level posts
    tag_list = {x.strip() for x in request.POST.getlist("tag_val", [])}
    tag_val = ','.join(tag_list) or post.tag_val

    fields = dict(content=content, title=title, post_type=post_type, tag_list=tag_list, tag_val=tag_val,
                  user=user, recaptcha_token=recaptcha_token, )

    return fields


def set_post(post, user, fields):

    # Set the fields for this post.
    if post.is_toplevel:
        post.title = fields.get('title', post.title)
        post.type = fields.get('post_type', post.type)
        post.tag_val = fields.get('tag_val', post.tag_val)

    post.lastedit_user = user
    post.lastedit_date = util.now()
    post.content = fields.get('content', post.content)
    post.save()

    return post


@ajax_limited(key=RATELIMIT_KEY, rate=EDIT_RATE)
@ajax_error_wrapper(method="POST", login_required=True)
def ajax_edit(request, uid):
    """
    Edit post content using ajax.
    """

    post = Post.objects.filter(uid=uid).first()
    user = request.user
    can_edit = (user.profile.is_moderator or user == post.author)

    if not post:
        return ajax_error(msg="Post does not exist")

    if not can_edit:
        return ajax_error(msg="Only moderators or the author can edit posts.")

    # Get the fields found in the request
    fields = get_fields(request=request, post=post)

    # Pick the form
    if post.is_toplevel:
        form = forms.PostLongForm(post=post, user=user, data=fields)
    else:
        form = forms.PostShortForm(post=post, user=user, data=fields)

    if form.is_valid():
        post = set_post(post, user, form.cleaned_data)
        return ajax_success(msg='Edited post', redirect=post.get_absolute_url())
    else:
        msg = [field.errors for field in form if field.errors]
        return ajax_error(msg=msg)


@ajax_error_wrapper(method="POST", login_required=True)
def ajax_delete(request):
    uid = request.POST.get('uid')
    user = request.user
    post = Post.objects.filter(uid=uid).first()

    if not post:
        return ajax_error(msg="Post does not exist")

    if not (user.profile.is_moderator or post.author == user):
        return ajax_error(msg="Only moderators and post authors can delete.")

    url = moderate.delete_post(post=post, request=request)

    return ajax_success(msg="post deleted", url=url)


@ajax_limited(key=RATELIMIT_KEY, rate=EDIT_RATE)
@ajax_error_wrapper(method="POST")
def ajax_comment_create(request):

    # Fields common to all posts
    user = request.user
    content = request.POST.get("content", "")

    parent_uid = request.POST.get('parent', '')
    parent = Post.objects.filter(uid=parent_uid).first()
    if not parent:
        return ajax_error(msg='Parent post does not exist.')

    fields = dict(content=content, parent_uid=parent_uid)

    form = forms.PostShortForm(post=parent, user=user, data=fields)

    if form.is_valid():
        # Create the comment.
        post = Post.objects.create(type=Post.COMMENT, content=content, author=user, parent=parent)
        return ajax_success(msg='Created post', redirect=post.get_absolute_url())
    else:
        msg = [field.errors for field in form if field.errors]
        return ajax_error(msg=msg)


@ajax_limited(key=RATELIMIT_KEY, rate=EDIT_RATE)
@ajax_error_wrapper(method="GET")
def handle_search(request):
    """
    Used to search by the user handle.
    """

    query = request.GET.get('query')
    if query:
        users = User.objects.filter(profile__handle__icontains=query
                                    ).values_list('profile__handle', flat=True
                                                  ).order_by('profile__score')
    else:
        users = User.objects.order_by('profile__score').values_list('profile__handle', flat=True)

    users = list(users[:20])
    # Return list of users matching username
    return ajax_success(users=users, msg="Username searched")


@ajax_limited(key=RATELIMIT_KEY, rate=EDIT_RATE)
@ajax_error_wrapper(method="GET")
def inplace_form(request):
    """
    Used to render inplace forms for editing posts.
    """
    MIN_LINES = 10
    user = request.user
    if user.is_anonymous:
        return ajax_error(msg="You need to be logged in to edit or create posts.")

    # Get the current post uid we are editing
    uid = request.GET.get('uid', '')
    post = Post.objects.filter(uid=uid).first()
    if not post:
        return ajax_error(msg="Post does not exist.")

    add_comment = request.GET.get('add_comment', False)

    html = "" if add_comment else post.html

    # Load the content and form template
    template = "forms/form_inplace.html"
    tmpl = loader.get_template(template_name=template)

    nlines = post.num_lines(offset=3)
    rows = nlines if nlines >= MIN_LINES else MIN_LINES
    form = forms.PostLongForm(user=request.user)

    content = '' if add_comment else post.content
    context = dict(user=user, post=post, new=add_comment, html=html,
                   captcha_key=settings.RECAPTCHA_PUBLIC_KEY, rows=rows, form=form,
                   content=content)

    form = tmpl.render(context)

    return ajax_success(msg="success", inplace_form=form)


def similar_posts(request, uid):
    """
    Return a feed populated with posts similar to the one in the request.
    """

    post = Post.objects.filter(uid=uid).first()
    if not post:
        ajax_error(msg='Post does not exist.')

    template_name = 'widgets/similar_posts.html'
    cache_key = f"{const.SIMILAR_CACHE_KEY}-{post.uid}"
    results = cache.get(cache_key)

    if results is None:
        logger.debug("Setting similar posts cache.")
        # Do a more like this search on post
        similar = search.more_like_this(uid=post.uid)
        # Render template with posts
        tmpl = loader.get_template(template_name)
        context = dict(results=similar)
        results = tmpl.render(context)

        # Expire in one week if results exists, one hour if not.
        expire = 3600 * 24 * 7 if len(similar) > 1 else 3600
        cache.set(cache_key, results, expire)

    return ajax_success(html=results, msg="success")
