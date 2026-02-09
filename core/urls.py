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
]
