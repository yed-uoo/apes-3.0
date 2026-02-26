from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Abstract, CoordinatorApproval, Group, GroupMember, GroupRequest, GuideRequest, StudentProfile, FacultyProfile, SustainableDevelopmentGoal


def _is_student(user):
	return hasattr(user, "student_profile")


def _is_guide(user):
	return hasattr(user, "faculty_profile") and user.faculty_profile.is_guide


def _is_coordinator(user):
	return hasattr(user, "faculty_profile") and user.faculty_profile.is_coordinator


def _has_dual_faculty_roles(user):
	return _is_guide(user) and _is_coordinator(user)


def _get_active_faculty_role(request):
	if not _has_dual_faculty_roles(request.user):
		return None
	active_role = request.session.get("active_role")
	if active_role in ["guide", "coordinator"]:
		return active_role
	return None


def _ensure_active_role_for_dual_faculty(request, required_role):
	if not _has_dual_faculty_roles(request.user):
		return None
	active_role = _get_active_faculty_role(request)
	if not active_role:
		return redirect("role_selection")
	if active_role != required_role:
		return redirect("guide_dashboard" if active_role == "guide" else "coordinator_dashboard")
	return None


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
	if _has_dual_faculty_roles(request.user):
		active_role = _get_active_faculty_role(request)
		if not active_role:
			return redirect("role_selection")
		return redirect("guide_dashboard" if active_role == "guide" else "coordinator_dashboard")
	if _is_guide(request.user):
		request.session["active_role"] = "guide"
		return redirect("guide_dashboard")
	elif _is_coordinator(request.user):
		request.session["active_role"] = "coordinator"
		return redirect("coordinator_dashboard")
	return render(request, "dashboard.html")


@login_required
def role_selection(request):
	if not hasattr(request.user, "faculty_profile"):
		return redirect("dashboard")

	if not _has_dual_faculty_roles(request.user):
		return redirect("dashboard")

	if request.method == "POST":
		selected_role = request.POST.get("role")
		if selected_role == "guide":
			request.session["active_role"] = "guide"
			return redirect("guide_dashboard")
		if selected_role == "coordinator":
			request.session["active_role"] = "coordinator"
			return redirect("coordinator_dashboard")
		messages.error(request, "Please select a valid role.")

	return render(request, "role_selection.html")


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
		action = request.POST.get("action")

		if action == "submit_sdg":
			if not group:
				messages.error(request, "You must be in a group to submit SDG.")
				return redirect("mini_project")

			if group.leader != request.user:
				messages.error(request, "Only the group leader can submit SDG.")
				return redirect("mini_project")

			coordinator_approval = CoordinatorApproval.objects.filter(
				group=group,
				status=CoordinatorApproval.STATUS_APPROVED,
			).first()
			if not coordinator_approval:
				messages.error(request, "Coordinator approval is required before SDG submission.")
				return redirect("mini_project")

			if SustainableDevelopmentGoal.objects.filter(group=group).exists():
				messages.info(request, "SDG already submitted for this group.")
				return redirect("mini_project")

			sdg_fields = [
				"sdg1", "sdg1_justification", "sdg2", "sdg2_justification", "sdg3", "sdg3_justification",
				"sdg4", "sdg4_justification", "sdg5", "sdg5_justification",
				"wp1", "wp1_justification", "wp2", "wp2_justification", "wp3", "wp3_justification",
				"wp4", "wp4_justification", "wp5", "wp5_justification",
				"po1", "po2", "po3", "po4", "po5", "pso1", "pso2",
			]
			sdg_data = {}
			for field in sdg_fields:
				value = request.POST.get(field, "").strip()
				sdg_data[field] = value

			SustainableDevelopmentGoal.objects.create(
				group=group,
				submitted_by=request.user,
				is_submitted=True,
				**sdg_data,
			)
			messages.success(request, "SDG submitted successfully.")
			return redirect("mini_project")

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

	coordinator_approval = None
	if group:
		try:
			coordinator_approval = CoordinatorApproval.objects.get(group=group)
		except CoordinatorApproval.DoesNotExist:
			pass

	sdg_submission = SustainableDevelopmentGoal.objects.filter(group=group).first() if group else None
	assigned_guide = _get_accepted_guide_for_group(group) if group else None
	selected_topic = Abstract.objects.filter(group=group, is_final_approved=True).order_by("-submitted_at").first() if group else None
	can_submit_sdg = bool(
		group
		and is_leader
		and coordinator_approval
		and coordinator_approval.status == CoordinatorApproval.STATUS_APPROVED
		and (not sdg_submission or not sdg_submission.is_submitted)
	)

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
		"sdg_submission": sdg_submission,
		"assigned_guide": assigned_guide,
		"can_submit_sdg": can_submit_sdg,
		"selected_topic": selected_topic,
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

	role_redirect = _ensure_active_role_for_dual_faculty(request, "guide")
	if role_redirect:
		return role_redirect

	accepted_requests = GuideRequest.objects.filter(
		guide=request.user,
		status=GuideRequest.STATUS_ACCEPTED,
	).select_related("group", "group__leader")

	group_ids = accepted_requests.values_list("group_id", flat=True)
	sdg_by_group_id = {
		sdg.group_id: sdg
		for sdg in SustainableDevelopmentGoal.objects.filter(group_id__in=group_ids)
	}

	assigned_groups = [
		{
			"group": guide_request.group,
			"sdg": sdg_by_group_id.get(guide_request.group_id),
		}
		for guide_request in accepted_requests
	]

	context = {
		"assigned_groups": assigned_groups,
	}
	return render(request, "guide_dashboard.html", context)


