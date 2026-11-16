from django.urls import path

from . import views

urlpatterns = [
    path("", views.inbox, name="feedback_inbox"),
    path("list/", views.feedback_list, name="feedback_list"),
    path("bulk_action/", views.bulk_action, name="feedback_bulk_action"),
    path("submit/", views.submit, name="feedback_submit"),
]
