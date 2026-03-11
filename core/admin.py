from django.contrib import admin

from .models import Abstract, CoordinatorApproval, Group, GroupMember, GroupRequest, GuideRequest, Notification, StudentProfile, FacultyProfile, SustainableDevelopmentGoal, GroupEvaluation, EvaluationFile, StudentEvaluation


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
	list_display = ("user", "class_name", "roll_number", "register_number", "department", "cgp")
	search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", "roll_number", "register_number")
	list_filter = ("department", "class_name")
	ordering = ("user__username",)
	fieldsets = (
		("User Information", {
			"fields": ("user",)
		}),
		("Academic Details", {
			"fields": ("class_name", "roll_number", "register_number", "department", "cgp")
		}),
	)


@admin.register(FacultyProfile)
class FacultyProfileAdmin(admin.ModelAdmin):
	list_display = ("user", "department", "is_guide", "is_coordinator", "is_hod")
	search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
	list_filter = ("is_guide", "is_coordinator", "is_hod", "department")
	ordering = ("user__username",)
	fieldsets = (
		("User Information", {
			"fields": ("user",)
		}),
		("Faculty Details", {
			"fields": ("department",)
		}),
		("Roles", {
			"fields": ("is_guide", "is_coordinator", "is_hod"),
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


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
	list_display = ("recipient", "notif_type", "is_read", "created_at", "related_abstract")
	search_fields = ("recipient__username", "message")
	list_filter = ("notif_type", "is_read", "created_at")
	ordering = ("-created_at",)
	readonly_fields = ("created_at",)


@admin.register(GroupEvaluation)
class GroupEvaluationAdmin(admin.ModelAdmin):
	list_display = ("group", "stage", "guide_submitted", "coordinator_submitted", "is_completed", "created_at")
	search_fields = ("group__leader__username",)
	list_filter = ("stage", "guide_submitted", "coordinator_submitted", "created_at")
	ordering = ("group", "stage")
	readonly_fields = ("created_at", "updated_at")
	fieldsets = (
		("Group & Stage", {
			"fields": ("group", "stage")
		}),
		("Guide Evaluation", {
			"fields": ("guide_technical_exposure", "guide_socially_relevant", "guide_product_based", "guide_research_oriented", "guide_review", "guide_submitted")
		}),
		("Coordinator Evaluation", {
			"fields": ("coordinator_technical_exposure", "coordinator_socially_relevant", "coordinator_product_based", "coordinator_research_oriented", "coordinator_review", "coordinator_submitted")
		}),
		("Timestamps", {
			"fields": ("created_at", "updated_at")
		}),
	)

	def is_completed(self, obj):
		"""Show whether both evaluations are submitted."""
		return obj.is_completed
	is_completed.boolean = True
	is_completed.short_description = "Completed"


@admin.register(EvaluationFile)
class EvaluationFileAdmin(admin.ModelAdmin):
	list_display = ("group", "stage", "file_name", "file_size", "uploaded_by", "uploaded_at")
	search_fields = ("group__leader__username", "file_name", "uploaded_by__username")
	list_filter = ("stage", "uploaded_at")
	ordering = ("-uploaded_at",)
	readonly_fields = ("uploaded_at",)


@admin.register(StudentEvaluation)
class StudentEvaluationAdmin(admin.ModelAdmin):
	list_display = ("student", "group", "stage", "guide_submitted", "coordinator_submitted", "finalized", "guide_total", "coordinator_total")
	search_fields = ("student__username", "group__leader__username")
	list_filter = ("stage", "guide_submitted", "coordinator_submitted", "finalized", "created_at")
	ordering = ("group", "stage", "student")
	readonly_fields = ("created_at", "updated_at", "guide_total", "coordinator_total")
	fieldsets = (
		("Student & Group", {
			"fields": ("student", "group", "stage")
		}),
		("Guide Marks", {
			"fields": (
				"guide_topic", "guide_planning", "guide_scalability", "guide_novelty",
				"guide_task_distribution", "guide_schedule", "guide_interim",
				"guide_presentation", "guide_viva", "guide_submitted"
			)
		}),
		("Coordinator Marks", {
			"fields": (
				"coordinator_topic", "coordinator_planning", "coordinator_scalability", "coordinator_novelty",
				"coordinator_task_distribution", "coordinator_schedule", "coordinator_interim",
				"coordinator_presentation", "coordinator_viva", "coordinator_submitted"
			)
		}),
		("Status", {
			"fields": ("finalized",)
		}),
		("Totals & Timestamps", {
			"fields": ("guide_total", "coordinator_total", "created_at", "updated_at")
		}),
	)

	def guide_total(self, obj):
		"""Display guide total marks."""
		return obj.guide_total
	guide_total.short_description = "Guide Total"

	def coordinator_total(self, obj):
		"""Display coordinator total marks."""
		return obj.coordinator_total
	coordinator_total.short_description = "Coordinator Total"

