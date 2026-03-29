from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Class(models.Model):
	"""Represents a class/section. Each class has two coordinators assigned."""
	name = models.CharField(max_length=100, unique=True)
	department = models.CharField(max_length=100)
	
	class Meta:
		verbose_name_plural = "Classes"
	
	def __str__(self):
		return f"{self.name} - {self.department}"


class CoordinatorAssignment(models.Model):
	"""Assigns coordinators to classes. Each class should have exactly 2 coordinators."""
	faculty = models.ForeignKey(User, on_delete=models.CASCADE, related_name="coordinator_assignments")
	student_class = models.ForeignKey(Class, on_delete=models.CASCADE, related_name="coordinator_assignments")
	
	class Meta:
		unique_together = ("faculty", "student_class")
	
	def __str__(self):
		return f"{self.faculty.username} → {self.student_class.name}"


class StudentProfile(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
	student_class = models.ForeignKey(Class, on_delete=models.SET_NULL, null=True, blank=True, related_name="students")
	roll_number = models.CharField(max_length=50, blank=True, null=True)
	register_number = models.CharField(max_length=50, blank=True, null=True)
	department = models.CharField(max_length=100, blank=True, null=True)
	cgp = models.DecimalField(max_digits=3, decimal_places=2, blank=True, null=True)

	def __str__(self):
		return f"{self.user.username} - Student"


class FacultyProfile(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="faculty_profile")
	department = models.CharField(max_length=100, blank=True, null=True)
	is_guide = models.BooleanField(default=False)
	is_coordinator = models.BooleanField(default=False)
	is_hod = models.BooleanField(default=False)

	def __str__(self):
		roles = []
		if self.is_guide:
			roles.append("Guide")
		if self.is_coordinator:
			roles.append("Coordinator")
		if self.is_hod:
			roles.append("HOD")
		role_str = ", ".join(roles) if roles else "Faculty"
		return f"{self.user.username} - {role_str}"


class Group(models.Model):
	leader = models.ForeignKey(User, on_delete=models.CASCADE, related_name="leading_groups")
	created_at = models.DateTimeField(auto_now_add=True)


class GroupMember(models.Model):
	group = models.ForeignKey(Group, on_delete=models.CASCADE)
	user = models.ForeignKey(User, on_delete=models.CASCADE)

	class Meta:
		unique_together = ("group", "user")


class GroupRequest(models.Model):
	STATUS_PENDING = "pending"
	STATUS_ACCEPTED = "accepted"
	STATUS_REJECTED = "rejected"
	STATUS_CHOICES = [
		(STATUS_PENDING, "Pending"),
		(STATUS_ACCEPTED, "Accepted"),
		(STATUS_REJECTED, "Rejected"),
	]

	sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_group_requests")
	recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_group_requests")
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		unique_together = ("sender", "recipient")


class GuideRequest(models.Model):
	STATUS_PENDING = "pending"
	STATUS_ACCEPTED = "accepted"
	STATUS_REJECTED = "rejected"
	STATUS_CHOICES = [
		(STATUS_PENDING, "Pending"),
		(STATUS_ACCEPTED, "Accepted"),
		(STATUS_REJECTED, "Rejected"),
	]

	group = models.ForeignKey(Group, on_delete=models.CASCADE)
	guide = models.ForeignKey(User, on_delete=models.CASCADE, related_name="guide_requests")
	message = models.TextField()
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)


class CoordinatorApproval(models.Model):
	STATUS_PENDING = "pending"
	STATUS_APPROVED = "approved"
	STATUS_REJECTED = "rejected"
	STATUS_CHOICES = [
		(STATUS_PENDING, "Pending"),
		(STATUS_APPROVED, "Approved"),
		(STATUS_REJECTED, "Rejected"),
	]

	group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="coordinator_approvals")
	coordinator = models.ForeignKey(User, on_delete=models.CASCADE, related_name="coordinator_approvals")
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	
	class Meta:
		unique_together = ("group", "coordinator")
	
	def __str__(self):
		return f"Group {self.group.id} - {self.coordinator.username} ({self.status})"


