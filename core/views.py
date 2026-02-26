from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Abstract, CoordinatorApproval, Group, GroupMember, GroupRequest, GuideRequest, StudentProfile, FacultyProfile


def _is_student(user):
	return hasattr(user, "student_profile")


def _is_guide(user):
	return hasattr(user, "faculty_profile") and user.faculty_profile.is_guide


def _is_coordinator(user):
	return hasattr(user, "faculty_profile") and user.faculty_profile.is_coordinator


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
	is_guide = _is_guide(request.user)
	is_coord = _is_coordinator(request.user)
	if is_guide and is_coord:
		return render(request, "role_selection.html")
	elif is_guide:
		return render(request, "guide_dashboard.html")
	elif is_coord:
		return redirect("coordinator_dashboard")
	return render(request, "dashboard.html")


@login_required
def mini_project(request):
	if not _is_student(request.user):
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
	available_students = User.objects.filter(student_profile__isnull=False).exclude(id=request.user.id)
	if query:
		available_students = available_students.filter(Q(username__icontains=query) | Q(email__icontains=query))

	sent_requests = GroupRequest.objects.filter(sender=request.user).select_related("recipient")
	group_members = GroupMember.objects.filter(group=group).select_related("user") if group else []

	coordinator_approval = None
	if group:
		try:
			coordinator_approval = CoordinatorApproval.objects.get(group=group)
		except CoordinatorApproval.DoesNotExist:
			pass

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
		"coordinator_approval": coordinator_approval,
	}
	return render(request, "mini_project.html", context)


@login_required
def group_requests(request):
	if not _is_student(request.user):
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
	if not _is_student(request.user):
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

	try:
		coordinator_approval = CoordinatorApproval.objects.get(group=group)
		if coordinator_approval.status != CoordinatorApproval.STATUS_APPROVED:
			messages.error(request, "Your group must be approved by a coordinator before requesting a guide.")
			return redirect("mini_project")
	except CoordinatorApproval.DoesNotExist:
		messages.error(request, "Your group must be approved by a coordinator before requesting a guide.")
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
		if not _is_guide(guide_user):
			messages.error(request, "Selected user is not a guide.")
			return redirect("guide_request")
		GuideRequest.objects.create(group=group, guide=guide_user, message=message)
		messages.success(request, "Guide request sent.")
		return redirect("guide_request")

	guides = User.objects.filter(faculty_profile__is_guide=True)
	context = {
		"guides": guides,
		"group": group,
		"group_size": group_size,
		"existing_request": existing_request,
	}
	return render(request, "guide_request.html", context)


@login_required
def guide_dashboard(request):
	if not _is_guide(request.user):
		messages.error(request, "Only guides can access this page.")
		return redirect("dashboard")
	return render(request, "guide_dashboard.html")


@login_required
def guide_requests(request):
	if not _is_guide(request.user):
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


def _get_accepted_guide_for_group(group):
	"""Get the accepted guide for a group, if any."""
	accepted_request = GuideRequest.objects.filter(group=group, status=GuideRequest.STATUS_ACCEPTED).first()
	return accepted_request.guide if accepted_request else None


@login_required
def submit_abstract(request):
	if not _is_student(request.user):
		messages.error(request, "Only students can access this page.")
		return redirect("dashboard")

	group = _get_group_for_user(request.user)
	if not group:
		messages.error(request, "You must be in a group to submit an abstract.")
		return redirect("mini_project")

	if group.leader != request.user:
		messages.error(request, "Only the group leader can submit abstracts.")
		return redirect("mini_project")

	group_size = _get_group_size(group)
	if group_size < 4:
		messages.error(request, "Group must have at least 4 members to submit an abstract.")
		return redirect("mini_project")

	guide = _get_accepted_guide_for_group(group)
	if not guide:
		messages.error(request, "Your group must have an accepted guide before submitting an abstract.")
		return redirect("guide_request")

	if request.method == "POST":
		title = request.POST.get("title", "").strip()
		abstract_text = request.POST.get("abstract_text", "").strip()
		pdf_file = request.FILES.get("pdf_file")

		if not title:
			messages.error(request, "Title is required.")
			return redirect("submit_abstract")

		if not abstract_text:
			messages.error(request, "Abstract text is required.")
			return redirect("submit_abstract")

		if not pdf_file:
			messages.error(request, "PDF file is required.")
			return redirect("submit_abstract")

		if pdf_file.size > 10485760:  # 10MB
			messages.error(request, "PDF file size must be less than 10MB.")
			return redirect("submit_abstract")

		if not pdf_file.name.lower().endswith('.pdf'):
			messages.error(request, "Only PDF files are allowed.")
			return redirect("submit_abstract")

		# Create new abstract submission
		abstract = Abstract.objects.create(
			group=group,
			title=title,
			abstract_text=abstract_text,
			pdf_file=pdf_file.read(),
			pdf_filename=pdf_file.name,
			pdf_size=pdf_file.size,
			status=Abstract.STATUS_PENDING
		)

		messages.success(request, "Abstract submitted successfully!")
		return redirect("abstract_status")

	# Get previous submissions
	previous_abstracts = Abstract.objects.filter(group=group).order_by("-submitted_at")

	context = {
		"group": group,
		"guide": guide,
		"previous_abstracts": previous_abstracts,
	}
	return render(request, "submit_abstract.html", context)


