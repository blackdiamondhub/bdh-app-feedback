from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Feedback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(blank=True, max_length=100, null=True)),
                ("email", models.EmailField(blank=True, max_length=254, null=True)),
                ("message", models.TextField()),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("is_read", models.BooleanField(default=False)),
                ("page_url", models.URLField(blank=True)),
                ("stay", models.CharField(blank=True, default="", max_length=120)),
                ("page_title", models.CharField(blank=True, default="", max_length=120)),
                ("page_icon", models.CharField(blank=True, default="", max_length=300)),
            ],
        ),
    ]
