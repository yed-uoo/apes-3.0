from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
	ROLE_STUDENT = "student"
	ROLE_GUIDE = "guide"
	ROLE_CHOICES = [
		(ROLE_STUDENT, "Student"),
		(ROLE_GUIDE, "Guide"),
	]

	user = models.OneToOneField(User, on_delete=models.CASCADE)
	role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_STUDENT)


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
	feedback = models.TextField(null=True, blank=True)
	submitted_at = models.DateTimeField(auto_now_add=True)
	reviewed_at = models.DateTimeField(null=True, blank=True)
	reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_abstracts")

	class Meta:
		ordering = ["-submitted_at"]

	def __str__(self):
		return f"{self.title} - {self.group.leader.username}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
	if created:
		UserProfile.objects.create(user=instance)
