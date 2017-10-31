
import uuid
import logging

from django.utils import http
from django.contrib import messages
from ratelimit.decorators import ratelimit
from django.views.decorators import csrf, cache
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.urls import reverse


from .forms import SignUpForm, LoginForm, LogoutForm
from biostar.engine.const import *
from biostar.engine.views import breadcrumb_builder
from django.contrib import auth

logger = logging.getLogger('engine')
NEXTURL = ""

def get_uuid(limit=32):
    return str(uuid.uuid4())[:limit]


def info(request):

    return redirect("/")


def user_profile(request, id):

    user = User.objects.filter(id=id).first()
    steps = breadcrumb_builder([HOME_ICON, USER_ICON], user=user)

    context = dict(user=user, steps=steps)

    return render(request, 'accounts/profile.html', context)



@ratelimit(key='ip', rate='10/m', block=True, method=ratelimit.UNSAFE)
def user_signup(request):

    steps = breadcrumb_builder([HOME_ICON, SIGNUP_ICON])

    if request.method == 'POST':

        form = SignUpForm(request.POST)

        if form.is_valid():
            email = form.cleaned_data.get('email')
            password = form.cleaned_data.get('password1')
            name = email.split("@")[0]

            user = User.objects.create(username=get_uuid(), email=email,
                                       first_name=name)
            user.set_password(password)
            user.save()

            auth.login(request, user)
            logger.info(f"Signed up and logged in user.id={user.id}, user.email={user.email}")
            messages.info(request, "Signup successful!")
            return redirect(reverse('login'))
    else:

        form = SignUpForm()
    context = dict(form=form, steps=steps)
    return render(request, 'accounts/signup.html', context=context)


def user_logout(request):
    steps = breadcrumb_builder([HOME_ICON, LOGOUT_ICON])

    if request.method == "POST":

        form = LogoutForm(request.POST)

        if form.is_valid():
            auth.logout(request)
            messages.info(request, "You have been logged out")
            return redirect("/")

    form = LogoutForm()

    context = dict(steps=steps, form=form)

    return render(request, "accounts/logout.html", context=context)


@ratelimit(key='ip', rate='10/m', block=True, method=ratelimit.UNSAFE)
@csrf.csrf_protect
@cache.never_cache
def user_login(request):

    #TODO: Current hacky way of redirecting
    global NEXTURL
    redirect_to = request.GET.get('next', '/')
    safe = http.is_safe_url(redirect_to, request.get_host())

    if (not len(NEXTURL) and safe) or ( len(NEXTURL) and safe and redirect_to != NEXTURL) :
        NEXTURL =  redirect_to

    steps = breadcrumb_builder([HOME_ICON, LOGIN_ICON])

    if request.method == "POST":
        auth.logout(request)
        form = LoginForm(data=request.POST)

        if form.is_valid():


            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            # Due to an early bug emails may not be unique. Last subscription wins.
            user = User.objects.filter(email__iexact=email).order_by('-id').first()

            if not user:
                form.add_error(None, "This email does not exist.")
                context = dict(form=form, steps=steps)
                return render(request, "accounts/login.html", context=context)

            user = auth.authenticate(username=user.username, password=password)

            if not user:
                form.add_error(None, "Invalid password.")
            elif user and not user.is_active:
                form.add_error(None, "This user may not log in.")
            elif user and user.is_active:
                auth.login(request, user)
                logger.info(f"logged in user.id={user.id}, user.email={user.email}")
                messages.info(request, "Login successful!")
                print(NEXTURL)
                return redirect(NEXTURL)
            else:
                # This should not happen normally.
                form.add_error(None, "Invalid form processing.")
    else:
        initial = dict(next=request.GET.get('next', '/'))
        form = LoginForm(initial=initial)



    context = dict(form=form, steps=steps, next=redirect_to)
    return render(request, "accounts/login.html", context=context)