@login_required
def guide_requests(request):
	if not _is_guide(request.user):
		messages.error(request, "Only guides can access this page.")
		return redirect("dashboard")

	role_redirect = _ensure_active_role_for_dual_faculty(request, "guide")
	if role_redirect:
		return role_redirect

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


def _apply_abstract_derived_status(abstract):
	if abstract.is_final_approved:
		abstract.status = Abstract.STATUS_APPROVED
	elif abstract.guide_status == Abstract.STATUS_REJECTED or abstract.coordinator_status == Abstract.STATUS_REJECTED:
		abstract.status = Abstract.STATUS_REJECTED
	else:
		abstract.status = Abstract.STATUS_PENDING


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
			status=Abstract.STATUS_PENDING,
			guide_status=Abstract.STATUS_PENDING,
			coordinator_status=Abstract.STATUS_PENDING,
			is_final_approved=False,
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
	selected_topic = abstracts.filter(is_final_approved=True).first()

	context = {
		"group": group,
		"abstracts": abstracts,
		"selected_topic": selected_topic,
	}
	return render(request, "abstract_status.html", context)


@login_required
def faculty_abstracts(request):
	if not _is_guide(request.user):
		messages.error(request, "Only faculty can access this page.")
		return redirect("dashboard")

	role_redirect = _ensure_active_role_for_dual_faculty(request, "guide")
	if role_redirect:
		return role_redirect

	# Get all groups where this faculty has accepted guide requests
	accepted_groups = GuideRequest.objects.filter(
		guide=request.user,
		status=GuideRequest.STATUS_ACCEPTED
	).values_list("group_id", flat=True)

	# Get all abstracts from these groups
	all_abstracts = Abstract.objects.filter(group_id__in=accepted_groups).select_related("group", "group__leader").order_by("-submitted_at")

	pending_abstracts = all_abstracts.filter(guide_status=Abstract.STATUS_PENDING)
	approved_abstracts = all_abstracts.filter(guide_status=Abstract.STATUS_APPROVED)
	rejected_abstracts = all_abstracts.filter(guide_status=Abstract.STATUS_REJECTED)

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

	role_redirect = _ensure_active_role_for_dual_faculty(request, "guide")
	if role_redirect:
		return role_redirect

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
		if abstract.guide_status != Abstract.STATUS_PENDING:
			messages.info(request, "This abstract has already been reviewed.")
			return redirect("review_abstract", abstract_id=abstract_id)

		action = request.POST.get("action")
		feedback = request.POST.get("feedback", "").strip()

		if action == "approve":
			abstract.guide_status = Abstract.STATUS_APPROVED
			abstract.coordinator_status = Abstract.STATUS_PENDING
			abstract.is_final_approved = False
			_apply_abstract_derived_status(abstract)
			abstract.reviewed_at = timezone.now()
			abstract.reviewed_by = request.user
			abstract.feedback = feedback if feedback else None
			abstract.save()
			messages.success(request, "Abstract approved and forwarded to coordinator.")
			return redirect("faculty_abstracts")

		elif action == "reject":
			if not feedback:
				messages.error(request, "Feedback is required when rejecting an abstract.")
				return redirect("review_abstract", abstract_id=abstract_id)

			abstract.guide_status = Abstract.STATUS_REJECTED
			abstract.is_final_approved = False
			_apply_abstract_derived_status(abstract)
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

	role_redirect = _ensure_active_role_for_dual_faculty(request, "coordinator")
	if role_redirect:
		return role_redirect

	if request.method == "POST":
		abstract_id = request.POST.get("abstract_id")
		abstract_action = request.POST.get("abstract_action")
		if abstract_id and abstract_action:
			assigned_classes_for_post = list(
				CoordinatorApproval.objects.filter(coordinator=request.user)
				.values_list("group__leader__student_profile__class_name", flat=True)
				.distinct()
			)
			assigned_classes_for_post = [class_name for class_name in assigned_classes_for_post if class_name]

			abstract = get_object_or_404(Abstract, id=abstract_id)
			abstract_class = getattr(getattr(abstract.group.leader, "student_profile", None), "class_name", None)
			if abstract_class not in assigned_classes_for_post:
				messages.error(request, "You are not authorized to review this abstract.")
				return redirect("coordinator_dashboard")

			if abstract.guide_status != Abstract.STATUS_APPROVED or abstract.coordinator_status != Abstract.STATUS_PENDING:
				messages.error(request, "This abstract is not available for coordinator review.")
				return redirect("coordinator_dashboard")

			if abstract_action == "approve":
				abstract.coordinator_status = Abstract.STATUS_APPROVED
				abstract.is_final_approved = True
				_apply_abstract_derived_status(abstract)
				abstract.reviewed_at = timezone.now()
				abstract.reviewed_by = request.user
				abstract.save()
				messages.success(request, "Abstract approved by coordinator. Topic selected.")
			elif abstract_action == "reject":
				abstract.coordinator_status = Abstract.STATUS_REJECTED
				abstract.is_final_approved = False
				_apply_abstract_derived_status(abstract)
				abstract.reviewed_at = timezone.now()
				abstract.reviewed_by = request.user
				abstract.save()
				messages.info(request, "Abstract rejected by coordinator.")
			else:
				messages.error(request, "Invalid abstract review action.")
			return redirect("coordinator_dashboard")

		approval_id = request.POST.get("approval_id")
		action = request.POST.get("action")
		if not approval_id:
			messages.error(request, "Invalid coordinator action.")
			return redirect("coordinator_dashboard")
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

	faculty_profile = request.user.faculty_profile

	assigned_classes = list(
		CoordinatorApproval.objects.filter(coordinator=request.user)
		.values_list("group__leader__student_profile__class_name", flat=True)
		.distinct()
	)
	assigned_classes = [class_name for class_name in assigned_classes if class_name]

	groups_queryset = Group.objects.none()
	if assigned_classes:
		groups_queryset = Group.objects.filter(
			leader__student_profile__class_name__in=assigned_classes
		)

	groups_queryset = groups_queryset.select_related(
		"leader",
		"leader__student_profile",
		"coordinator_approval",
		"coordinator_approval__coordinator",
	).prefetch_related(
		Prefetch(
			"groupmember_set",
			queryset=GroupMember.objects.select_related("user", "user__student_profile").order_by("id"),
		),
		Prefetch(
			"guiderequest_set",
			queryset=GuideRequest.objects.select_related("guide").order_by("-id"),
		),
		Prefetch(
			"abstracts",
			queryset=Abstract.objects.select_related("reviewed_by").order_by("-submitted_at"),
		),
	)

	sdg_by_group_id = {}
	if groups_queryset:
		sdg_by_group_id = {
			sdg.group_id: sdg
			for sdg in SustainableDevelopmentGoal.objects.filter(group_id__in=groups_queryset.values_list("id", flat=True))
		}

	group_details = []
	for group in groups_queryset.order_by("id"):
		members = list(group.groupmember_set.all())
		guide_requests = list(group.guiderequest_set.all())
		latest_guide_request = guide_requests[0] if guide_requests else None
		assigned_guide = None
		if latest_guide_request and latest_guide_request.status == GuideRequest.STATUS_ACCEPTED:
			assigned_guide = latest_guide_request.guide

		abstracts = list(group.abstracts.all())
		approved_abstract = next((item for item in abstracts if item.is_final_approved), None)
		sdg_entry = sdg_by_group_id.get(group.id)

		group_details.append({
			"group": group,
			"class_name": getattr(getattr(group.leader, "student_profile", None), "class_name", None),
			"department": getattr(getattr(group.leader, "student_profile", None), "department", None),
			"leader_profile": getattr(group.leader, "student_profile", None),
			"members": members,
			"group_size": len(members),
			"coordinator_approval": getattr(group, "coordinator_approval", None),
			"latest_guide_request": latest_guide_request,
			"assigned_guide": assigned_guide,
			"approved_abstract": approved_abstract,
			"sdg": sdg_entry,
		})

	pending_approvals = CoordinatorApproval.objects.filter(
		coordinator=request.user,
		status=CoordinatorApproval.STATUS_PENDING,
	).select_related("group", "group__leader")

	coordinator_pending_abstracts = Abstract.objects.filter(
		guide_status=Abstract.STATUS_APPROVED,
		coordinator_status=Abstract.STATUS_PENDING,
		group__leader__student_profile__class_name__in=assigned_classes,
	).select_related("group", "group__leader").order_by("-submitted_at")

	context = {
		"pending_approvals": pending_approvals,
		"faculty_profile": faculty_profile,
		"assigned_classes": assigned_classes,
		"group_details": group_details,
		"coordinator_pending_abstracts": coordinator_pending_abstracts,
	}
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




