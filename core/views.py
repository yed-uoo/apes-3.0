import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Prefetch, Q
from django.http import FileResponse, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import Abstract, CoordinatorApproval, CoordinatorAssignment, Group, GroupMember, GroupRequest, GuideRequest, Notification, StudentProfile, FacultyProfile, SustainableDevelopmentGoal, GroupEvaluation, EvaluationFile, ProjectReport, StudentEvaluation


def _is_student(user):
	return hasattr(user, "student_profile")


def _is_guide(user):
	return hasattr(user, "faculty_profile") and user.faculty_profile.is_guide


def _is_coordinator(user):
	return hasattr(user, "faculty_profile") and user.faculty_profile.is_coordinator


def _is_hod(user):
	return hasattr(user, "faculty_profile") and user.faculty_profile.is_hod


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


def _is_stage_completed_for_group(group, stage):
	"""True when all group members have finalized evaluation for a stage."""
	member_ids = list(GroupMember.objects.filter(group=group).values_list("user_id", flat=True))
	if not member_ids:
		return False
	evaluations = StudentEvaluation.objects.filter(group=group, stage=stage, student_id__in=member_ids)
	if evaluations.count() != len(member_ids):
		return False
	return not evaluations.filter(finalized=False).exists()


def _get_ese_availability(student_eval):
	"""Return (is_available, message) describing ESE readiness for a student."""
	if not student_eval:
		return False, "Second Evaluation record is not available for this student."
	if not student_eval.second_eval_completed:
		return False, "Second Evaluation must be completed before entering ESE marks."
	if not student_eval.final_guide_submitted:
		return False, "Final Guide Evaluation must be submitted before ESE marks."
	if not student_eval.attendance_submitted:
		return False, "Attendance marks must be submitted before ESE marks."
	try:
		project_report = student_eval.group.project_report
	except ProjectReport.DoesNotExist:
		project_report = None
	if not project_report or project_report.final_mark is None:
		return False, "Project Report must be evaluated before recording ESE marks."
	if not student_eval.cie_calculated:
		return False, "CIE must be calculated before ESE is enabled."
	return True, ""


def _update_ese_completion(student_eval):
	"""Recalculate ESE aggregates whenever any evaluator submits."""
	final_mark = student_eval.ese_final_calculated
	if final_mark is not None:
		student_eval.ese_final = final_mark
	else:
		student_eval.ese_final = None
		_reset_final_result(student_eval)

	all_submitted = (
		student_eval.ese_guide_submitted
		and student_eval.ese_coord1_submitted
		and student_eval.ese_coord2_submitted
	)
	student_eval.ese_completed = all_submitted
	student_eval.ese_completed_at = timezone.now() if all_submitted else None
	return student_eval.ese_final is not None


def _reset_final_result(student_eval):
	"""Clear cached final result values when prerequisites are invalid."""
	student_eval.final_total = None
	student_eval.final_percentage = None
	student_eval.final_grade = None
	student_eval.result_calculated = False


def calculate_final_result(student_eval):
	"""Compute final total, percentage, and grade once CIE and ESE are done."""
	if not student_eval:
		return
	if not (
		student_eval.cie_total is not None
		and student_eval.ese_final is not None
	):
		return
	final_total = student_eval.cie_total + student_eval.ese_final
	final_percentage = round((final_total / 150) * 100, 2)
	if (
		student_eval.result_calculated
		and student_eval.final_total == final_total
		and student_eval.final_percentage == final_percentage
	):
		return
	grade = _derive_grade_from_percentage(final_percentage)
	student_eval.final_total = final_total
	student_eval.final_percentage = final_percentage
	student_eval.final_grade = grade
	student_eval.result_calculated = True
	student_eval.save(update_fields=[
		"final_total",
		"final_percentage",
		"final_grade",
		"result_calculated",
	])


def _derive_grade_from_percentage(percentage):
	if percentage >= 90:
		return "S"
	if percentage >= 85:
		return "A+"
	if percentage >= 80:
		return "A"
	if percentage >= 75:
		return "B+"
	if percentage >= 70:
		return "B"
	if percentage >= 65:
		return "C+"
	if percentage >= 60:
		return "C"
	if percentage >= 55:
		return "D"
	if percentage >= 50:
		return "P"
	return "F"


def _ensure_final_result(student_eval):
	"""Backfill final result if prerequisites met but cache stale."""
	if not student_eval:
		return
	calculate_final_result(student_eval)


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
	elif _is_hod(request.user):
		return redirect("hod_dashboard")
	
	# Get student-specific data for dashboard
	group = _get_group_for_user(request.user)
	group_size = _get_group_size(group) if group else 0
	group_ready = group_size >= 4
	
	# Get pending requests count
	pending_requests_count = GroupRequest.objects.filter(
		recipient=request.user,
		status=GroupRequest.STATUS_PENDING
	).count()
	
	# Get evaluation files for the group
	evaluation_files = {}
	evaluations = {}
	if group:
		evaluation_files = {
			"zeroth": EvaluationFile.objects.filter(group=group, stage="zeroth").first(),
			"first": EvaluationFile.objects.filter(group=group, stage="first").first(),
			"second": EvaluationFile.objects.filter(group=group, stage="second").first(),
			"final": EvaluationFile.objects.filter(group=group, stage="final").first(),
		}
		evaluations = {
			"zeroth": GroupEvaluation.objects.filter(group=group, stage="zeroth").first(),
			"first": GroupEvaluation.objects.filter(group=group, stage="first").first(),
			"second": GroupEvaluation.objects.filter(group=group, stage="second").first(),
			"final": GroupEvaluation.objects.filter(group=group, stage="final").first(),
		}
	
	context = {
		'group': group,
		'group_size': group_size,
		'group_ready': group_ready,
		'pending_requests_count': pending_requests_count,
		'evaluation_files': evaluation_files,
		'evaluations': evaluations,
	}
	return render(request, "dashboard.html", context)


@login_required
def switch_role(request):
	if not _has_dual_faculty_roles(request.user):
		return redirect("dashboard")
	active_role = _get_active_faculty_role(request)
	if active_role == "guide":
		request.session["active_role"] = "coordinator"
		return redirect("coordinator_dashboard")
	else:
		request.session["active_role"] = "guide"
		return redirect("guide_dashboard")


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
		
		# Validate that recipient is a student
		if not _is_student(to_user):
			messages.error(request, "You can only send group requests to students.")
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

		group_request, created = GroupRequest.objects.get_or_create(
			sender=request.user,
			recipient=to_user,
			defaults={"status": GroupRequest.STATUS_PENDING},
		)
		if not created:
			if group_request.status == GroupRequest.STATUS_PENDING:
				messages.info(request, "Request already sent and awaiting response.")
				return redirect("mini_project")
			group_request.status = GroupRequest.STATUS_PENDING
			group_request.created_at = timezone.now()
			group_request.save(update_fields=["status", "created_at"])
			messages.success(request, "Group request re-sent.")
		else:
			messages.success(request, "Group request sent.")
		return redirect("mini_project")

	query = request.GET.get("q", "").strip()
	# Only show students in the available list (exclude faculty, coordinators, HOD, admin)
	available_students = User.objects.filter(student_profile__isnull=False).exclude(id=request.user.id)
	if query:
		available_students = available_students.filter(Q(username__icontains=query) | Q(email__icontains=query))

	sent_requests = GroupRequest.objects.filter(sender=request.user).select_related("recipient")
	group_members = GroupMember.objects.filter(group=group).select_related("user") if group else []

	coordinator_approval = None
	coordinator_approvals = []
	is_coordinator_approved = False
	if group:
		coordinator_approvals = list(CoordinatorApproval.objects.filter(group=group).select_related("coordinator", "coordinator__faculty_profile"))
		# Check if ANY coordinator has approved
		is_coordinator_approved = any(approval.status == CoordinatorApproval.STATUS_APPROVED for approval in coordinator_approvals)
		# For backward compatibility, set coordinator_approval to first approved or first overall
		if is_coordinator_approved:
			coordinator_approval = next((a for a in coordinator_approvals if a.status == CoordinatorApproval.STATUS_APPROVED), None)
		elif coordinator_approvals:
			coordinator_approval = coordinator_approvals[0]

	sdg_submission = SustainableDevelopmentGoal.objects.filter(group=group).first() if group else None
	assigned_guide = _get_accepted_guide_for_group(group) if group else None
	selected_topic = Abstract.objects.filter(group=group, is_final_approved=True).order_by("-submitted_at").first() if group else None
	can_submit_sdg = bool(
		group
		and is_leader
		and is_coordinator_approved
		and (not sdg_submission or not sdg_submission.is_submitted)
	)
	project_report = ProjectReport.objects.filter(group=group).first() if group else None
	first_complete = _is_stage_completed_for_group(group, "first") if group else False
	second_complete = _is_stage_completed_for_group(group, "second") if group else False

	# Get evaluation files and evaluations for the group
	evaluation_files = {}
	evaluations = {}
	student_evaluations = {}
	if group:
		evaluation_files = {
			"zeroth": EvaluationFile.objects.filter(group=group, stage="zeroth").first(),
			"first": EvaluationFile.objects.filter(group=group, stage="first").first(),
			"second": EvaluationFile.objects.filter(group=group, stage="second").first(),
			"final": EvaluationFile.objects.filter(group=group, stage="final").first(),
		}
		evaluations = {
			"zeroth": GroupEvaluation.objects.filter(group=group, stage="zeroth").first(),
			"first": GroupEvaluation.objects.filter(group=group, stage="first").first(),
			"second": GroupEvaluation.objects.filter(group=group, stage="second").first(),
			"final": GroupEvaluation.objects.filter(group=group, stage="final").first(),
		}
		
		# Get student evaluations for current user
		student_evaluations = {
			"first": StudentEvaluation.objects.filter(student=request.user, stage="first").first(),
			"second": StudentEvaluation.objects.filter(student=request.user, stage="second").first(),
		}
		_ensure_final_result(student_evaluations.get("second"))

	# Official SDG names for display
	sdg_names = {
		'1': 'No Poverty', '2': 'Zero Hunger', '3': 'Good Health and Well-being',
		'4': 'Quality Education', '5': 'Gender Equality', '6': 'Clean Water and Sanitation',
		'7': 'Affordable and Clean Energy', '8': 'Decent Work and Economic Growth',
		'9': 'Industry, Innovation and Infrastructure', '10': 'Reduced Inequalities',
		'11': 'Sustainable Cities and Communities', '12': 'Responsible Consumption and Production',
		'13': 'Climate Action', '14': 'Life Below Water', '15': 'Life on Land',
		'16': 'Peace, Justice and Strong Institutions', '17': 'Partnerships for the Goals',
	}
	selected_sdgs = []
	selected_wps = []
	po_pso_pairs = []
	if sdg_submission:
		for i in range(1, 6):
			val = getattr(sdg_submission, f'sdg{i}', '').strip()
			if val:
				selected_sdgs.append({
					'number': val,
					'name': sdg_names.get(val, val),
					'justification': getattr(sdg_submission, f'sdg{i}_justification', '').strip(),
				})
		for i in range(1, 6):
			val = getattr(sdg_submission, f'wp{i}', '').strip()
			if val:
				selected_wps.append({
					'number': i,
					'title': val,
					'justification': getattr(sdg_submission, f'wp{i}_justification', '').strip(),
				})
		po_pso_pairs = [
			('PO1', sdg_submission.po1), ('PO2', sdg_submission.po2),
			('PO3', sdg_submission.po3), ('PO4', sdg_submission.po4),
			('PO5', sdg_submission.po5), ('PSO1', sdg_submission.pso1),
			('PSO2', sdg_submission.pso2),
		]

	second_eval_record = student_evaluations.get("second") if student_evaluations else None
	ese_allowed = False
	ese_message = "End Semester Evaluation will be available after completion of all internal evaluations."
	if second_eval_record:
		ese_allowed, ese_reason = _get_ese_availability(second_eval_record)
		if not ese_allowed and ese_reason:
			ese_message = ese_reason
	else:
		ese_message = "Second Evaluation record is not available for this student."

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
		"coordinator_approvals": coordinator_approvals,
		"is_coordinator_approved": is_coordinator_approved,
		"sdg_submission": sdg_submission,
		"selected_sdgs": selected_sdgs,
		"selected_wps": selected_wps,
		"po_pso_pairs": po_pso_pairs,
		"assigned_guide": assigned_guide,
		"can_submit_sdg": can_submit_sdg,
		"selected_topic": selected_topic,
		"evaluation_files": evaluation_files,
		"evaluations": evaluations,
		"student_evaluations": student_evaluations,
		"project_report": project_report,
		"first_complete": first_complete,
		"second_complete": second_complete,
		"can_submit_report": bool(group and first_complete and second_complete),
		"ese_status": {
			"allowed": ese_allowed,
			"message": ese_message,
		},
	}
	return render(request, "mini_project.html", context)


