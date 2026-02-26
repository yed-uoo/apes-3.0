from django.contrib import admin

from .models import Abstract, CoordinatorApproval, Group, GroupMember, GroupRequest, GuideRequest, StudentProfile, FacultyProfile, SustainableDevelopmentGoal


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
	list_display = ("user", "class_name", "roll_number", "register_number", "department")
	search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", "roll_number", "register_number")
	list_filter = ("department", "class_name")
	ordering = ("user__username",)


@admin.register(FacultyProfile)
class FacultyProfileAdmin(admin.ModelAdmin):
	list_display = ("user", "department", "is_guide", "is_coordinator")
	search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
	list_filter = ("is_guide", "is_coordinator", "department")
	ordering = ("user__username",)
	fieldsets = (
		("User Information", {
			"fields": ("user",)
		}),
		("Faculty Details", {
			"fields": ("department",)
		}),
		("Roles", {
			"fields": ("is_guide", "is_coordinator"),
			"description": "Select the roles for this faculty member."
		}),
	)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
	list_display = ("id", "leader", "created_at")
	search_fields = ("leader__username", "leader__email")
	ordering = ("-created_at",)


@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):
	list_display = ("group", "user")
	search_fields = ("group__leader__username", "user__username", "user__email")
	ordering = ("group", "user")


@admin.register(GroupRequest)
class GroupRequestAdmin(admin.ModelAdmin):
	list_display = ("sender", "recipient", "status", "created_at")
	search_fields = ("sender__username", "sender__email", "recipient__username", "recipient__email")
	list_filter = ("status",)
	ordering = ("-created_at",)


@admin.register(GuideRequest)
class GuideRequestAdmin(admin.ModelAdmin):
	list_display = ("group", "guide", "status")
	search_fields = ("group__leader__username", "guide__username", "guide__email")
	list_filter = ("status",)
	ordering = ("-id",)


@admin.register(CoordinatorApproval)
class CoordinatorApprovalAdmin(admin.ModelAdmin):
	list_display = ("group", "coordinator", "status", "created_at", "updated_at")
	search_fields = ("group__leader__username", "coordinator__username", "coordinator__email")
	list_filter = ("status",)
	ordering = ("-created_at",)
	readonly_fields = ("created_at", "updated_at")


@admin.register(Abstract)
class AbstractAdmin(admin.ModelAdmin):
	list_display = ("title", "group", "status", "submitted_at", "reviewed_by")
	search_fields = ("title", "group__leader__username", "abstract_text")
	list_filter = ("status", "submitted_at")
	ordering = ("-submitted_at",)
	readonly_fields = ("submitted_at", "reviewed_at")


@admin.register(SustainableDevelopmentGoal)
class SustainableDevelopmentGoalAdmin(admin.ModelAdmin):
	list_display = ("group", "submitted_by", "created_at")
	search_fields = ("group__leader__username", "submitted_by__username", "sdg1", "sdg2", "sdg3", "sdg4", "sdg5")
	ordering = ("-created_at",)
	readonly_fields = ("created_at",)