class Abstract(models.Model):
	STATUS_PENDING = "pending"
	STATUS_APPROVED = "approved"
	STATUS_REJECTED = "rejected"
	STATUS_CHOICES = [
		(STATUS_PENDING, "Pending"),
		(STATUS_APPROVED, "Approved"),
		(STATUS_REJECTED, "Rejected"),
	]

	group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="abstracts")
	title = models.CharField(max_length=255)
	abstract_text = models.TextField()
	pdf_file = models.BinaryField(null=True, blank=True)
	pdf_filename = models.CharField(max_length=255, null=True, blank=True)
	pdf_size = models.IntegerField(null=True, blank=True)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
	guide_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
	coordinator_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)  # Keep for backward compatibility
	coordinator1_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
	coordinator2_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
	hod_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
	is_final_approved = models.BooleanField(default=False)
	presentation_approved = models.BooleanField(default=False)
	final_approved = models.BooleanField(default=False)
	feedback = models.TextField(null=True, blank=True)
	submitted_at = models.DateTimeField(auto_now_add=True)
	reviewed_at = models.DateTimeField(null=True, blank=True)
	reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_abstracts")

	class Meta:
		ordering = ["-submitted_at"]

	def __str__(self):
		return f"{self.title} - {self.group.leader.username}"


class SustainableDevelopmentGoal(models.Model):
	group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="sdg")
	
	# Project Information
	project_title = models.CharField(max_length=500, default="", blank=True)
	project_description = models.TextField(default="", blank=True)
	
	# SDG Goals
	sdg1 = models.CharField(max_length=255, default="", blank=True)
	sdg1_justification = models.TextField(default="", blank=True)
	sdg2 = models.CharField(max_length=255, default="", blank=True)
	sdg2_justification = models.TextField(default="", blank=True)
	sdg3 = models.CharField(max_length=255, default="", blank=True)
	sdg3_justification = models.TextField(default="", blank=True)
	sdg4 = models.CharField(max_length=255, default="", blank=True)
	sdg4_justification = models.TextField(default="", blank=True)
	sdg5 = models.CharField(max_length=255, default="", blank=True)
	sdg5_justification = models.TextField(default="", blank=True)
	
	# Work Packages
	wp1 = models.CharField(max_length=255, default="", blank=True)
	wp1_justification = models.TextField(default="", blank=True)
	wp2 = models.CharField(max_length=255, default="", blank=True)
	wp2_justification = models.TextField(default="", blank=True)
	wp3 = models.CharField(max_length=255, default="", blank=True)
	wp3_justification = models.TextField(default="", blank=True)
	wp4 = models.CharField(max_length=255, default="", blank=True)
	wp4_justification = models.TextField(default="", blank=True)
	wp5 = models.CharField(max_length=255, default="", blank=True)
	wp5_justification = models.TextField(default="", blank=True)

	# Program Outcomes
	po1 = models.CharField(max_length=100, default="", blank=True)
	po2 = models.CharField(max_length=100, default="", blank=True)
	po3 = models.CharField(max_length=100, default="", blank=True)
	po4 = models.CharField(max_length=100, default="", blank=True)
	po5 = models.CharField(max_length=100, default="", blank=True)
	pso1 = models.CharField(max_length=100, default="", blank=True)
	pso2 = models.CharField(max_length=100, default="", blank=True)

	submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="submitted_sdgs")
	is_submitted = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"SDG - Group {self.group_id}"

	@property
	def content(self):
		return f"SDG1: {self.sdg1}\nSDG2: {self.sdg2}\nSDG3: {self.sdg3}\nSDG4: {self.sdg4}\nSDG5: {self.sdg5}"