@login_required
def sdg_submission(request):
	if not _is_student(request.user):
		messages.error(request, "Only students can access this page.")
		return redirect("dashboard")

	group = _get_group_for_user(request.user)
	is_leader = group and group.leader == request.user

	if request.method == "POST":
		if not group:
			messages.error(request, "You must be in a group to submit SDG.")
			return redirect("mini_project")

		if group.leader != request.user:
			messages.error(request, "Only the group leader can submit SDG.")
			return redirect("sdg_submission")

		coordinator_approval = CoordinatorApproval.objects.filter(
			group=group,
			status=CoordinatorApproval.STATUS_APPROVED,
		).first()
		if not coordinator_approval:
			messages.error(request, "Coordinator approval is required before SDG submission.")
			return redirect("sdg_submission")

		if SustainableDevelopmentGoal.objects.filter(group=group).exists():
			messages.info(request, "SDG already submitted for this group.")
			return redirect("sdg_submission")

		# Collect selected SDG goals (1-17)
		selected_sdgs = []
		for i in range(1, 6):
			sdg_value = request.POST.get(f"sdg{i}", "").strip()
			if sdg_value:
				selected_sdgs.append(sdg_value)

		# Validate selection
		if len(selected_sdgs) < 4 or len(selected_sdgs) > 5:
			messages.error(request, "You must select between 4 and 5 SDG goals.")
			return redirect("sdg_submission")

		# Check for duplicates
		if len(selected_sdgs) != len(set(selected_sdgs)):
			messages.error(request, "Cannot select the same SDG goal multiple times.")
			return redirect("sdg_submission")

		# Create SDG record with selected goal numbers stored in SDG fields
		sdg_data = {
			"group": group,
			"submitted_by": request.user,
			"is_submitted": True,
		}

		# Store SDG goal numbers in the sdg1-sdg5 fields
		for idx, sdg_num in enumerate(selected_sdgs, 1):
			sdg_data[f"sdg{idx}"] = sdg_num

		SustainableDevelopmentGoal.objects.create(**sdg_data)
		messages.success(request, f"SDG submitted successfully with {len(selected_sdgs)} goals selected.")
		return redirect("mini_project")

	# GET request - show SDG submission form
	coordinator_approval = CoordinatorApproval.objects.filter(
		group=group,
		status=CoordinatorApproval.STATUS_APPROVED,
	).first() if group else None

	sdg_submission = SustainableDevelopmentGoal.objects.filter(group=group).first() if group else None

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
		"coordinator_approval": coordinator_approval,
		"sdg_submission": sdg_submission,
		"can_submit_sdg": can_submit_sdg,
	}
	return render(request, "sdg_submission.html", context)


@login_required
def project_report(request):
	if not _is_student(request.user):
		messages.error(request, "Only students can access project report submission.")
		return redirect("dashboard")
	return redirect(f"{reverse('mini_project')}#project-report")


@login_required
def submit_project_report(request, group_id):
	if not _is_student(request.user):
		messages.error(request, "Only students can submit project reports.")
		return redirect("dashboard")

	if request.method != "POST":
		return redirect(f"{reverse('mini_project')}#project-report")

	group = get_object_or_404(Group, id=group_id)
	if group.leader_id != request.user.id:
		messages.error(request, "Only the group leader can upload the project report.")
		return redirect(f"{reverse('mini_project')}#project-report")

	if not (_is_stage_completed_for_group(group, "first") and _is_stage_completed_for_group(group, "second")):
		messages.error(request, "Project report can only be submitted after completion of First and Second Evaluations.")
		return redirect(f"{reverse('mini_project')}#project-report")

	report_file = request.FILES.get("report_file")
	if not report_file:
		messages.error(request, "Please choose a PDF file to upload.")
		return redirect(f"{reverse('mini_project')}#project-report")

	file_name = report_file.name.lower()
	if not file_name.endswith(".pdf"):
		messages.error(request, "Only PDF files are allowed.")
		return redirect(f"{reverse('mini_project')}#project-report")

	content_type = (getattr(report_file, "content_type", "") or "").lower()
	if content_type and "pdf" not in content_type:
		messages.error(request, "Only PDF files are allowed.")
		return redirect(f"{reverse('mini_project')}#project-report")

	report, created = ProjectReport.objects.get_or_create(
		group=group,
		defaults={
			"uploaded_by": request.user,
			"report_file": report_file,
			"review_status": ProjectReport.STATUS_PENDING,
		},
	)

	if created:
		messages.success(request, "Project report uploaded successfully.")
	else:
		if report.report_file:
			report.report_file.delete(save=False)
		report.report_file = report_file
		report.uploaded_by = request.user
		report.uploaded_at = timezone.now()
		report.coordinator1_mark = None
		report.coordinator2_mark = None
		report.final_mark = None
		report.coordinator1_submitted = False
		report.coordinator2_submitted = False
		report.review_status = ProjectReport.STATUS_PENDING
		report.rejection_review = ""
		report.rejected_by = None
		report.rejected_at = None
		report.save()
		messages.success(request, "Project report updated successfully.")

	return redirect(f"{reverse('mini_project')}#project-report")


@login_required
def submit_report_mark(request, report_id):
	if not _is_coordinator(request.user):
		return HttpResponseForbidden("Only coordinators can submit report marks.")

	role_redirect = _ensure_active_role_for_dual_faculty(request, "coordinator")
	if role_redirect:
		return role_redirect

	if request.method != "POST":
		return redirect("coordinator_dashboard")

	report = get_object_or_404(
		ProjectReport.objects.select_related("group", "group__leader", "group__leader__student_profile"),
		id=report_id,
	)

	student_profile = getattr(report.group.leader, "student_profile", None)
	if not student_profile or not student_profile.student_class:
		return HttpResponseForbidden("Group leader class information is missing.")

	coordinator_role = None
	assignments = list(
		CoordinatorAssignment.objects.filter(student_class=student_profile.student_class)
		.select_related("faculty")
		.order_by("id")
	)
	for idx, assignment in enumerate(assignments, 1):
		if assignment.faculty_id == request.user.id:
			coordinator_role = idx
			break

	if coordinator_role not in (1, 2):
		return HttpResponseForbidden("You are not assigned as a coordinator for this group.")

	if report.review_status == ProjectReport.STATUS_REJECTED:
		messages.error(request, "This report was rejected. Wait for student resubmission before marking.")
		return redirect("coordinator_dashboard")

	mark_raw = request.POST.get("report_mark", "").strip()
	try:
		mark = int(mark_raw)
	except (TypeError, ValueError):
		messages.error(request, "Report mark must be a whole number between 0 and 10.")
		return redirect("coordinator_dashboard")

	if mark < 0 or mark > 10:
		messages.error(request, "Report mark must be between 0 and 10.")
		return redirect("coordinator_dashboard")

	if coordinator_role == 1:
		report.coordinator1_mark = mark
		report.coordinator1_submitted = True
	else:
		report.coordinator2_mark = mark
		report.coordinator2_submitted = True

	if report.coordinator1_submitted and report.coordinator2_submitted and report.coordinator1_mark is not None and report.coordinator2_mark is not None:
		report.final_mark = round((report.coordinator1_mark + report.coordinator2_mark) / 2)
		report.review_status = ProjectReport.STATUS_APPROVED
	else:
		report.final_mark = None
		report.review_status = ProjectReport.STATUS_PENDING

	report.rejection_review = ""
	report.rejected_by = None
	report.rejected_at = None

	report.save()

	# Attempt CIE calculation for all group members now that report mark may be final
	if report.final_mark is not None:
		for member in GroupMember.objects.filter(group=report.group).select_related("user"):
			second_eval = StudentEvaluation.objects.filter(student=member.user, group=report.group, stage="second").first()
			if second_eval:
				_try_calculate_cie(second_eval)

	messages.success(request, "Project report mark saved successfully.")
	return redirect("coordinator_dashboard")


