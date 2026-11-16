from django.db import models


class Feedback(models.Model):
    """One message from the top bar's feedback pill.

    The first seven fields match the hub's old built-in ``feedback`` app, so
    its rows import as they are (see the README).
    """

    name = models.CharField(max_length=100, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    message = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    page_url = models.URLField(max_length=200, blank=True)
    stay = models.CharField(max_length=120, blank=True, default="")
    # The hub page's tile title and icon when the message was sent. Blank on
    # imported rows; the inbox falls back to the URL's path.
    page_title = models.CharField(max_length=120, blank=True, default="")
    page_icon = models.CharField(max_length=300, blank=True, default="")

    def __str__(self):
        return f"Feedback from {self.name or 'Anonymous'}"
