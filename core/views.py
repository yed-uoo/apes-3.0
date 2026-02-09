from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import Group, GroupMember, GroupRequest, GuideRequest, UserProfile


def _get_user_role(user):
	try:
		return user.userprofile.role
	except UserProfile.DoesNotExist:
		return UserProfile.ROLE_STUDENT


def _get_group_for_user(user):
	leader_group = Group.objects.filter(leader=user).first()
	if leader_group:
		return leader_group
	membership = GroupMember.objects.filter(user=user).select_related("group").first()
	return membership.group if membership else None


def _get_group_size(group):
	return GroupMember.objects.filter(group=group).count()


@login_required
def dashboard(request):
	role = _get_user_role(request.user)
	if role == UserProfile.ROLE_GUIDE:
		return render(request, "guide_dashboard.html")
	return render(request, "dashboard.html")


@login_required
def mini_project(request):
	role = _get_user_role(request.user)
	if role != UserProfile.ROLE_STUDENT:
		messages.error(request, "Only students can access this page.")
		return redirect("dashboard")

	group = _get_group_for_user(request.user)
	is_leader = group and group.leader == request.user
	group_size = _get_group_size(group) if group else 0
	group_full = group_size >= 5

	if request.method == "POST":
		if group and group.leader != request.user:
			messages.error(request, "Only the group leader can send requests.")
			return redirect("mini_project")
		to_user_id = request.POST.get("to_user_id")
		if group_full:
			messages.error(request, "Group is full.")
			return redirect("mini_project")
		if not to_user_id:
			messages.error(request, "Select a student to invite.")
			return redirect("mini_project")
		to_user = get_object_or_404(User, id=to_user_id)
		if to_user == request.user:
			messages.error(request, "You cannot invite yourself.")
			return redirect("mini_project")

		if not group:
			group = Group.objects.create(leader=request.user)
			GroupMember.objects.create(group=group, user=request.user)
			is_leader = True
			group_size = _get_group_size(group)
		else:
			GroupMember.objects.get_or_create(group=group, user=request.user)

		if Group.objects.filter(leader=to_user).exists() or GroupMember.objects.filter(user=to_user).exists():
			messages.error(request, "User is already in a group.")
			return redirect("mini_project")

		if GroupRequest.objects.filter(sender=request.user, recipient=to_user, status=GroupRequest.STATUS_PENDING).exists():
			messages.info(request, "Request already sent.")
			return redirect("mini_project")

		GroupRequest.objects.create(sender=request.user, recipient=to_user)
		messages.success(request, "Group request sent.")
		return redirect("mini_project")

	query = request.GET.get("q", "").strip()
	available_students = User.objects.exclude(id=request.user.id)
	if query:
		available_students = available_students.filter(Q(username__icontains=query) | Q(email__icontains=query))

	sent_requests = GroupRequest.objects.filter(sender=request.user).select_related("recipient")
	group_members = GroupMember.objects.filter(group=group).select_related("user") if group else []

	context = {
		"group": group,
		"is_leader": is_leader,
		"group_size": group_size,
		"group_full": group_full,
		"group_ready": group_size >= 4,
		"available_students": available_students,
		"sent_requests": sent_requests,
		"group_members": group_members,
		"query": query,
	}
	return render(request, "mini_project.html", context)