class Notification(models.Model):
	NOTIF_COORDINATOR_FORWARD = "coordinator_forward"
	NOTIF_PRESENTATION_READY = "presentation_ready"
	NOTIF_FINAL_APPROVAL = "final_approval"
	NOTIF_TYPE_CHOICES = [
		(NOTIF_COORDINATOR_FORWARD, "Coordinator Forwarded Project"),
		(NOTIF_PRESENTATION_READY, "Project Ready for Presentation Approval"),
		(NOTIF_FINAL_APPROVAL, "Final Project Requires Approval"),
	]

	recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
	notif_type = models.CharField(max_length=50, choices=NOTIF_TYPE_CHOICES, default=NOTIF_COORDINATOR_FORWARD)
	message = models.TextField()
	related_abstract = models.ForeignKey(
		"Abstract", on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
	)
	created_at = models.DateTimeField(auto_now_add=True)
	is_read = models.BooleanField(default=False)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return f"Notification for {self.recipient.username}: {self.message[:50]}"


class GroupEvaluation(models.Model):
	STAGE_CHOICES = [
		("zeroth", "Zeroth Evaluation"),
		("first", "First Evaluation"),
		("second", "Second Evaluation"),
		("final", "Final Evaluation"),
	]

	group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="evaluations")
	stage = models.CharField(max_length=10, choices=STAGE_CHOICES)

	# Guide evaluation checkboxes
	guide_technical_exposure = models.BooleanField(default=False)
	guide_socially_relevant = models.BooleanField(default=False)
	guide_product_based = models.BooleanField(default=False)
	guide_research_oriented = models.BooleanField(default=False)

	# Coordinator 1 evaluation checkboxes
	coordinator1_technical_exposure = models.BooleanField(default=False)
	coordinator1_socially_relevant = models.BooleanField(default=False)
	coordinator1_product_based = models.BooleanField(default=False)
	coordinator1_research_oriented = models.BooleanField(default=False)
	
	# Coordinator 2 evaluation checkboxes
	coordinator2_technical_exposure = models.BooleanField(default=False)
	coordinator2_socially_relevant = models.BooleanField(default=False)
	coordinator2_product_based = models.BooleanField(default=False)
	coordinator2_research_oriented = models.BooleanField(default=False)

	# Legacy coordinator evaluation checkboxes (keep for backward compatibility)
	coordinator_technical_exposure = models.BooleanField(default=False)
	coordinator_socially_relevant = models.BooleanField(default=False)
	coordinator_product_based = models.BooleanField(default=False)
	coordinator_research_oriented = models.BooleanField(default=False)

	# Review/Feedback fields
	guide_review = models.TextField(blank=True, null=True)
	coordinator1_review = models.TextField(blank=True, null=True)
	coordinator2_review = models.TextField(blank=True, null=True)
	coordinator_review = models.TextField(blank=True, null=True)  # Keep for backward compatibility

	guide_submitted = models.BooleanField(default=False)
	coordinator1_submitted = models.BooleanField(default=False)
	coordinator2_submitted = models.BooleanField(default=False)
	coordinator_submitted = models.BooleanField(default=False)  # Keep for backward compatibility

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		unique_together = ("group", "stage")
		ordering = ["group", "stage"]

	def __str__(self):
		return f"{self.group.leader.username} - {self.get_stage_display()}"

	@property
	def zeroth_completed(self):
		"""Zeroth stage is complete when guide and any one coordinator have submitted."""
		return self.guide_submitted and (
			self.coordinator1_submitted or self.coordinator2_submitted or self.coordinator_submitted
		)

	@property
	def is_completed(self):
		"""Stage-aware completion: zeroth allows any one coordinator; later stages require both."""
		if self.stage == "zeroth":
			return self.zeroth_completed
		return self.guide_submitted and self.coordinator1_submitted and self.coordinator2_submitted


