from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class StudentProfile(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
	class_name = models.CharField(max_length=100, blank=True, null=True)
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

	group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="coordinator_approval")
	coordinator = models.ForeignKey(User, on_delete=models.CASCADE, related_name="coordinator_approvals")
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)


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
	coordinator_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
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

	# Coordinator evaluation checkboxes
	coordinator_technical_exposure = models.BooleanField(default=False)
	coordinator_socially_relevant = models.BooleanField(default=False)
	coordinator_product_based = models.BooleanField(default=False)
	coordinator_research_oriented = models.BooleanField(default=False)

	# Review/Feedback fields
	guide_review = models.TextField(blank=True, null=True)
	coordinator_review = models.TextField(blank=True, null=True)

	guide_submitted = models.BooleanField(default=False)
	coordinator_submitted = models.BooleanField(default=False)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		unique_together = ("group", "stage")
		ordering = ["group", "stage"]

	def __str__(self):
		return f"{self.group.leader.username} - {self.get_stage_display()}"

	@property
	def is_completed(self):
		"""Returns True if both guide and coordinator have submitted."""
		return self.guide_submitted and self.coordinator_submitted


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
	guide_topic = models.IntegerField(null=True, blank=True)  # max 5
	guide_planning = models.IntegerField(null=True, blank=True)  # max 5
	guide_scalability = models.IntegerField(null=True, blank=True)  # max 2
	guide_novelty = models.IntegerField(null=True, blank=True)  # max 5
	guide_task_distribution = models.IntegerField(null=True, blank=True)  # max 5
	guide_schedule = models.IntegerField(null=True, blank=True)  # max 3
	guide_interim = models.IntegerField(null=True, blank=True)  # max 5
	guide_presentation = models.IntegerField(null=True, blank=True)  # max 5
	guide_viva = models.IntegerField(null=True, blank=True)  # max 5

	guide_submitted = models.BooleanField(default=False)

	# Coordinator marks (max 40 total)
	coordinator_topic = models.IntegerField(null=True, blank=True)  # max 5
	coordinator_planning = models.IntegerField(null=True, blank=True)  # max 5
	coordinator_scalability = models.IntegerField(null=True, blank=True)  # max 2
	coordinator_novelty = models.IntegerField(null=True, blank=True)  # max 5
	coordinator_task_distribution = models.IntegerField(null=True, blank=True)  # max 5
	coordinator_schedule = models.IntegerField(null=True, blank=True)  # max 3
	coordinator_interim = models.IntegerField(null=True, blank=True)  # max 5
	coordinator_presentation = models.IntegerField(null=True, blank=True)  # max 5
	coordinator_viva = models.IntegerField(null=True, blank=True)  # max 5

	coordinator_submitted = models.BooleanField(default=False)

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
	def coordinator_total(self):
		"""Calculate total coordinator marks."""
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
	def is_completed(self):
		"""Returns True if both guide and coordinator have submitted and finalized."""
		return self.guide_submitted and self.coordinator_submitted and self.finalized


