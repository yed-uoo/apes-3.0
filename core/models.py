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

	def __str__(self):
		return f"{self.user.username} - Student"


class FacultyProfile(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="faculty_profile")
	department = models.CharField(max_length=100, blank=True, null=True)
	is_guide = models.BooleanField(default=False)
	is_coordinator = models.BooleanField(default=False)

	def __str__(self):
		roles = []
		if self.is_guide:
			roles.append("Guide")
		if self.is_coordinator:
			roles.append("Coordinator")
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
	is_final_approved = models.BooleanField(default=False)
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
	sdg1 = models.CharField(max_length=255, default="")
	sdg1_justification = models.TextField(default="")
	sdg2 = models.CharField(max_length=255, default="")
	sdg2_justification = models.TextField(default="")
	sdg3 = models.CharField(max_length=255, default="")
	sdg3_justification = models.TextField(default="")
	sdg4 = models.CharField(max_length=255, default="")
	sdg4_justification = models.TextField(default="")
	sdg5 = models.CharField(max_length=255, default="")
	sdg5_justification = models.TextField(default="")

	wp1 = models.CharField(max_length=255, default="")
	wp1_justification = models.TextField(default="")
	wp2 = models.CharField(max_length=255, default="")
	wp2_justification = models.TextField(default="")
	wp3 = models.CharField(max_length=255, default="")
	wp3_justification = models.TextField(default="")
	wp4 = models.CharField(max_length=255, default="")
	wp4_justification = models.TextField(default="")
	wp5 = models.CharField(max_length=255, default="")
	wp5_justification = models.TextField(default="")

	po1 = models.CharField(max_length=100, default="")
	po2 = models.CharField(max_length=100, default="")
	po3 = models.CharField(max_length=100, default="")
	po4 = models.CharField(max_length=100, default="")
	po5 = models.CharField(max_length=100, default="")
	pso1 = models.CharField(max_length=100, default="")
	pso2 = models.CharField(max_length=100, default="")

	submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="submitted_sdgs")
	is_submitted = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"SDG - Group {self.group_id}"

	@property
	def content(self):
		return f"SDG1: {self.sdg1}\nSDG2: {self.sdg2}\nSDG3: {self.sdg3}\nSDG4: {self.sdg4}\nSDG5: {self.sdg5}"