@login_required
def abstract_status(request):
	if not _is_student(request.user):
		messages.error(request, "Only students can access this page.")
		return redirect("dashboard")

	group = _get_group_for_user(request.user)
	if not group:
		messages.error(request, "You must be in a group to view abstract status.")
		return redirect("mini_project")

	abstracts = Abstract.objects.filter(group=group).select_related("reviewed_by").order_by("-submitted_at")

	context = {
		"group": group,
		"abstracts": abstracts,
	}
	return render(request, "abstract_status.html", context)


@login_required
def faculty_abstracts(request):
	if not _is_guide(request.user):
		messages.error(request, "Only faculty can access this page.")
		return redirect("dashboard")

	# Get all groups where this faculty has accepted guide requests
	accepted_groups = GuideRequest.objects.filter(
		guide=request.user,
		status=GuideRequest.STATUS_ACCEPTED
	).values_list("group_id", flat=True)

	# Get all abstracts from these groups
	all_abstracts = Abstract.objects.filter(group_id__in=accepted_groups).select_related("group", "group__leader").order_by("-submitted_at")

	pending_abstracts = all_abstracts.filter(status=Abstract.STATUS_PENDING)
	approved_abstracts = all_abstracts.filter(status=Abstract.STATUS_APPROVED)
	rejected_abstracts = all_abstracts.filter(status=Abstract.STATUS_REJECTED)

	context = {
		"pending_abstracts": pending_abstracts,
		"approved_abstracts": approved_abstracts,
		"rejected_abstracts": rejected_abstracts,
	}
	return render(request, "faculty_abstracts.html", context)


@login_required
def review_abstract(request, abstract_id):
	if not _is_guide(request.user):
		messages.error(request, "Only faculty can access this page.")
		return redirect("dashboard")

	abstract = get_object_or_404(Abstract, id=abstract_id)

	# Verify this faculty is the accepted guide for this group
	guide_request = GuideRequest.objects.filter(
		group=abstract.group,
		guide=request.user,
		status=GuideRequest.STATUS_ACCEPTED
	).first()

	if not guide_request:
		messages.error(request, "You are not the assigned guide for this group.")
		return redirect("faculty_abstracts")

	if request.method == "POST":
		action = request.POST.get("action")
		feedback = request.POST.get("feedback", "").strip()

		if action == "approve":
			abstract.status = Abstract.STATUS_APPROVED
			abstract.reviewed_at = timezone.now()
			abstract.reviewed_by = request.user
			abstract.feedback = feedback if feedback else None
			abstract.save()
			messages.success(request, "Abstract approved successfully!")
			return redirect("faculty_abstracts")

		elif action == "reject":
			if not feedback:
				messages.error(request, "Feedback is required when rejecting an abstract.")
				return redirect("review_abstract", abstract_id=abstract_id)

			abstract.status = Abstract.STATUS_REJECTED
			abstract.reviewed_at = timezone.now()
			abstract.reviewed_by = request.user
			abstract.feedback = feedback
			abstract.save()
			messages.success(request, "Abstract rejected with feedback.")
			return redirect("faculty_abstracts")

	# Get group members
	group_members = GroupMember.objects.filter(group=abstract.group).select_related("user")

	context = {
		"abstract": abstract,
		"group_members": group_members,
	}
	return render(request, "review_abstract.html", context)


@login_required
def download_abstract(request, abstract_id):
	abstract = get_object_or_404(Abstract, id=abstract_id)

	# Check access: either student in the group or assigned faculty