@login_required
def submit_report_rejection(request, report_id):
	if not _is_coordinator(request.user):
		return HttpResponseForbidden("Only coordinators can reject project reports.")

	role_redirect = _ensure_active_role_for_dual_faculty(request, "coordinator")
	if role_redirect:
		return role_redirect

	if request.method != "POST":
		return redirect("coordinator_dashboard")

	report = get_object_or_404(
		ProjectReport.objects.select_related("group", "group__leader", "group__leader__student_profile"),
		id=report_id,
	)

	student_profile = getattr(report.group.leader, "student_profile", None)
	if not student_profile or not student_profile.student_class:
		return HttpResponseForbidden("Group leader class information is missing.")

	coordinator_assigned = CoordinatorAssignment.objects.filter(
		student_class=student_profile.student_class,
		faculty=request.user,
	).exists()
	if not coordinator_assigned:
		return HttpResponseForbidden("You are not assigned as a coordinator for this group.")

	review_text = request.POST.get("rejection_review", "").strip()
	if not review_text:
		messages.error(request, "Rejection review text is required.")
		return redirect("coordinator_dashboard")

	report.review_status = ProjectReport.STATUS_REJECTED
	report.rejection_review = review_text
	report.rejected_by = request.user
	report.rejected_at = timezone.now()
	report.coordinator1_mark = None
	report.coordinator2_mark = None
	report.final_mark = None
	report.coordinator1_submitted = False
	report.coordinator2_submitted = False
	report.save()

	messages.success(request, "Project report rejected. Students must upload a new report.")
	return redirect("coordinator_dashboard")


