# Generated by Django 2.0.3 on 2018-03-28 22:40

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("groups", "0005_auto_20180212_2325"),
    ]

    operations = [migrations.RenameModel(old_name="Item", new_name="Task")]