class EvaluationFile(models.Model):
	"""File uploads for group evaluations (PDF, PPT, etc.)"""
	STAGE_CHOICES = [
		("zeroth", "Zeroth Evaluation"),
		("first", "First Evaluation"),
		("second", "Second Evaluation"),
		("final", "Final Evaluation"),
	]

	group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="evaluation_files")
	stage = models.CharField(max_length=10, choices=STAGE_CHOICES)
	file_data = models.BinaryField()
	file_name = models.CharField(max_length=255)
	file_size = models.IntegerField()
	file_type = models.CharField(max_length=100)  # e.g., 'application/pdf', 'application/vnd.ms-powerpoint'
	uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="uploaded_evaluation_files")
	uploaded_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-uploaded_at"]

	def __str__(self):
		return f"{self.group.leader.username} - {self.get_stage_display()} - {self.file_name}"

	@property
	def file_extension(self):
		"""Returns the file extension."""
		return self.file_name.split('.')[-1].lower() if '.' in self.file_name else ''


class ProjectReport(models.Model):
	"""Group-level project report and coordinator review marks."""
	STATUS_PENDING = "pending"
	STATUS_APPROVED = "approved"
	STATUS_REJECTED = "rejected"
	STATUS_CHOICES = [
		(STATUS_PENDING, "Pending"),
		(STATUS_APPROVED, "Approved"),
		(STATUS_REJECTED, "Rejected"),
	]

	group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="project_report")
	report_file = models.FileField(upload_to="project_reports/")
	uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
	uploaded_at = models.DateTimeField(auto_now_add=True)
	review_status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
	rejection_review = models.TextField(blank=True)
	rejected_by = models.ForeignKey(
		User,
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="rejected_project_reports",
	)
	rejected_at = models.DateTimeField(null=True, blank=True)

	coordinator1_mark = models.IntegerField(
		null=True,
		blank=True,
		validators=[MinValueValidator(0), MaxValueValidator(10)],
	)
	coordinator2_mark = models.IntegerField(
		null=True,
		blank=True,
		validators=[MinValueValidator(0), MaxValueValidator(10)],
	)
	final_mark = models.IntegerField(
		null=True,
		blank=True,
		validators=[MinValueValidator(0), MaxValueValidator(10)],
	)

	coordinator1_submitted = models.BooleanField(default=False)
	coordinator2_submitted = models.BooleanField(default=False)

	def __str__(self):
		return f"Project Report - Group {self.group_id}"