@login_required
def download_abstract(request, abstract_id):
	abstract = get_object_or_404(Abstract, id=abstract_id)
	has_access = False

	if _is_student(request.user):
		group = _get_group_for_user(request.user)
		has_access = group and group.id == abstract.group.id

	elif _is_guide(request.user):
		guide_request = GuideRequest.objects.filter(
			group=abstract.group,
			guide=request.user,
			status=GuideRequest.STATUS_ACCEPTED
		).exists()
		has_access = guide_request

	if not has_access:
		messages.error(request, "You don't have permission to download this abstract.")
		return redirect("dashboard")

	if not abstract.pdf_file:
		messages.error(request, "No PDF file available for this abstract.")
		return redirect("abstract_status" if _is_student(request.user) else "faculty_abstracts")

	response = HttpResponse(abstract.pdf_file, content_type='application/pdf')
	response['Content-Disposition'] = f'attachment; filename="{abstract.pdf_filename}"'
	return response


@login_required
def request_coordinator_approval(request):
	if not _is_student(request.user):
		messages.error(request, "Only students can request coordinator approval.")
		return redirect("dashboard")

	group = _get_group_for_user(request.user)
	if not group or group.leader != request.user:
		messages.error(request, "Only group leaders can request coordinator approval.")
		return redirect("mini_project")

	group_size = _get_group_size(group)
	if group_size < 4:
		messages.error(request, "Group must have at least 4 members to request coordinator approval.")
		return redirect("mini_project")

	if hasattr(group, 'coordinator_approval'):
		messages.info(request, "Coordinator approval request already exists.")
		return redirect("mini_project")

	if request.method == "POST":
		coordinator_id = request.POST.get("coordinator_id")
		if not coordinator_id:
			messages.error(request, "Please select a coordinator.")
			return redirect("request_coordinator_approval")

		coordinator_user = get_object_or_404(User, id=coordinator_id)
		if not _is_coordinator(coordinator_user):
			messages.error(request, "Selected user is not a coordinator.")
			return redirect("request_coordinator_approval")

		CoordinatorApproval.objects.create(group=group, coordinator=coordinator_user)
		messages.success(request, "Coordinator approval request sent.")
		return redirect("mini_project")

	coordinators = User.objects.filter(faculty_profile__is_coordinator=True)
	context = {
		"coordinators": coordinators,
		"group": group,
		"group_size": group_size,
	}
	return render(request, "request_coordinator_approval.html", context)


@login_required
def coordinator_dashboard(request):
	if not _is_coordinator(request.user):
		messages.error(request, "Only coordinators can access this page.")
		return redirect("dashboard")

	if request.method == "POST":
		approval_id = request.POST.get("approval_id")
		action = request.POST.get("action")
		approval = get_object_or_404(CoordinatorApproval, id=approval_id, coordinator=request.user)

		if action == "approve":
			approval.status = CoordinatorApproval.STATUS_APPROVED
			approval.save()
			messages.success(request, "Group approved.")
		elif action == "reject":
			approval.status = CoordinatorApproval.STATUS_REJECTED
			approval.save()
			messages.info(request, "Group rejected.")
		return redirect("coordinator_dashboard")

	pending_approvals = CoordinatorApproval.objects.filter(
		coordinator=request.user,
		status=CoordinatorApproval.STATUS_PENDING
	).select_related("group", "group__leader")

	context = {"pending_approvals": pending_approvals}
	return render(request, "coordinator_dashboard.html", context)


@login_required
def profile(request):
	context = {
		"is_student": _is_student(request.user),
		"is_guide": _is_guide(request.user),
		"is_coordinator": _is_coordinator(request.user),
	}
	
	if _is_student(request.user):
		context["student_profile"] = request.user.student_profile
	elif hasattr(request.user, "faculty_profile"):
		context["faculty_profile"] = request.user.faculty_profile
	
	return render(request, "profile.html", context)


# simple stub pages to satisfy sidebar links
@login_required
@require_http_methods(["GET"])
def group_members(request):
    # reuse mini_project context for now
    return mini_project(request)

@login_required
@require_http_methods(["GET"])
def weekly_progress(request):
    return render(request, "weekly_progress.html")

@login_required
@require_http_methods(["GET"])
def meetings(request):
    return render(request, "meetings.html")

@login_required
@require_http_methods(["GET"])
def documents(request):
    return render(request, "documents.html")

@login_required
@require_http_methods(["GET"])
def project_status(request):
    return render(request, "project_status.html")

@login_required
@require_http_methods(["GET"])
def settings(request):
    return render(request, "settings.html")
