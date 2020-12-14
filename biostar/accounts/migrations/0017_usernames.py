# Generated by Django 3.1 on 2020-12-10 17:03

from django.db import migrations, models
from django.template.defaultfilters import slugify

def change_usernames(apps, schema_editor):

    User = apps.get_model('auth', 'User')
    users = User.objects.all()
    for user in users:
        # Remove spaces from usernames
        user.username = slugify(user.username)
        user.save()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_profile_watched'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='website',
            field=models.URLField(blank=True, default='', max_length=256),
        ),

        migrations.RunPython(change_usernames),
    ]
