from django.contrib import admin

from .models import Group, GroupMember, GroupRequest, GuideRequest, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
	list_display = ("user", "role")
	search_fields = ("user__username", "user__email")
	list_filter = ("role",)
	ordering = ("user__username",)


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
