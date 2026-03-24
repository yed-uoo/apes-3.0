from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("role-selection/", views.role_selection, name="role_selection"),
    path("switch-role/", views.switch_role, name="switch_role"),
    path("profile/", views.profile, name="profile"),
    path("mini-project/", views.mini_project, name="mini_project"),
    path("project-report/", views.project_report, name="project_report"),
    path("project-report/submit/<int:group_id>/", views.submit_project_report, name="submit_project_report"),
    path("project-report/mark/<int:report_id>/", views.submit_report_mark, name="submit_report_mark"),
    path("project-report/reject/<int:report_id>/", views.submit_report_rejection, name="submit_report_rejection"),
    path("project-report/download/<int:report_id>/", views.download_project_report, name="download_project_report"),
    path("sdg-submission/", views.sdg_submission, name="sdg_submission"),
    path("group-requests/", views.group_requests, name="group_requests"),
    path("guide-request/", views.guide_request, name="guide_request"),
    path("guide-dashboard/", views.guide_dashboard, name="guide_dashboard"),
    path("guide-requests/", views.guide_requests, name="guide_requests"),
    # Coordinator URLs
    path("request-coordinator-approval/", views.request_coordinator_approval, name="request_coordinator_approval"),
    path("coordinator-dashboard/", views.coordinator_dashboard, name="coordinator_dashboard"),
    # Abstract submission URLs
    path("submit-abstract/", views.submit_abstract, name="submit_abstract"),
    path("abstract-status/", views.abstract_status, name="abstract_status"),
    path("faculty-abstracts/", views.faculty_abstracts, name="faculty_abstracts"),
    path("review-abstract/<int:abstract_id>/", views.review_abstract, name="review_abstract"),
    path("download-abstract/<int:abstract_id>/", views.download_abstract, name="download_abstract"),
    # HOD URLs
    path("hod-dashboard/", views.hod_dashboard, name="hod_dashboard"),
    # Evaluation URLs
    path("evaluation/guide/<int:group_id>/<str:stage>/", views.submit_guide_evaluation, name="submit_guide_evaluation"),
    path("evaluation/coordinator/<int:group_id>/<str:stage>/", views.submit_coordinator_evaluation, name="submit_coordinator_evaluation"),
    path("evaluation/upload/<str:stage>/", views.upload_evaluation_file, name="upload_evaluation_file"),
    path("evaluation/download/<int:file_id>/", views.download_evaluation_file, name="download_evaluation_file"),
    # Student Evaluation URLs (First/Second)
    path("evaluation/guide/student/<int:group_id>/<str:stage>/", views.submit_guide_student_evaluation, name="submit_guide_student_evaluation"),
    path("evaluation/guide/final/<int:group_id>/", views.submit_final_guide_evaluation, name="submit_final_guide_evaluation"),
    path("evaluation/guide/ese/<int:group_id>/", views.submit_guide_ese, name="submit_guide_ese"),
    path("evaluation/coordinator/ese/<int:group_id>/", views.submit_coordinator_ese, name="submit_coordinator_ese"),
    path("evaluation/coordinator/student/<int:group_id>/<str:stage>/", views.submit_coordinator_student_evaluation, name="submit_coordinator_student_evaluation"),
    path("evaluation/attendance/<int:group_id>/", views.submit_attendance_marks, name="submit_attendance_marks"),
]