@login_required
def group_requests(request):
	role = _get_user_role(request.user)
	if role != UserProfile.ROLE_STUDENT:
		messages.error(request, "Only students can access this page.")
		return redirect("dashboard")

	if request.method == "POST":
		request_id = request.POST.get("request_id")
		action = request.POST.get("action")
		group_request = get_object_or_404(GroupRequest, id=request_id, recipient=request.user)
		sender = group_request.sender

		if action == "accept":
			if Group.objects.filter(leader=request.user).exists() or GroupMember.objects.filter(user=request.user).exists():
				group_request.status = GroupRequest.STATUS_REJECTED
				group_request.save()
				messages.error(request, "You are already in a group.")
				return redirect("group_requests")

			group = Group.objects.filter(leader=sender).first()
			if not group:
				group = Group.objects.create(leader=sender)

			group_size = _get_group_size(group)
			needs_sender = not GroupMember.objects.filter(group=group, user=sender).exists()
			needs_recipient = not GroupMember.objects.filter(group=group, user=request.user).exists()
			additional = (1 if needs_sender else 0) + (1 if needs_recipient else 0)
			if group_size + additional > 5:
				group_request.status = GroupRequest.STATUS_REJECTED
				group_request.save()
				messages.error(request, "Group is full.")
				return redirect("group_requests")

			GroupMember.objects.get_or_create(group=group, user=sender)
			GroupMember.objects.get_or_create(group=group, user=request.user)
			group_request.status = GroupRequest.STATUS_ACCEPTED
			group_request.save()
			messages.success(request, "Request accepted.")
		elif action == "reject":
			group_request.status = GroupRequest.STATUS_REJECTED
			group_request.save()
			messages.info(request, "Request rejected.")
		return redirect("group_requests")

	pending_requests = GroupRequest.objects.filter(recipient=request.user, status=GroupRequest.STATUS_PENDING).select_related("sender")
	context = {"pending_requests": pending_requests}
	return render(request, "group_requests.html", context)


@login_required
def guide_request(request):
	role = _get_user_role(request.user)
	if role != UserProfile.ROLE_STUDENT:
		messages.error(request, "Only students can access this page.")
		return redirect("dashboard")

	group = _get_group_for_user(request.user)
	if not group or group.leader != request.user:
		messages.error(request, "Only group leaders can request a guide.")
		return redirect("mini_project")

	group_size = _get_group_size(group)
	if group_size < 4:
		messages.error(request, "Group must have at least 4 members to request a guide.")
		return redirect("mini_project")

	existing_request = GuideRequest.objects.filter(group=group, status__in=[GuideRequest.STATUS_PENDING, GuideRequest.STATUS_ACCEPTED]).first()

	if request.method == "POST":
		guide_id = request.POST.get("guide_id")
		message = request.POST.get("message", "").strip()
		if existing_request:
			messages.error(request, "A guide request already exists for this group.")
			return redirect("guide_request")
		if not guide_id:
			messages.error(request, "Select a guide.")
			return redirect("guide_request")
		if not message:
			messages.error(request, "Message is required.")
			return redirect("guide_request")
		guide_user = get_object_or_404(User, id=guide_id)
		if _get_user_role(guide_user) != UserProfile.ROLE_GUIDE:
			messages.error(request, "Selected user is not a guide.")
			return redirect("guide_request")
		GuideRequest.objects.create(group=group, guide=guide_user, message=message)
		messages.success(request, "Guide request sent.")
		return redirect("guide_request")

	guides = User.objects.filter(userprofile__role=UserProfile.ROLE_GUIDE)
	context = {
		"guides": guides,
		"group": group,
		"group_size": group_size,
		"existing_request": existing_request,
	}
	return render(request, "guide_request.html", context)


@login_required
def guide_dashboard(request):
	role = _get_user_role(request.user)
	if role != UserProfile.ROLE_GUIDE:
		messages.error(request, "Only guides can access this page.")
		return redirect("dashboard")
	return render(request, "guide_dashboard.html")


@login_required
def guide_requests(request):
	role = _get_user_role(request.user)
	if role != UserProfile.ROLE_GUIDE:
		messages.error(request, "Only guides can access this page.")
		return redirect("dashboard")

	if request.method == "POST":
		request_id = request.POST.get("request_id")
		action = request.POST.get("action")
		guide_request_obj = get_object_or_404(GuideRequest, id=request_id, guide=request.user)

		if action == "accept":
			guide_request_obj.status = GuideRequest.STATUS_ACCEPTED
			guide_request_obj.save()
			messages.success(request, "Request accepted.")
		elif action == "reject":
			guide_request_obj.status = GuideRequest.STATUS_REJECTED
			guide_request_obj.save()
			messages.info(request, "Request rejected.")
		return redirect("guide_requests")

	pending_requests = GuideRequest.objects.filter(guide=request.user, status=GuideRequest.STATUS_PENDING).select_related("group", "group__leader")
	context = {"pending_requests": pending_requests}
	return render(request, "guide_requests.html", context)