@login_required
def download_project_report(request, report_id):
	report = get_object_or_404(
		ProjectReport.objects.select_related("group", "group__leader", "group__leader__student_profile"),
		id=report_id,
	)
	group = report.group

	allowed = False
	if request.user.is_superuser:
		allowed = True
	elif group.leader_id == request.user.id or GroupMember.objects.filter(group=group, user=request.user).exists():
		allowed = True
	elif _is_guide(request.user) and GuideRequest.objects.filter(group=group, guide=request.user, status=GuideRequest.STATUS_ACCEPTED).exists():
		allowed = True
	elif _is_coordinator(request.user):
		student_profile = getattr(group.leader, "student_profile", None)
		if student_profile and student_profile.student_class:
			allowed = CoordinatorAssignment.objects.filter(student_class=student_profile.student_class, faculty=request.user).exists()
	elif _is_hod(request.user):
		student_profile = getattr(group.leader, "student_profile", None)
		hod_dept = getattr(getattr(request.user, "faculty_profile", None), "department", None)
		allowed = bool(student_profile and hod_dept and student_profile.department == hod_dept)

	if not allowed:
		return HttpResponseForbidden("You are not authorized to download this project report.")

	file_name = os.path.basename(report.report_file.name)
	return FileResponse(report.report_file.open("rb"), as_attachment=True, filename=file_name)


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

	# Check if any coordinator has approved the group
	coordinator_approvals = CoordinatorApproval.objects.filter(group=group)
	is_coordinator_approved = any(approval.status == CoordinatorApproval.STATUS_APPROVED for approval in coordinator_approvals)
	
	if not coordinator_approvals.exists():
		messages.error(request, "Your group must be approved by a coordinator before requesting a guide.")
		return redirect("mini_project")
	
	if not is_coordinator_approved:
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
	report_by_group_id = {
		report.group_id: report
		for report in ProjectReport.objects.filter(group_id__in=group_ids)
	}

	# Get evaluations for assigned groups
	evaluations_by_group = {}
	evaluation_files_by_group = {}
	student_evaluations_by_group = {}
	for group_id in group_ids:
		evaluations_by_group[group_id] = {
			"zeroth": GroupEvaluation.objects.filter(group_id=group_id, stage="zeroth").first(),
			"first": GroupEvaluation.objects.filter(group_id=group_id, stage="first").first(),
			"second": GroupEvaluation.objects.filter(group_id=group_id, stage="second").first(),
			"final": GroupEvaluation.objects.filter(group_id=group_id, stage="final").first(),
		}
		evaluation_files_by_group[group_id] = {
			"zeroth": EvaluationFile.objects.filter(group_id=group_id, stage="zeroth").first(),
			"first": EvaluationFile.objects.filter(group_id=group_id, stage="first").first(),
			"second": EvaluationFile.objects.filter(group_id=group_id, stage="second").first(),
			"final": EvaluationFile.objects.filter(group_id=group_id, stage="final").first(),
		}
		
		# Get student evaluations for this group
		group_members = GroupMember.objects.filter(group_id=group_id).select_related("user")
		student_evaluations_by_group[group_id] = {
			"first": {
				member.user.id: StudentEvaluation.objects.filter(student=member.user, stage="first").first()
				for member in group_members
			},
			"second": {
				member.user.id: StudentEvaluation.objects.filter(student=member.user, stage="second").first()
				for member in group_members
			}
		}
		for eval_obj in student_evaluations_by_group[group_id]["second"].values():
			_ensure_final_result(eval_obj)

	assigned_groups = []
	for guide_request in accepted_requests:
		members = list(GroupMember.objects.filter(group=guide_request.group).select_related("user"))
		student_eval_map = student_evaluations_by_group.get(guide_request.group_id, {})
		first_eval_map = student_eval_map.get("first", {})
		second_eval_map = student_eval_map.get("second", {})
		esestatus = {}
		for member in members:
			eval_second = second_eval_map.get(member.user.id)
			allowed, reason = _get_ese_availability(eval_second)
			esestatus[member.user.id] = {"allowed": allowed, "message": reason}
		blocked_reasons = [status["message"] for status in esestatus.values() if not status["allowed"] and status["message"]]
		assigned_groups.append({
			"group": guide_request.group,
			"sdg": sdg_by_group_id.get(guide_request.group_id),
			"project_report": report_by_group_id.get(guide_request.group_id),
			"evaluations": evaluations_by_group.get(guide_request.group_id, {}),
			"evaluation_files": evaluation_files_by_group.get(guide_request.group_id, {}),
			"student_evaluations": student_eval_map,
			"members": members,
			"first_complete": all(eval_obj and eval_obj.finalized for eval_obj in first_eval_map.values()),
			"second_complete": all(eval_obj and eval_obj.finalized for eval_obj in second_eval_map.values()),
			"ese_status": esestatus,
			"ese_ready": not blocked_reasons,
			"ese_block_reason": blocked_reasons[0] if blocked_reasons else "",
		})

	# Get pending guide requests for the requests tab
	pending_requests = GuideRequest.objects.filter(
		guide=request.user,
		status=GuideRequest.STATUS_PENDING
	).select_related("group", "group__leader", "group__leader__student_profile")

	# Get abstracts for the review abstracts tab
	all_abstracts = Abstract.objects.filter(group_id__in=group_ids).select_related("group", "group__leader").order_by("-submitted_at")
	pending_abstracts = all_abstracts.filter(guide_status=Abstract.STATUS_PENDING)
	approved_abstracts = all_abstracts.filter(guide_status=Abstract.STATUS_APPROVED)
	rejected_abstracts = all_abstracts.filter(guide_status=Abstract.STATUS_REJECTED)

	context = {
		"assigned_groups": assigned_groups,
		"pending_requests": pending_requests,
		"pending_abstracts": pending_abstracts,
		"approved_abstracts": approved_abstracts,
		"rejected_abstracts": rejected_abstracts,
		"is_dual_role": _has_dual_faculty_roles(request.user),
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
		return HttpResponseRedirect(reverse("guide_dashboard") + "#requests")

	pending_requests = GuideRequest.objects.filter(guide=request.user, status=GuideRequest.STATUS_PENDING).select_related("group", "group__leader", "group__leader__student_profile")
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

	selected_topic = Abstract.objects.filter(group=group, is_final_approved=True).order_by("-submitted_at").first()
	if selected_topic and request.method == "POST":
		messages.info(request, "Abstract already selected. New submissions are not allowed for this group.")
		return redirect("abstract_status")

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
		"selected_topic": selected_topic,
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

	elif _is_coordinator(request.user):
		has_access = CoordinatorApproval.objects.filter(
			group=abstract.group,
			coordinator=request.user,
		).exists()
		if not has_access:
			student_profile = getattr(abstract.group.leader, "student_profile", None)
			student_class = getattr(student_profile, "student_class", None)
			if student_class:
				has_access = CoordinatorAssignment.objects.filter(
					faculty=request.user,
					student_class=student_class,
				).exists()

	elif _is_hod(request.user):
		user_dept = getattr(request.user.faculty_profile, "department", None)
		group_dept = getattr(getattr(abstract.group.leader, "student_profile", None), "department", None)
		has_access = user_dept and group_dept and user_dept == group_dept

	def _role_redirect():
		if _is_student(request.user):
			return redirect("abstract_status")
		if _is_guide(request.user):
			return redirect("faculty_abstracts")
		if _is_coordinator(request.user):
			return HttpResponseRedirect(reverse("coordinator_dashboard") + "#topics")
		if _is_hod(request.user):
			return redirect("hod_dashboard")
		return redirect("dashboard")

	if not has_access:
		messages.error(request, "You don't have permission to download this abstract.")
		return _role_redirect()

	if not abstract.pdf_file:
		messages.error(request, "No PDF file available for this abstract.")
		return _role_redirect()

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

	# Check if any coordinator approval already exists for this group
	existing_approvals = CoordinatorApproval.objects.filter(group=group)
	if existing_approvals.exists():
		messages.info(request, "Coordinator approval request already exists.")
		return redirect("mini_project")

	# Get student's class
	student_profile = getattr(request.user, "student_profile", None)
	student_class = student_profile.student_class if student_profile else None
	
	if not student_class:
		messages.error(request, "You must be assigned to a class before requesting coordinator approval.")
		return redirect("mini_project")

	# Get coordinators assigned to the student's class
	coordinator_assignments = CoordinatorAssignment.objects.filter(
		student_class=student_class
	).select_related("faculty", "faculty__faculty_profile")
	
	coordinators = [assignment.faculty for assignment in coordinator_assignments if _is_coordinator(assignment.faculty)]

	if request.method == "POST":
		if not coordinators:
			messages.error(request, "No coordinators are assigned to your class. Please contact the administrator.")
			return redirect("mini_project")

		# Create approval requests for all assigned coordinators
		created_count = 0
		for coordinator in coordinators:
			CoordinatorApproval.objects.create(group=group, coordinator=coordinator)
			created_count += 1

		messages.success(request, f"Coordinator approval request sent to {created_count} coordinator(s). Any one coordinator can approve your group.")
		return redirect("mini_project")

	context = {
		"coordinators": coordinators,
		"group": group,
		"group_size": group_size,
		"student_class": student_class,
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
				.values_list("group__leader__student_profile__student_class__name", flat=True)
				.distinct()
			)
			assigned_classes_for_post = [class_name for class_name in assigned_classes_for_post if class_name]

			abstract = get_object_or_404(Abstract, id=abstract_id)
			student_profile = getattr(abstract.group.leader, "student_profile", None)
			abstract_class = student_profile.student_class.name if student_profile and student_profile.student_class else None
			if abstract_class not in assigned_classes_for_post:
				messages.error(request, "You are not authorized to review this abstract.")
				return HttpResponseRedirect(reverse("coordinator_dashboard") + "#topics")

			if abstract.guide_status != Abstract.STATUS_APPROVED or abstract.coordinator_status != Abstract.STATUS_PENDING:
				messages.error(request, "This abstract is not available for coordinator review.")
				return HttpResponseRedirect(reverse("coordinator_dashboard") + "#topics")

			if abstract_action == "approve":
				abstract.coordinator_status = Abstract.STATUS_APPROVED
				abstract.is_final_approved = True
				_apply_abstract_derived_status(abstract)
				abstract.reviewed_at = timezone.now()
				abstract.reviewed_by = request.user
				abstract.save()
				# Notify HODs in the same department
				dept = getattr(getattr(abstract.group.leader, "student_profile", None), "department", None)
				if dept:
					hod_users = User.objects.filter(faculty_profile__is_hod=True, faculty_profile__department=dept)
					for hod_user in hod_users:
						Notification.objects.create(
							recipient=hod_user,
							notif_type=Notification.NOTIF_COORDINATOR_FORWARD,
							message=f"Coordinator '{request.user.get_full_name() or request.user.username}' has forwarded abstract '{abstract.title}' for HOD review.",
							related_abstract=abstract,
						)
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
			return HttpResponseRedirect(reverse("coordinator_dashboard") + "#topics")

		approval_id = request.POST.get("approval_id")
		action = request.POST.get("action")
		if not approval_id:
			messages.error(request, "Invalid coordinator action.")
			return HttpResponseRedirect(reverse("coordinator_dashboard") + "#approvals")
		approval = get_object_or_404(CoordinatorApproval, id=approval_id, coordinator=request.user)

		if action == "approve":
			approval.status = CoordinatorApproval.STATUS_APPROVED
			approval.save()
			messages.success(request, "Group approved.")
		elif action == "reject":
			approval.status = CoordinatorApproval.STATUS_REJECTED
			approval.save()
			messages.info(request, "Group rejected.")
		return HttpResponseRedirect(reverse("coordinator_dashboard") + "#approvals")

	faculty_profile = request.user.faculty_profile
	coordinator_dept = faculty_profile.department

	assigned_classes = list(
		CoordinatorApproval.objects.filter(coordinator=request.user)
		.values_list("group__leader__student_profile__student_class__name", flat=True)
		.distinct()
	)
	assigned_classes = [class_name for class_name in assigned_classes if class_name]

	# Show ALL groups from coordinator's department for evaluation
	groups_queryset = Group.objects.filter(
		leader__student_profile__department=coordinator_dept
	)

	groups_queryset = groups_queryset.select_related(
		"leader",
		"leader__student_profile",
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
		Prefetch(
			"coordinator_approvals",
			queryset=CoordinatorApproval.objects.select_related("coordinator", "coordinator__faculty_profile").order_by("id"),
		),
	)

	sdg_by_group_id = {}
	report_by_group_id = {}
	if groups_queryset:
		sdg_by_group_id = {
			sdg.group_id: sdg
			for sdg in SustainableDevelopmentGoal.objects.filter(group_id__in=groups_queryset.values_list("id", flat=True))
		}
		report_by_group_id = {
			report.group_id: report
			for report in ProjectReport.objects.filter(group_id__in=groups_queryset.values_list("id", flat=True))
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
		project_report = report_by_group_id.get(group.id)

		# Get evaluations for this group
		group_evaluations = {
			"zeroth": GroupEvaluation.objects.filter(group=group, stage="zeroth").first(),
			"first": GroupEvaluation.objects.filter(group=group, stage="first").first(),
			"second": GroupEvaluation.objects.filter(group=group, stage="second").first(),
			"final": GroupEvaluation.objects.filter(group=group, stage="final").first(),
		}

		# Get evaluation files for this group
		evaluation_files = {
			"zeroth": EvaluationFile.objects.filter(group=group, stage="zeroth").first(),
			"first": EvaluationFile.objects.filter(group=group, stage="first").first(),
			"second": EvaluationFile.objects.filter(group=group, stage="second").first(),
			"final": EvaluationFile.objects.filter(group=group, stage="final").first(),
		}

		# Get student evaluations for this group
		group_members = GroupMember.objects.filter(group=group).select_related("user")
		student_evaluations = {
			"first": {
				member.user.id: StudentEvaluation.objects.filter(student=member.user, stage="first").first()
				for member in group_members
			},
			"second": {
				member.user.id: StudentEvaluation.objects.filter(student=member.user, stage="second").first()
				for member in group_members
			}
		}
		for eval_obj in student_evaluations.get("second", {}).values():
			_ensure_final_result(eval_obj)

		second_eval_map = student_evaluations.get("second", {})
		ese_rows = [
			{"student": member.user, "student_eval": second_eval_map.get(member.user.id)}
			for member in members
		]
		esestatus = {}
		for member in group_members:
			allowed, message = _get_ese_availability(second_eval_map.get(member.user.id))
			esestatus[member.user.id] = {"allowed": allowed, "message": message}
		blocked_reasons = [status["message"] for status in esestatus.values() if not status["allowed"] and status["message"]]

		student_profile = getattr(group.leader, "student_profile", None)
		class_name = student_profile.student_class.name if student_profile and student_profile.student_class else None
		coordinator_role = None
		if student_profile and student_profile.student_class:
			class_assignments = list(
				CoordinatorAssignment.objects.filter(student_class=student_profile.student_class)
				.select_related("faculty")
				.order_by("id")
			)
			for idx, assignment in enumerate(class_assignments, 1):
				if assignment.faculty_id == request.user.id:
					coordinator_role = idx
					break
		
		# Get all coordinator approvals for this group
		coordinator_approvals = list(group.coordinator_approvals.all())
		# Check if any coordinator has approved
		is_coordinator_approved = any(approval.status == CoordinatorApproval.STATUS_APPROVED for approval in coordinator_approvals)
		coordinator_approval = None
		if is_coordinator_approved:
			coordinator_approval = next(
				(approval for approval in coordinator_approvals if approval.status == CoordinatorApproval.STATUS_APPROVED),
				None,
			)
		elif coordinator_approvals:
			coordinator_approval = coordinator_approvals[0]
		
		group_details.append({
			"group": group,
			"class_name": class_name,
			"department": getattr(student_profile, "department", None),
			"leader_profile": getattr(group.leader, "student_profile", None),
			"members": members,
			"group_size": len(members),
			"coordinator_role": coordinator_role,
			"coordinator_approval": coordinator_approval,
			"coordinator_approvals": coordinator_approvals,
			"is_coordinator_approved": is_coordinator_approved,
			"latest_guide_request": latest_guide_request,
			"assigned_guide": assigned_guide,
			"approved_abstract": approved_abstract,
			"sdg": sdg_entry,
			"project_report": project_report,
			"evaluations": group_evaluations,
			"evaluation_files": evaluation_files,
			"student_evaluations": student_evaluations,
			# Add flags for evaluation completion status
			"first_complete": all(
				eval_obj and eval_obj.finalized
				for eval_obj in student_evaluations.get("first", {}).values()
			),
			"second_complete": all(
				eval_obj and eval_obj.finalized
				for eval_obj in student_evaluations.get("second", {}).values()
			),
			"ese_status": esestatus,
			"ese_ready": not blocked_reasons,
			"ese_block_reason": blocked_reasons[0] if blocked_reasons else "",
			"ese_data": ese_rows,
		})

	pending_approvals = CoordinatorApproval.objects.filter(
		coordinator=request.user,
		status=CoordinatorApproval.STATUS_PENDING,
	).select_related("group", "group__leader")

	coordinator_pending_abstracts = Abstract.objects.filter(
		guide_status=Abstract.STATUS_APPROVED,
		coordinator_status=Abstract.STATUS_PENDING,
		group__leader__student_profile__student_class__name__in=assigned_classes,
	).select_related("group", "group__leader").order_by("-submitted_at")

	context = {
		"pending_approvals": pending_approvals,
		"faculty_profile": faculty_profile,
		"assigned_classes": assigned_classes,
		"group_details": group_details,
		"coordinator_pending_abstracts": coordinator_pending_abstracts,
		"is_dual_role": _has_dual_faculty_roles(request.user),
	}
	return render(request, "coordinator_dashboard.html", context)


@login_required
def profile(request):
	context = {
		"is_student": _is_student(request.user),
		"is_guide": _is_guide(request.user),
		"is_coordinator": _is_coordinator(request.user),
		"is_hod": _is_hod(request.user),
	}
	
	if _is_student(request.user):
		context["student_profile"] = request.user.student_profile
		# Fetch the student's group and its SDG submission
		group = _get_group_for_user(request.user)
		if group:
			sdg_submission = SustainableDevelopmentGoal.objects.filter(group=group).first()
			context["student_group"] = group
			context["sdg_submission"] = sdg_submission
			
			# Create a list of selected SDG goals with their names
			sdg_names = {
				'1': 'No Poverty',
				'2': 'Zero Hunger',
				'3': 'Good Health and Well-being',
				'4': 'Quality Education',
				'5': 'Gender Equality',
				'6': 'Clean Water and Sanitation',
				'7': 'Affordable and Clean Energy',
				'8': 'Decent Work and Economic Growth',
				'9': 'Industry, Innovation and Infrastructure',
				'10': 'Reduced Inequalities',
				'11': 'Sustainable Cities and Communities',
				'12': 'Responsible Consumption and Production',
				'13': 'Climate Action',
				'14': 'Life Below Water',
				'15': 'Life on Land',
				'16': 'Peace, Justice and Strong Institutions',
				'17': 'Partnerships for the Goals'
			}
			
			selected_sdgs = []
			if sdg_submission:
				for i in range(1, 6):
					sdg_field_value = getattr(sdg_submission, f"sdg{i}", "")
					if sdg_field_value:
						selected_sdgs.append({
							'number': sdg_field_value,
							'name': sdg_names.get(sdg_field_value, f'SDG {sdg_field_value}')
						})
			context["selected_sdgs"] = selected_sdgs
	elif hasattr(request.user, "faculty_profile"):
		context["faculty_profile"] = request.user.faculty_profile
	
	return render(request, "profile.html", context)


@login_required
def hod_dashboard(request):
	if not _is_hod(request.user):
		messages.error(request, "Only HOD can access this page.")
		return redirect("dashboard")

	hod_profile = request.user.faculty_profile
	dept = hod_profile.department

	# Handle HOD actions
	if request.method == "POST":
		abstract_id = request.POST.get("abstract_id")
		action = request.POST.get("action")

		if abstract_id and action:
			abstract = get_object_or_404(Abstract, id=abstract_id)
			# Verify the abstract belongs to HOD's department
			abstract_dept = getattr(getattr(abstract.group.leader, "student_profile", None), "department", None)
			if abstract_dept != dept:
				messages.error(request, "You are not authorized to manage this project.")
				return redirect("hod_dashboard")

			if action == "verify_compliance":
				abstract.hod_status = Abstract.STATUS_APPROVED
				abstract.save()
				# Notify HOD (self) – can also notify guide/coordinator
				Notification.objects.create(
					recipient=request.user,
					notif_type=Notification.NOTIF_PRESENTATION_READY,
					message=f"Academic compliance verified for '{abstract.title}'. Project is ready for presentation approval.",
					related_abstract=abstract,
				)
				messages.success(request, f"Academic compliance verified for '{abstract.title}'.")

			elif action == "approve_presentation":
				if abstract.hod_status != Abstract.STATUS_APPROVED:
					messages.error(request, "Academic compliance must be verified before approving presentation.")
					return redirect("hod_dashboard")
				abstract.presentation_approved = True
				abstract.save()
				Notification.objects.create(
					recipient=request.user,
					notif_type=Notification.NOTIF_FINAL_APPROVAL,
					message=f"Presentation approved for '{abstract.title}'. Final project approval is now pending.",
					related_abstract=abstract,
				)
				messages.success(request, f"Final presentation approved for '{abstract.title}'.")

			elif action == "approve_final":
				if not abstract.presentation_approved:
					messages.error(request, "Presentation must be approved before final project approval.")
					return redirect("hod_dashboard")
				abstract.final_approved = True
				abstract.save()
				messages.success(request, f"Final project approved for '{abstract.title}'.")

			elif action == "reject_hod":
				abstract.hod_status = Abstract.STATUS_REJECTED
				abstract.save()
				messages.info(request, f"Project '{abstract.title}' rejected at HOD level.")

			return redirect("hod_dashboard")

	# HOD sees coordinator-approved abstracts in their department only
	forwarded_abstracts = Abstract.objects.filter(
		coordinator_status=Abstract.STATUS_APPROVED,
		group__leader__student_profile__department=dept,
	).select_related("group", "group__leader", "reviewed_by").order_by("-reviewed_at")

	# Notifications for this HOD
	notifications = Notification.objects.filter(recipient=request.user, is_read=False).order_by("-created_at")
	unread_count = notifications.count()

	# Mark notifications as read on visit
	notifications.update(is_read=True)

	all_notifications = Notification.objects.filter(recipient=request.user).order_by("-created_at")[:20]

	context = {
		"hod_profile": hod_profile,
		"department": dept,
		"forwarded_abstracts": forwarded_abstracts,
		"notifications": all_notifications,
		"unread_count": unread_count,
		"compliance_count": forwarded_abstracts.filter(hod_status=Abstract.STATUS_APPROVED).count(),
		"presentation_count": forwarded_abstracts.filter(presentation_approved=True).count(),
		"final_count": forwarded_abstracts.filter(final_approved=True).count(),
	}
	return render(request, "hod_dashboard.html", context)


@login_required
def submit_guide_evaluation(request, group_id, stage):
	"""Handle guide evaluation submission."""
	if not _is_guide(request.user):
		messages.error(request, "Only guides can submit evaluations.")
		return redirect("dashboard")

	group = get_object_or_404(Group, id=group_id)
	
	# Verify the guide is assigned to this group
	if not GuideRequest.objects.filter(group=group, guide=request.user, status=GuideRequest.STATUS_ACCEPTED).exists():
		messages.error(request, "You are not the guide for this group.")
		return redirect("guide_dashboard")

	if request.method == "POST":
		# Get or create evaluation
		evaluation, created = GroupEvaluation.objects.get_or_create(
			group=group,
			stage=stage
		)

		# Check if already submitted
		if evaluation.guide_submitted:
			messages.warning(request, "You have already submitted this evaluation.")
			return redirect("guide_dashboard")

		# Update evaluation fields
		evaluation.guide_technical_exposure = request.POST.get("technical_exposure") == "on"
		evaluation.guide_socially_relevant = request.POST.get("socially_relevant") == "on"
		evaluation.guide_product_based = request.POST.get("product_based") == "on"
		evaluation.guide_research_oriented = request.POST.get("research_oriented") == "on"
		evaluation.guide_review = request.POST.get("review", "").strip()
		evaluation.guide_submitted = True
		evaluation.save()

		messages.success(request, f"{evaluation.get_stage_display()} submitted successfully!")
		return redirect("guide_dashboard")

	return redirect("guide_dashboard")


@login_required
def submit_coordinator_evaluation(request, group_id, stage):
	"""Handle coordinator evaluation submission."""
	if not _is_coordinator(request.user):
		messages.error(request, "Only coordinators can submit evaluations.")
		return redirect("dashboard")

	# Handle dual role
	role_redirect = _ensure_active_role_for_dual_faculty(request, "coordinator")
	if role_redirect:
		return role_redirect

	group = get_object_or_404(Group, id=group_id)
	
	# Get student class and coordinator assignments
	student_profile = getattr(group.leader, "student_profile", None)
	if not student_profile or not student_profile.student_class:
		messages.error(request, "Group leader's class is not assigned.")
		return redirect("coordinator_dashboard")
	
	student_class = student_profile.student_class
	coordinator_assignments = list(
		CoordinatorAssignment.objects.filter(student_class=student_class)
		.select_related('faculty')
		.order_by('id')
	)
	
	if not coordinator_assignments:
		messages.error(request, "No coordinators assigned to this class.")
		return redirect("coordinator_dashboard")
	
	# Determine which coordinator is submitting (coordinator1 or coordinator2)
	coordinator_role = None
	for idx, assignment in enumerate(coordinator_assignments, 1):
		if assignment.faculty == request.user:
			coordinator_role = idx
			break
	
	if not coordinator_role:
		messages.error(request, "You are not assigned as a coordinator for this class.")
		return redirect("coordinator_dashboard")

	if request.method == "POST":
		# Get or create evaluation
		evaluation, created = GroupEvaluation.objects.get_or_create(
			group=group,
			stage=stage
		)

		# Check if this coordinator already submitted
		if coordinator_role == 1 and evaluation.coordinator1_submitted:
			messages.warning(request, "You have already submitted this evaluation.")
			return redirect("coordinator_dashboard")
		elif coordinator_role == 2 and evaluation.coordinator2_submitted:
			messages.warning(request, "You have already submitted this evaluation.")
			return redirect("coordinator_dashboard")

		# Update evaluation fields based on coordinator role
		if coordinator_role == 1:
			evaluation.coordinator1_technical_exposure = request.POST.get("technical_exposure") == "on"
			evaluation.coordinator1_socially_relevant = request.POST.get("socially_relevant") == "on"
			evaluation.coordinator1_product_based = request.POST.get("product_based") == "on"
			evaluation.coordinator1_research_oriented = request.POST.get("research_oriented") == "on"
			evaluation.coordinator1_review = request.POST.get("review", "").strip()
			evaluation.coordinator1_submitted = True
		else:  # coordinator_role == 2
			evaluation.coordinator2_technical_exposure = request.POST.get("technical_exposure") == "on"
			evaluation.coordinator2_socially_relevant = request.POST.get("socially_relevant") == "on"
			evaluation.coordinator2_product_based = request.POST.get("product_based") == "on"
			evaluation.coordinator2_research_oriented = request.POST.get("research_oriented") == "on"
			evaluation.coordinator2_review = request.POST.get("review", "").strip()
			evaluation.coordinator2_submitted = True
		
		# Also update legacy coordinator fields for backward compatibility
		evaluation.coordinator_technical_exposure = request.POST.get("technical_exposure") == "on"
		evaluation.coordinator_socially_relevant = request.POST.get("socially_relevant") == "on"
		evaluation.coordinator_product_based = request.POST.get("product_based") == "on"
		evaluation.coordinator_research_oriented = request.POST.get("research_oriented") == "on"
		evaluation.coordinator_review = request.POST.get("review", "").strip()
		evaluation.coordinator_submitted = True
		
		evaluation.save()

		messages.success(request, f"{evaluation.get_stage_display()} submitted successfully!")
		return redirect("coordinator_dashboard")

	return redirect("coordinator_dashboard")


@login_required
def upload_evaluation_file(request, stage):
	"""Handle file upload for group evaluations."""
	if not _is_student(request.user):
		messages.error(request, "Only students can upload evaluation files.")
		return redirect("dashboard")

	group = _get_group_for_user(request.user)
	if not group:
		messages.error(request, "You must be in a group to upload files.")
		return redirect("mini_project")

	if request.method == "POST" and request.FILES.get("file"):
		uploaded_file = request.FILES["file"]
		
		# Validate file type
		allowed_extensions = ['.pdf', '.ppt', '.pptx', '.doc', '.docx']
		file_ext = '.' + uploaded_file.name.split('.')[-1].lower()
		if file_ext not in allowed_extensions:
			messages.error(request, f"Invalid file type. Allowed: {', '.join(allowed_extensions)}")
			return redirect("dashboard")

		# Validate file size (max 10MB)
		if uploaded_file.size > 10 * 1024 * 1024:
			messages.error(request, "File size must be less than 10MB.")
			return redirect("dashboard")

		# Delete existing file for this stage if exists
		EvaluationFile.objects.filter(group=group, stage=stage).delete()

		# Save new file
		EvaluationFile.objects.create(
			group=group,
			stage=stage,
			file_data=uploaded_file.read(),
			file_name=uploaded_file.name,
			file_size=uploaded_file.size,
			file_type=uploaded_file.content_type,
			uploaded_by=request.user,
		)

		messages.success(request, f"File uploaded successfully for {stage} evaluation!")
		return redirect("dashboard")

	return redirect("dashboard")


@login_required
def download_evaluation_file(request, file_id):
	"""Download evaluation file."""
	eval_file = get_object_or_404(EvaluationFile, id=file_id)
	
	# Check authorization
	user = request.user
	is_authorized = False
	
	# Students in the group can download
	if _is_student(user) and _get_group_for_user(user) == eval_file.group:
		is_authorized = True
	
	# Guide of the group can download
	if _is_guide(user) and GuideRequest.objects.filter(
		group=eval_file.group, 
		guide=user, 
		status=GuideRequest.STATUS_ACCEPTED
	).exists():
		is_authorized = True
	
	# Coordinator can download if same department
	if _is_coordinator(user):
		coordinator_dept = user.faculty_profile.department
		group_dept = getattr(getattr(eval_file.group.leader, "student_profile", None), "department", None)
		if coordinator_dept == group_dept:
			is_authorized = True
	
	# HOD can download if same department
	if _is_hod(user):
		hod_dept = user.faculty_profile.department
		group_dept = getattr(getattr(eval_file.group.leader, "student_profile", None), "department", None)
		if hod_dept == group_dept:
			is_authorized = True
	
	if not is_authorized:
		messages.error(request, "You are not authorized to download this file.")
		return redirect("dashboard")
	
	response = HttpResponse(eval_file.file_data, content_type=eval_file.file_type)
	response['Content-Disposition'] = f'attachment; filename="{eval_file.file_name}"'
	return response


def _update_finalized_status(group, stage):
	"""Update finalized status for all students in a group for a given stage."""
	evaluations = StudentEvaluation.objects.filter(group=group, stage=stage)
	for evaluation in evaluations:
		if evaluation.guide_submitted and evaluation.coordinator1_submitted and evaluation.coordinator2_submitted:
			evaluation.finalized = True
			evaluation.save(update_fields=['finalized'])


def _calculate_cie(second_eval):
	"""Compute and save CIE totals on a second-stage StudentEvaluation record."""
	first_eval = StudentEvaluation.objects.filter(
		student=second_eval.student, stage="first"
	).first()
	if not first_eval:
		return

	committee_raw_total = (
		(first_eval.guide_total or 0)
		+ (first_eval.coordinator1_total or 0)
		+ (first_eval.coordinator2_total or 0)
		+ (second_eval.guide_total or 0)
		+ (second_eval.coordinator1_total or 0)
		+ (second_eval.coordinator2_total or 0)
	)
	committee_mark = round((committee_raw_total / 240) * 40)

	guide_mark = second_eval.final_guide_mark or 0
	attendance_mark = second_eval.attendance_marks or 0

	try:
		report_mark = second_eval.group.project_report.final_mark or 0
	except Exception:
		return

	cie_total = committee_mark + guide_mark + attendance_mark + report_mark

	second_eval.committee_raw_total = committee_raw_total
	second_eval.committee_mark = committee_mark
	second_eval.cie_total = cie_total
	second_eval.cie_calculated = True
	second_eval.cie_calculated_at = timezone.now()
	second_eval.save(update_fields=[
		"committee_raw_total",
		"committee_mark",
		"cie_total",
		"cie_calculated",
		"cie_calculated_at",
	])
	if second_eval.ese_completed:
		calculate_final_result(second_eval)


def _try_calculate_cie(second_eval):
	"""Calculate CIE for a student if all required components are complete."""
	if not (
		second_eval.second_eval_completed
		and second_eval.final_guide_submitted
		and second_eval.attendance_submitted
	):
		return
	try:
		report = second_eval.group.project_report
	except Exception:
		return
	if report is None or report.final_mark is None:
		return
	_calculate_cie(second_eval)


@login_required
def submit_attendance_marks(request, group_id):
	"""Allow a coordinator to submit or update attendance marks for all students in a group."""
	if not _is_coordinator(request.user):
		return HttpResponseForbidden("Only coordinators can submit attendance marks.")

	role_redirect = _ensure_active_role_for_dual_faculty(request, "coordinator")
	if role_redirect:
		return role_redirect

	if request.method != "POST":
		return redirect("coordinator_dashboard")

	group = get_object_or_404(Group, id=group_id)

	student_profile = getattr(group.leader, "student_profile", None)
	if not student_profile or not student_profile.student_class:
		return HttpResponseForbidden("Group leader's class is not assigned.")

	coordinator_assigned = CoordinatorAssignment.objects.filter(
		student_class=student_profile.student_class,
		faculty=request.user,
	).exists()
	if not coordinator_assigned:
		return HttpResponseForbidden("You are not assigned as a coordinator for this class.")

	members = list(GroupMember.objects.filter(group=group).select_related("user").order_by("id"))
	evaluations = {
		evaluation.student_id: evaluation
		for evaluation in StudentEvaluation.objects.filter(group=group, stage="second").select_related(
			"student",
			"attendance_submitted_by",
		)
	}

	missing_evaluations = [member.user.username for member in members if member.user.id not in evaluations]
	if missing_evaluations:
		messages.error(request, "Second evaluation record is missing for: " + ", ".join(missing_evaluations))
		return redirect("coordinator_dashboard")

	incomplete_students = [
		evaluation.student.username
		for evaluation in evaluations.values()
		if not evaluation.second_eval_completed
	]
	if incomplete_students:
		messages.error(request, "Attendance marks can be entered only after Second Evaluation is completed for all students.")
		return redirect("coordinator_dashboard")

	validated_marks = {}
	for member in members:
		field_name = f"attendance_{member.user.id}"
		marks_raw = request.POST.get(field_name, "").strip()
		if marks_raw == "":
			messages.error(request, "Fill attendance marks for all students before submitting.")
			return redirect("coordinator_dashboard")
		try:
			attendance_marks = int(marks_raw)
		except (TypeError, ValueError):
			messages.error(request, f"Attendance marks for {member.user.username} must be a whole number between 0 and 10.")
			return redirect("coordinator_dashboard")
		if attendance_marks < 0 or attendance_marks > 10:
			messages.error(request, f"Attendance marks for {member.user.username} must be between 0 and 10.")
			return redirect("coordinator_dashboard")
		validated_marks[member.user.id] = attendance_marks

	submitted_at = timezone.now()
	for member in members:
		evaluation = evaluations[member.user.id]
		evaluation.attendance_marks = validated_marks[member.user.id]
		evaluation.attendance_submitted = True
		evaluation.attendance_submitted_by = request.user
		evaluation.attendance_submitted_at = submitted_at
		evaluation.save(update_fields=[
			"attendance_marks",
			"attendance_submitted",
			"attendance_submitted_by",
			"attendance_submitted_at",
		])

	# Attempt CIE calculation now that attendance is saved
	for evaluation in evaluations.values():
		_try_calculate_cie(evaluation)

	messages.success(request, "Attendance marks saved successfully for all students.")
	return redirect("coordinator_dashboard")


@login_required
def submit_coordinator_ese(request, group_id):
	"""Allow coordinators to record End Semester Evaluation (ESE) marks for students."""
	if not _is_coordinator(request.user):
		return HttpResponseForbidden("Only coordinators can submit ESE marks.")

	role_redirect = _ensure_active_role_for_dual_faculty(request, "coordinator")
	if role_redirect:
		return role_redirect

	if request.method != "POST":
		return redirect("coordinator_dashboard")

	group = get_object_or_404(Group, id=group_id)
	student_profile = getattr(group.leader, "student_profile", None)
	if not student_profile or not student_profile.student_class:
		return HttpResponseForbidden("Group leader's class is not assigned.")

	assignments = list(
		CoordinatorAssignment.objects.filter(student_class=student_profile.student_class)
		.select_related("faculty")
		.order_by("id")
	)
	if not assignments:
		messages.error(request, "No coordinators assigned to this class.")
		return redirect("coordinator_dashboard")

	coordinator_role = None
	for idx, assignment in enumerate(assignments, 1):
		if assignment.faculty == request.user:
			coordinator_role = idx
			break
	if not coordinator_role:
		messages.error(request, "You are not assigned as a coordinator for this class.")
		return redirect("coordinator_dashboard")

	members = list(GroupMember.objects.filter(group=group).select_related("user").order_by("id"))
	second_stage_evals = {
		member.user.id: StudentEvaluation.objects.filter(student=member.user, group=group, stage="second").first()
		for member in members
	}

	missing = [member.user.username for member in members if not second_stage_evals.get(member.user.id)]
	if missing:
		messages.error(request, "Second Evaluation record is missing for: " + ", ".join(missing))
		return redirect("coordinator_dashboard")

	allowed_students = {}
	for member in members:
		allowed, message = _get_ese_availability(second_stage_evals[member.user.id])
		if allowed:
			allowed_students[member.user.id] = True
		else:
			allowed_students[member.user.id] = False
	if not any(allowed_students.values()):
		messages.error(request, "ESE marks can be entered only after all prerequisites are complete for at least one student.")
		return redirect("coordinator_dashboard")

	criteria = {
		"presentation": {"max": 30, "label": "Presentation (30)"},
		"demo": {"max": 20, "label": "Demonstration (20)"},
		"viva": {"max": 25, "label": "Viva (25)"},
	}

	validated_scores = {}
	for member in members:
		if not allowed_students[member.user.id]:
			continue
		base_prefix = f"student_{member.user.id}_"
		req_prefix = f"{base_prefix}ese_"
		scores = {}
		for field_key, spec in criteria.items():
			max_score = spec["max"]
			label = spec["label"]
			raw_value = request.POST.get(f"{req_prefix}{field_key}")
			if raw_value is None:
				raw_value = request.POST.get(f"{base_prefix}{field_key}")
			raw_value = (raw_value or "").strip()
			if raw_value == "":
				messages.error(request, f"{label} for {member.user.username} is required.")
				return redirect("coordinator_dashboard")
			try:
				score = int(raw_value)
			except (TypeError, ValueError):
				messages.error(request, f"{label} for {member.user.username} must be a whole number between 0 and {max_score}.")
				return redirect("coordinator_dashboard")
			if score < 0 or score > max_score:
				messages.error(request, f"{label} for {member.user.username} must be between 0 and {max_score}.")
				return redirect("coordinator_dashboard")
			scores[field_key] = score
		validated_scores[member.user.id] = scores

	for member in members:
		if not allowed_students[member.user.id]:
			continue
		evaluation = second_stage_evals[member.user.id]
		scores = validated_scores[member.user.id]
		coord_fields = []
		total = sum(scores.values())
		if coordinator_role == 1:
			evaluation.ese_coord1_presentation = scores["presentation"]
			evaluation.ese_coord1_demo = scores["demo"]
			evaluation.ese_coord1_viva = scores["viva"]
			evaluation.ese_coord1_submitted = True
			coord_fields.extend([
				"ese_coord1_presentation",
				"ese_coord1_demo",
				"ese_coord1_viva",
				"ese_coord1_submitted",
			])
		else:
			evaluation.ese_coord2_presentation = scores["presentation"]
			evaluation.ese_coord2_demo = scores["demo"]
			evaluation.ese_coord2_viva = scores["viva"]
			evaluation.ese_coord2_submitted = True
			coord_fields.extend([
				"ese_coord2_presentation",
				"ese_coord2_demo",
				"ese_coord2_viva",
				"ese_coord2_submitted",
			])

		completed = _update_ese_completion(evaluation)
		coord_fields.extend([
			"ese_final",
			"ese_completed",
			"ese_completed_at",
			"final_total",
			"final_percentage",
			"final_grade",
			"result_calculated",
		])
		evaluation.save(update_fields=coord_fields)
		if completed:
			calculate_final_result(evaluation)

	messages.success(request, "ESE marks submitted successfully.")
	return redirect("coordinator_dashboard")


@login_required
def submit_guide_ese(request, group_id):
	"""Allow the assigned guide to submit their ESE marks for all members in a group."""
	if not _is_guide(request.user):
		messages.error(request, "Only guides can submit ESE marks.")
		return redirect("dashboard")

	if request.method != "POST":
		return redirect("guide_dashboard")

	group = get_object_or_404(Group, id=group_id)

	if not GuideRequest.objects.filter(group=group, guide=request.user, status=GuideRequest.STATUS_ACCEPTED).exists():
		messages.error(request, "You are not the assigned guide for this group.")
		return redirect("guide_dashboard")

	if not _is_stage_completed_for_group(group, "second"):
		messages.error(request, "ESE entry is available only after the Second Evaluation is completed for the group.")
		return redirect("guide_dashboard")

	members = list(GroupMember.objects.filter(group=group).select_related("user").order_by("id"))
	second_stage_evals = {
		member.user.id: StudentEvaluation.objects.filter(student=member.user, group=group, stage="second").first()
		for member in members
	}

	missing_records = [member.user.username for member in members if not second_stage_evals.get(member.user.id)]
	if missing_records:
		messages.error(request, "Second Evaluation data is missing for: " + ", ".join(missing_records))
		return redirect("guide_dashboard")

	not_ready = {}
	for member in members:
		eval_record = second_stage_evals[member.user.id]
		allowed, message = _get_ese_availability(eval_record)
		if not allowed:
			not_ready[member.user.username] = message or "Prerequisites for ESE are not met."

	if not_ready:
		first_user, reason = next(iter(not_ready.items()))
		messages.error(request, f"ESE cannot be submitted because {first_user}: {reason}")
		return redirect("guide_dashboard")

	criteria = {
		"presentation": ("ese_guide_presentation", 30, "Presentation (30)"),
		"demo": ("ese_guide_demo", 20, "Demonstration (20)"),
		"viva": ("ese_guide_viva", 25, "Viva (25)"),
	}

	now = timezone.now()
	for member in members:
		eval_record = second_stage_evals[member.user.id]
		prefix = f"student_{member.user.id}_ese_"
		validated_scores = {}
		for slug, (model_field, max_score, label) in criteria.items():
			raw_value = request.POST.get(f"{prefix}{slug}", "").strip()
			if raw_value == "":
				messages.error(request, f"{label} mark for {member.user.username} is required.")
				return redirect("guide_dashboard")
			try:
				score = int(raw_value)
			except (TypeError, ValueError):
				messages.error(request, f"{label} mark for {member.user.username} must be a whole number between 0 and {max_score}.")
				return redirect("guide_dashboard")
			if score < 0 or score > max_score:
				messages.error(request, f"{label} mark for {member.user.username} must be between 0 and {max_score}.")
				return redirect("guide_dashboard")
			validated_scores[model_field] = score

		for field_name, score in validated_scores.items():
			setattr(eval_record, field_name, score)
		eval_record.ese_guide_submitted = True
		eval_record.ese_guide_submitted_at = now
		completed = _update_ese_completion(eval_record)
		update_fields = [
			"ese_guide_presentation",
			"ese_guide_demo",
			"ese_guide_viva",
			"ese_guide_submitted",
			"ese_guide_submitted_at",
			"ese_final",
			"ese_completed",
			"ese_completed_at",
			"final_total",
			"final_percentage",
			"final_grade",
			"result_calculated",
		]
		eval_record.save(update_fields=update_fields)
		if completed:
			calculate_final_result(eval_record)

	messages.success(request, "Guide ESE marks submitted successfully.")
	return redirect("guide_dashboard")


@login_required
def submit_guide_student_evaluation(request, group_id, stage):
	"""Handle guide submission for student evaluations (First/Second)."""
	if not _is_guide(request.user):
		messages.error(request, "Only guides can submit evaluations.")
		return redirect("dashboard")

	group = get_object_or_404(Group, id=group_id)
	
	# Verify the guide is assigned to this group
	if not GuideRequest.objects.filter(group=group, guide=request.user, status=GuideRequest.STATUS_ACCEPTED).exists():
		messages.error(request, "You are not the guide for this group.")
		return redirect("guide_dashboard")

	if request.method == "POST":
		# Get all group members
		members = GroupMember.objects.filter(group=group).select_related("user")
		
		# Process marks for each student
		for member in members:
			student = member.user
			evaluation, created = StudentEvaluation.objects.get_or_create(
				student=student,
				group=group,
				stage=stage
			)

			# Get marks from POST data (prefixed with student_id) - allow editing
			prefix = f"student_{student.id}_"
			evaluation.guide_topic = int(request.POST.get(f"{prefix}topic", 0) or 0)
			evaluation.guide_planning = int(request.POST.get(f"{prefix}planning", 0) or 0)
			evaluation.guide_scalability = int(request.POST.get(f"{prefix}scalability", 0) or 0)
			evaluation.guide_novelty = int(request.POST.get(f"{prefix}novelty", 0) or 0)
			evaluation.guide_task_distribution = int(request.POST.get(f"{prefix}task_distribution", 0) or 0)
			evaluation.guide_schedule = int(request.POST.get(f"{prefix}schedule", 0) or 0)
			evaluation.guide_interim = int(request.POST.get(f"{prefix}interim", 0) or 0)
			evaluation.guide_presentation = int(request.POST.get(f"{prefix}presentation", 0) or 0)
			evaluation.guide_viva = int(request.POST.get(f"{prefix}viva", 0) or 0)
			evaluation.guide_submitted = True
			# Finalize only if guide and both coordinators have submitted
			if evaluation.guide_submitted and evaluation.coordinator1_submitted and evaluation.coordinator2_submitted:
				evaluation.finalized = True
			evaluation.save()

		# Save presentation review (group-level)
		presentation_review = request.POST.get('presentation_review', '').strip()
		group_eval, created = GroupEvaluation.objects.get_or_create(
			group=group,
			stage=stage
		)
		group_eval.guide_review = presentation_review
		group_eval.save()

		# Ensure all students have finalized status updated
		_update_finalized_status(group, stage)

		# Attempt CIE calculation for all second-stage records in this group
		if stage == "second":
			for member in GroupMember.objects.filter(group=group).select_related("user"):
				second_eval = StudentEvaluation.objects.filter(student=member.user, group=group, stage="second").first()
				if second_eval:
					_try_calculate_cie(second_eval)

		messages.success(request, f"{stage.capitalize()} Evaluation submitted successfully for all students!")
		return redirect("guide_dashboard")

	return redirect("guide_dashboard")


@login_required
def submit_final_guide_evaluation(request, group_id):
	"""Guide submits/updates final guide evaluation for all group members at once."""
	if not _is_guide(request.user):
		messages.error(request, "Only guides can submit final guide evaluation.")
		return redirect("dashboard")

	if request.method != "POST":
		return redirect("guide_dashboard")

	group = get_object_or_404(Group, id=group_id)

	if not GuideRequest.objects.filter(
		group=group,
		guide=request.user,
		status=GuideRequest.STATUS_ACCEPTED,
	).exists():
		messages.error(request, "You are not the guide for this group.")
		return redirect("guide_dashboard")

	if not _is_stage_completed_for_group(group, "second"):
		messages.error(request, "Final Guide Evaluation is available only after Second Evaluation is completed.")
		return redirect("guide_dashboard")

	criteria_spec = {
		"final_guide_topic": ("Topic Identification", 5),
		"final_guide_planning": ("Planning", 5),
		"final_guide_scale": ("Scalability", 2),
		"final_guide_novelty": ("Novelty", 5),
		"final_guide_task": ("Task Distribution", 5),
		"final_guide_schedule": ("Schedule Adherence", 3),
		"final_guide_interim": ("Interim Results", 5),
		"final_guide_presentation": ("Presentation", 5),
		"final_guide_viva": ("Viva", 5),
	}

	members = GroupMember.objects.filter(group=group).select_related("user")
	now = timezone.now()

	for member in members:
		student = member.user
		student_eval = StudentEvaluation.objects.filter(student=student, group=group, stage="second").first()
		if not student_eval:
			continue

		prefix = f"student_{student.id}_"
		validated_scores = {}
		error_occurred = False
		for field_name, (label, max_score) in criteria_spec.items():
			raw_value = request.POST.get(f"{prefix}{field_name}", "").strip()
			if raw_value == "":
				messages.error(request, f"{label} mark for {student.username} is required.")
				error_occurred = True
				break
			try:
				score = int(raw_value)
			except (TypeError, ValueError):
				messages.error(request, f"{label} mark for {student.username} must be a whole number between 0 and {max_score}.")
				error_occurred = True
				break
			if score < 0 or score > max_score:
				messages.error(request, f"{label} mark for {student.username} must be between 0 and {max_score}.")
				error_occurred = True
				break
			validated_scores[field_name] = score

		if error_occurred:
			return redirect("guide_dashboard")

		final_guide_total = sum(validated_scores.values())
		final_guide_mark = int(round((final_guide_total / 40) * 15))

		for field_name, score in validated_scores.items():
			setattr(student_eval, field_name, score)
		student_eval.final_guide_total = final_guide_total
		student_eval.final_guide_raw = final_guide_total
		student_eval.final_guide_mark = final_guide_mark
		student_eval.final_guide_submitted = True
		student_eval.final_guide_submitted_at = now
		student_eval.save(update_fields=[
			"final_guide_topic",
			"final_guide_planning",
			"final_guide_scale",
			"final_guide_novelty",
			"final_guide_task",
			"final_guide_schedule",
			"final_guide_interim",
			"final_guide_presentation",
			"final_guide_viva",
			"final_guide_total",
			"final_guide_raw",
			"final_guide_mark",
			"final_guide_submitted",
			"final_guide_submitted_at",
		])
		_try_calculate_cie(student_eval)

	messages.success(request, "Final Guide Evaluation submitted for all students.")
	return redirect("guide_dashboard")


@login_required
def submit_coordinator_student_evaluation(request, group_id, stage):
	"""Handle coordinator submission for student evaluations (First/Second)."""
	if not _is_coordinator(request.user):
		messages.error(request, "Only coordinators can submit evaluations.")
		return redirect("dashboard")

	# Handle dual role
	role_redirect = _ensure_active_role_for_dual_faculty(request, "coordinator")
	if role_redirect:
		return role_redirect

	group = get_object_or_404(Group, id=group_id)
	
	# Get student class and coordinator assignments
	student_profile = getattr(group.leader, "student_profile", None)
	if not student_profile or not student_profile.student_class:
		messages.error(request, "Group leader's class is not assigned.")
		return redirect("coordinator_dashboard")
	
	student_class = student_profile.student_class
	coordinator_assignments = list(
		CoordinatorAssignment.objects.filter(student_class=student_class)
		.select_related('faculty')
		.order_by('id')
	)
	
	if not coordinator_assignments:
		messages.error(request, "No coordinators assigned to this class.")
		return redirect("coordinator_dashboard")
	
	# Determine which coordinator is submitting (coordinator1 or coordinator2)
	coordinator_role = None
	for idx, assignment in enumerate(coordinator_assignments, 1):
		if assignment.faculty == request.user:
			coordinator_role = idx
			break
	
	if not coordinator_role:
		messages.error(request, "You are not assigned as a coordinator for this class.")
		return redirect("coordinator_dashboard")

	if request.method == "POST":
		# Get all group members
		members = GroupMember.objects.filter(group=group).select_related("user")
		
		# Process marks for each student
		for member in members:
			student = member.user
			evaluation, created = StudentEvaluation.objects.get_or_create(
				student=student,
				group=group,
				stage=stage
			)

			# Get marks from POST data (prefixed with student_id)
			prefix = f"student_{student.id}_"
			
			# Update fields based on coordinator role
			if coordinator_role == 1:
				evaluation.coordinator1_topic = int(request.POST.get(f"{prefix}topic", 0) or 0)
				evaluation.coordinator1_planning = int(request.POST.get(f"{prefix}planning", 0) or 0)
				evaluation.coordinator1_scalability = int(request.POST.get(f"{prefix}scalability", 0) or 0)
				evaluation.coordinator1_novelty = int(request.POST.get(f"{prefix}novelty", 0) or 0)
				evaluation.coordinator1_task_distribution = int(request.POST.get(f"{prefix}task_distribution", 0) or 0)
				evaluation.coordinator1_schedule = int(request.POST.get(f"{prefix}schedule", 0) or 0)
				evaluation.coordinator1_interim = int(request.POST.get(f"{prefix}interim", 0) or 0)
				evaluation.coordinator1_presentation = int(request.POST.get(f"{prefix}presentation", 0) or 0)
				evaluation.coordinator1_viva = int(request.POST.get(f"{prefix}viva", 0) or 0)
				evaluation.coordinator1_submitted = True
			else:  # coordinator_role == 2
				evaluation.coordinator2_topic = int(request.POST.get(f"{prefix}topic", 0) or 0)
				evaluation.coordinator2_planning = int(request.POST.get(f"{prefix}planning", 0) or 0)
				evaluation.coordinator2_scalability = int(request.POST.get(f"{prefix}scalability", 0) or 0)
				evaluation.coordinator2_novelty = int(request.POST.get(f"{prefix}novelty", 0) or 0)
				evaluation.coordinator2_task_distribution = int(request.POST.get(f"{prefix}task_distribution", 0) or 0)
				evaluation.coordinator2_schedule = int(request.POST.get(f"{prefix}schedule", 0) or 0)
				evaluation.coordinator2_interim = int(request.POST.get(f"{prefix}interim", 0) or 0)
				evaluation.coordinator2_presentation = int(request.POST.get(f"{prefix}presentation", 0) or 0)
				evaluation.coordinator2_viva = int(request.POST.get(f"{prefix}viva", 0) or 0)
				evaluation.coordinator2_submitted = True
			
			# Also update legacy coordinator fields for backward compatibility
			evaluation.coordinator_topic = int(request.POST.get(f"{prefix}topic", 0) or 0)
			evaluation.coordinator_planning = int(request.POST.get(f"{prefix}planning", 0) or 0)
			evaluation.coordinator_scalability = int(request.POST.get(f"{prefix}scalability", 0) or 0)
			evaluation.coordinator_novelty = int(request.POST.get(f"{prefix}novelty", 0) or 0)
			evaluation.coordinator_task_distribution = int(request.POST.get(f"{prefix}task_distribution", 0) or 0)
			evaluation.coordinator_schedule = int(request.POST.get(f"{prefix}schedule", 0) or 0)
			evaluation.coordinator_interim = int(request.POST.get(f"{prefix}interim", 0) or 0)
			evaluation.coordinator_presentation = int(request.POST.get(f"{prefix}presentation", 0) or 0)
			evaluation.coordinator_viva = int(request.POST.get(f"{prefix}viva", 0) or 0)
			evaluation.coordinator_submitted = True
			
			# Finalize only if guide and both coordinators have submitted
			if evaluation.guide_submitted and evaluation.coordinator1_submitted and evaluation.coordinator2_submitted:
				evaluation.finalized = True
			evaluation.save()

		# Save presentation review (group-level)
		presentation_review = request.POST.get('presentation_review', '').strip()
		group_eval, created = GroupEvaluation.objects.get_or_create(
			group=group,
			stage=stage
		)
		if coordinator_role == 1:
			group_eval.coordinator1_review = presentation_review
		else:
			group_eval.coordinator2_review = presentation_review
		group_eval.coordinator_review = presentation_review  # Legacy field
		group_eval.save()

		# Ensure all students have finalized status updated
		_update_finalized_status(group, stage)

		# Attempt CIE calculation for all second-stage records in this group
		if stage == "second":
			for member in GroupMember.objects.filter(group=group).select_related("user"):
				second_eval = StudentEvaluation.objects.filter(student=member.user, group=group, stage="second").first()
				if second_eval:
					_try_calculate_cie(second_eval)

		messages.success(request, f"{stage.capitalize()} Evaluation submitted successfully for all students!")
		return redirect("coordinator_dashboard")

	return redirect("coordinator_dashboard")
