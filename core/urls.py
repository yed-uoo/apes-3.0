from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("mini-project/", views.mini_project, name="mini_project"),
    path("group-requests/", views.group_requests, name="group_requests"),
    path("guide-request/", views.guide_request, name="guide_request"),
    path("guide-dashboard/", views.guide_dashboard, name="guide_dashboard"),
    path("guide-requests/", views.guide_requests, name="guide_requests"),
    # Abstract submission URLs
    path("submit-abstract/", views.submit_abstract, name="submit_abstract"),
    path("abstract-status/", views.abstract_status, name="abstract_status"),
    path("faculty-abstracts/", views.faculty_abstracts, name="faculty_abstracts"),
    path("review-abstract/<int:abstract_id>/", views.review_abstract, name="review_abstract"),
    path("download-abstract/<int:abstract_id>/", views.download_abstract, name="download_abstract"),
]