class StudentEvaluation(models.Model):
	"""Per-student evaluation for First and Second stages with detailed criteria."""
	STAGE_CHOICES = [
		("first", "First Evaluation"),
		("second", "Second Evaluation"),
	]

	student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="student_evaluations")
	group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="student_evaluations")
	stage = models.CharField(max_length=10, choices=STAGE_CHOICES)

	# Guide marks (max 40 total)
	guide_topic = models.IntegerField(default=0)  # max 5
	guide_planning = models.IntegerField(default=0)  # max 5
	guide_scalability = models.IntegerField(default=0)  # max 2
	guide_novelty = models.IntegerField(default=0)  # max 5
	guide_task_distribution = models.IntegerField(default=0)  # max 5
	guide_schedule = models.IntegerField(default=0)  # max 3
	guide_interim = models.IntegerField(default=0)  # max 5
	guide_presentation = models.IntegerField(default=0)  # max 5
	guide_viva = models.IntegerField(default=0)  # max 5

	guide_submitted = models.BooleanField(default=False)

	# Coordinator 1 marks (max 40 total)
	coordinator1_topic = models.IntegerField(default=0)
	coordinator1_planning = models.IntegerField(default=0)
	coordinator1_scalability = models.IntegerField(default=0)
	coordinator1_novelty = models.IntegerField(default=0)
	coordinator1_task_distribution = models.IntegerField(default=0)
	coordinator1_schedule = models.IntegerField(default=0)
	coordinator1_interim = models.IntegerField(default=0)
	coordinator1_presentation = models.IntegerField(default=0)
	coordinator1_viva = models.IntegerField(default=0)

	coordinator1_submitted = models.BooleanField(default=False)

	# Coordinator 2 marks (max 40 total)
	coordinator2_topic = models.IntegerField(default=0)
	coordinator2_planning = models.IntegerField(default=0)
	coordinator2_scalability = models.IntegerField(default=0)
	coordinator2_novelty = models.IntegerField(default=0)
	coordinator2_task_distribution = models.IntegerField(default=0)
	coordinator2_schedule = models.IntegerField(default=0)
	coordinator2_interim = models.IntegerField(default=0)
	coordinator2_presentation = models.IntegerField(default=0)
	coordinator2_viva = models.IntegerField(default=0)

	coordinator2_submitted = models.BooleanField(default=False)

	# Legacy coordinator marks (keep for backward compatibility)
	coordinator_topic = models.IntegerField(default=0)
	coordinator_planning = models.IntegerField(default=0)
	coordinator_scalability = models.IntegerField(default=0)
	coordinator_novelty = models.IntegerField(default=0)
	coordinator_task_distribution = models.IntegerField(default=0)
	coordinator_schedule = models.IntegerField(default=0)
	coordinator_interim = models.IntegerField(default=0)
	coordinator_presentation = models.IntegerField(default=0)
	coordinator_viva = models.IntegerField(default=0)

	coordinator_submitted = models.BooleanField(default=False)

	attendance_marks = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(10)],
	)
	attendance_submitted = models.BooleanField(default=False)
	attendance_submitted_by = models.ForeignKey(
		User,
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="attendance_uploaded",
	)
	attendance_submitted_at = models.DateTimeField(null=True, blank=True)

	final_guide_topic = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(5)],
	)
	final_guide_planning = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(5)],
	)
	final_guide_scale = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(2)],
	)
	final_guide_novelty = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(5)],
	)
	final_guide_task = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(5)],
	)
	final_guide_schedule = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(3)],
	)
	final_guide_interim = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(5)],
	)
	final_guide_presentation = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(5)],
	)
	final_guide_viva = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(5)],
	)
	final_guide_total = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(40)],
	)

	final_guide_raw = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(40)],
	)
	final_guide_mark = models.IntegerField(default=0, null=True, blank=True)
	final_guide_submitted = models.BooleanField(default=False)
	final_guide_submitted_at = models.DateTimeField(null=True, blank=True)

	# CIE (Continuous Internal Evaluation) fields — stored on the "second" stage record
	committee_raw_total = models.IntegerField(default=0, null=True, blank=True)
	committee_mark = models.IntegerField(default=0, null=True, blank=True)
	cie_total = models.IntegerField(default=0, null=True, blank=True)
	cie_calculated = models.BooleanField(default=False)
	cie_calculated_at = models.DateTimeField(null=True, blank=True)

	# ESE (External Evaluation) Guide marks
	ese_guide_presentation = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(30)],
	)  # max 30
	ese_guide_demo = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(20)],
	)  # max 20
	ese_guide_viva = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(25)],
	)  # max 25
	ese_guide_submitted = models.BooleanField(default=False)
	ese_guide_submitted_at = models.DateTimeField(null=True, blank=True)

	# ESE (External Evaluation) Coordinator 1 marks
	ese_coord1_presentation = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(30)],
	)  # max 30
	ese_coord1_demo = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(20)],
	)  # max 20
	ese_coord1_viva = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(25)],
	)  # max 25
	ese_coord1_submitted = models.BooleanField(default=False)
	ese_coord1_submitted_at = models.DateTimeField(null=True, blank=True)

	# ESE (External Evaluation) Coordinator 2 marks
	ese_coord2_presentation = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(30)],
	)  # max 30
	ese_coord2_demo = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(20)],
	)  # max 20
	ese_coord2_viva = models.IntegerField(
		default=0,
		validators=[MinValueValidator(0), MaxValueValidator(25)],
	)  # max 25
	ese_coord2_submitted = models.BooleanField(default=False)
	ese_coord2_submitted_at = models.DateTimeField(null=True, blank=True)

	# ESE Final averaged mark
	ese_final = models.IntegerField(null=True, blank=True)
	ese_completed = models.BooleanField(default=False)
	ese_completed_at = models.DateTimeField(null=True, blank=True)

	# Final result cache
	final_total = models.IntegerField(null=True, blank=True)
	final_percentage = models.FloatField(null=True, blank=True)
	final_grade = models.CharField(max_length=5, null=True, blank=True)
	result_calculated = models.BooleanField(default=False)

	finalized = models.BooleanField(default=False)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		unique_together = ("student", "stage")
		ordering = ["group", "stage", "student"]

	def __str__(self):
		return f"{self.student.username} - {self.get_stage_display()}"

	@property
	def guide_total(self):
		"""Calculate total guide marks."""
		marks = [
			self.guide_topic or 0,
			self.guide_planning or 0,
			self.guide_scalability or 0,
			self.guide_novelty or 0,
			self.guide_task_distribution or 0,
			self.guide_schedule or 0,
			self.guide_interim or 0,
			self.guide_presentation or 0,
			self.guide_viva or 0,
		]
		return sum(marks)

	@property
	def coordinator1_total(self):
		"""Calculate total coordinator1 marks."""
		marks = [
			self.coordinator1_topic or 0,
			self.coordinator1_planning or 0,
			self.coordinator1_scalability or 0,
			self.coordinator1_novelty or 0,
			self.coordinator1_task_distribution or 0,
			self.coordinator1_schedule or 0,
			self.coordinator1_interim or 0,
			self.coordinator1_presentation or 0,
			self.coordinator1_viva or 0,
		]
		return sum(marks)
	
	@property
	def coordinator2_total(self):
		"""Calculate total coordinator2 marks."""
		marks = [
			self.coordinator2_topic or 0,
			self.coordinator2_planning or 0,
			self.coordinator2_scalability or 0,
			self.coordinator2_novelty or 0,
			self.coordinator2_task_distribution or 0,
			self.coordinator2_schedule or 0,
			self.coordinator2_interim or 0,
			self.coordinator2_presentation or 0,
			self.coordinator2_viva or 0,
		]
		return sum(marks)

	@property
	def coordinator_total(self):
		"""Calculate total coordinator marks (legacy compatibility)."""
		marks = [
			self.coordinator_topic or 0,
			self.coordinator_planning or 0,
			self.coordinator_scalability or 0,
			self.coordinator_novelty or 0,
			self.coordinator_task_distribution or 0,
			self.coordinator_schedule or 0,
			self.coordinator_interim or 0,
			self.coordinator_presentation or 0,
			self.coordinator_viva or 0,
		]
		return sum(marks)

	@property
	def ese_guide_total(self):
		"""Calculate total ESE Guide marks (presentation + demo + viva)."""
		marks = [
			self.ese_guide_presentation or 0,
			self.ese_guide_demo or 0,
			self.ese_guide_viva or 0,
		]
		return sum(marks)

	@property
	def ese_coord1_total(self):
		"""Calculate total ESE Coordinator 1 marks (presentation + demo + viva)."""
		marks = [
			self.ese_coord1_presentation or 0,
			self.ese_coord1_demo or 0,
			self.ese_coord1_viva or 0,
		]
		return sum(marks)

	@property
	def ese_coord2_total(self):
		"""Calculate total ESE Coordinator 2 marks (presentation + demo + viva)."""
		marks = [
			self.ese_coord2_presentation or 0,
			self.ese_coord2_demo or 0,
			self.ese_coord2_viva or 0,
		]
		return sum(marks)

	@property
	def ese_final_calculated(self):
		"""Average submitted ESE totals on the native 75-point scale."""
		totals = []
		if self.ese_guide_submitted:
			totals.append(self.ese_guide_total)
		if self.ese_coord1_submitted:
			totals.append(self.ese_coord1_total)
		if self.ese_coord2_submitted:
			totals.append(self.ese_coord2_total)
		if totals:
			average = sum(totals) / len(totals)
			return round(average)
		return None

	@property
	def second_eval_completed(self):
		"""Returns True when guide and both coordinators have submitted second evaluation marks."""
		return self.guide_submitted and self.coordinator1_submitted and self.coordinator2_submitted

	@property
	def is_completed(self):
		"""Returns True if guide and both coordinators have submitted and finalized."""
		return self.second_eval_completed and self.finalized


