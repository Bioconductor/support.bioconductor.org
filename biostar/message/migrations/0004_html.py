# Generated by Django 2.2 on 2019-05-08 12:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('message', '0003_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='html',
            field=models.TextField(default='', max_length=100000),
        ),
        migrations.AlterField(
            model_name='message',
            name='type',
            field=models.IntegerField(choices=[(0, 'Local messages.'), (1, 'Email messages.'), (2, 'Mailing list.')], db_index=True, default=0),
        ),
    ]
