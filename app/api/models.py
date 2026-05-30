import uuid
from datetime import datetime
import os

from celery import chain
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify
from .utils import split_full_name
from django.db.models import Sum
from storages.backends.azure_storage import AzureStorage
from django.core.exceptions import ValidationError

class EduquestUser(AbstractUser):
    """
    Custom User model for EduQuest
    is_staff: True if user is an instructor
    """
    nickname = models.CharField(max_length=100, blank=True, null=True, editable=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    total_points = models.FloatField(default=0)
    current_points = models.FloatField(default=0)
    daily_checkin_streak = models.PositiveIntegerField(default=0)
    daily_checkin_longest_streak = models.PositiveIntegerField(default=0)
    daily_checkin_last_date = models.DateField(null=True, blank=True)
    daily_goals = models.JSONField(default=list, blank=True)  # [{goal: str, completed: bool}, ...]

    def __str__(self):
        return f"{self.id} - {self.username}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            self.nickname = self.username.replace("#", "")
            self.first_name, self.last_name = split_full_name(self.nickname)
        super().save(*args, **kwargs)
        if is_new and not self.is_superuser:
            # Ensure private learning path exists, then enroll the user.
            private_course_group = CourseGroup.objects.filter(name="Private Course Group").first()
            if private_course_group is None:
                private_academic_year = AcademicYear.objects.filter(start_year=0, end_year=0).order_by('id').first()
                if private_academic_year is None:
                    private_academic_year = AcademicYear.objects.create(start_year=0, end_year=0)

                private_term = Term.objects.filter(
                    academic_year=private_academic_year,
                    name="Private Term"
                ).order_by('id').first()
                if private_term is None:
                    private_term = Term.objects.create(
                        academic_year=private_academic_year,
                        name="Private Term",
                        start_date=None,
                        end_date=None
                    )

                private_course = Course.objects.filter(name="Private Course").first()
                if private_course is None:
                    private_image = Image.objects.filter(name="Private Courses").first()
                    private_course = Course.objects.create(
                        term=private_term,
                        name="Private Course",
                        code="PRIVATE",
                        type="System-enroll",
                        description="This is a private course for personal quest generation.",
                        status="Active",
                        image=private_image
                    )

                default_instructor = (
                    EduquestUser.objects.filter(is_superuser=True).order_by('id').first()
                    or EduquestUser.objects.filter(is_staff=True).order_by('id').first()
                    or self
                )
                private_course_group = CourseGroup.objects.filter(
                    course=private_course,
                    name="Private Course Group"
                ).order_by('id').first()
                if private_course_group is None:
                    private_course_group = CourseGroup.objects.create(
                        course=private_course,
                        name="Private Course Group",
                        session_day="",
                        session_time="",
                        instructor=default_instructor
                    )

            UserCourseGroupEnrollment.objects.get_or_create(student=self, course_group=private_course_group)
            UserCosmetics.objects.get_or_create(user=self)
            print(f"[Enroll Private Course Group] User: {self.username} has been enrolled in the Private course group")


class Image(models.Model):
    """
    Model to store images for courses, quests, and badges
    The image files are stored in Next.js public folder
    """
    name = models.CharField(max_length=100)
    filename = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class AcademicYear(models.Model):
    """
    Model to store academic years
    e.g. AY2021-2022
    """
    start_year = models.PositiveIntegerField()
    end_year = models.PositiveIntegerField()

    def __str__(self):
        return f"AY{self.start_year}-{self.end_year}"


class Term(models.Model):
    """
    Model to store terms for each academic year
    e.g. Term 1, Term 2, Term 3
    """
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='terms')
    name = models.CharField(max_length=50)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.academic_year} - {self.name} ({self.start_date} to {self.end_date})"


class Course(models.Model):
    """
    Model to store courses for each term
    e.g. Term 1 - SC1000, SC2000
    e.g. Term 2 - SC1000
    e.g. Term 2 - SC2000
    One course can have many course groups
    Many coordinators can coordinate many courses
    e.g. SC1000 coordinators: instructor1, instructor2
    e.g. SC2000 coordinators: instructor2, instructor3
    """
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='courses')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=100, null=True, blank=True)
    type = models.CharField(max_length=100)  # System-enroll, Self-enroll, Private
    description = models.TextField()
    status = models.CharField(max_length=100)  # Active, Expired
    image = models.ForeignKey(Image, on_delete=models.SET_NULL, null=True, blank=True)
    coordinators = models.ManyToManyField(EduquestUser, related_name='coordinated_courses')

    def clean(self):
        super().clean()
        # Remove the following block to prevent ValidationError during creation
        # if not self.pk and not self.coordinators.exists():
        #     raise ValidationError("A course must have at least one coordinator.")

    def save(self, *args, **kwargs):
        is_new_instance = self.pk is None
        old_status_value = None
        if not is_new_instance:
            old_instance = Course.objects.get(pk=self.pk)
            old_status_value = old_instance.status

        self.full_clean()  # Call the clean method
        super(Course, self).save(*args, **kwargs)

        # After saving the instance, check if 'status' changed from Active to Expired
        if old_status_value == 'Active' and self.status == 'Expired':
            # Import tasks locally to avoid circular import
            from .tasks import check_course_completion_and_award_completionist_badge, award_tutorial_attendance_badges_for_course
            # Trigger all tasks
            check_course_completion_and_award_completionist_badge.delay(self.id)
            award_tutorial_attendance_badges_for_course.delay(self.id)

            # Recursively set all quests in all course groups to 'Expired'
            for course_group in self.groups.all():
                for quest in course_group.quests.all():
                    quest.status = 'Expired'
                    quest.save()

    def total_students_enrolled(self):
        return UserCourseGroupEnrollment.objects.filter(course_group__course=self).count()

    def __str__(self):
        return f"Term {self.term.name} - {self.code}"



class CourseGroup(models.Model):
    """
    Model to store course groups for each course
    This is similar to how course index works in NTU
    e.g. SC1000 - TEL1, SCS1
    e.g. SC2000 - TEL2, SCS2
    """
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='groups')
    name = models.CharField(max_length=100) # Group name: e.g. TEL1, SWLA, SCSJ
    session_day = models.CharField(max_length=10, null=True, blank=True)  # e.g. Monday, Tuesday, Wednesday
    session_time = models.CharField(max_length=100, null=True, blank=True)  # e.g. 10:00 AM - 12:00 PM, 2:30 PM - 4:30 PM
    instructor = models.ForeignKey(EduquestUser, on_delete=models.CASCADE, related_name='instructed_course_groups')

    def total_students_enrolled(self):
        return UserCourseGroupEnrollment.objects.filter(course_group=self).count()

    def __str__(self):
        return f"Group {self.name} from {self.course.code}"


class UserCourseGroupEnrollment(models.Model):
    """
    Model to store the user's enrollment in a course group
    One course group can have many course group enrollment records
    One enrollment only stores one course group and one student
    """
    student = models.ForeignKey(EduquestUser, related_name='enrolled_course_groups', on_delete=models.CASCADE)
    course_group = models.ForeignKey(CourseGroup, related_name='enrolled_students', on_delete=models.CASCADE)
    enrolled_on = models.DateTimeField(auto_now_add=True)
    completed_on = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.student.username} enrolled in {self.course_group.course.code} - {self.course_group.name}"


class Quest(models.Model):
    """
    Model to store quests for each course group
    One course group can have many quests
    """
    course_group = models.ForeignKey(CourseGroup, on_delete=models.CASCADE, related_name='quests')
    name = models.CharField(max_length=100)
    description = models.TextField()
    type = models.CharField(max_length=50)  # EduQuest MCQ, Kahoot!, WooClap, Private
    status = models.CharField(max_length=50, default="Active")  # Active, Expired
    tutorial_date = models.DateTimeField(null=True, blank=True)
    expiration_date = models.DateTimeField(null=True, blank=True)
    max_attempts = models.PositiveIntegerField(default=1)
    organiser = models.ForeignKey(EduquestUser, on_delete=models.CASCADE, related_name='quests_organised')
    image = models.ForeignKey(Image, on_delete=models.SET_NULL, null=True, blank=True)
    source_document = models.ForeignKey('Document', on_delete=models.SET_NULL, null=True, blank=True, related_name='quests')

    def __str__(self):
        return f"{self.name} from Group {self.course_group.course.name} {self.course_group.course.code}"

    # Calculate the total max score for all questions in a quest
    def total_max_score(self):
        return self.questions.aggregate(total_max_score=Sum('max_score'))['total_max_score'] or 0

    # Calculate the total number of questions in a quest
    def total_questions(self):
        return self.questions.count()

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        previous_status = None
        if not is_new:
            previous = Quest.objects.get(pk=self.pk)
            previous_status = previous.status

        super(Quest, self).save(*args, **kwargs)
        # If the quest status changed from Active to Expired
        if previous_status == "Active" and self.status == "Expired":
            self.expiration_date = timezone.now()
            super(Quest, self).save(update_fields=['expiration_date'])

            from .tasks import award_speedster_badge, award_expert_badge
            award_expert_badge.delay(self.id)
            award_speedster_badge.delay(self.id)


class Question(models.Model):
    """
    Model to store questions for each quest
    One quest can have many questions
    """
    quest = models.ForeignKey(Quest, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    number = models.PositiveIntegerField()
    max_score = models.FloatField(default=1)
    hint = models.TextField(null=True, blank=True)

    question_type = models.CharField(max_length=50, default="mcq")  # mcq, matching, categorising, latex_mcq
    structured_data = models.JSONField(default=dict, blank=True)  # Extra data for non-mcq types

    cognitive_level = models.CharField(max_length=100, null=True, blank=True)  # Bloom's Taxonomy: Remember, Understand, Apply, Analyze, Evaluate, Create
    topic = models.CharField(max_length=255, null=True, blank=True)  # Topic of the question
    difficulty_score = models.FloatField(null=True, blank=True)  # 1-10 scale
    explanation = models.TextField(null=True, blank=True)  # Explanation for the correct answer
    
    def __str__(self):
        return f"{self.number} from Quest ID {self.quest.id}"


class Answer(models.Model):
    """
    Model to store answer options for each question
    """
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    reason = models.TextField(blank=True, null=True)  # Explanation for the correct answer, only for generated quest

    def __str__(self):
        return f"{self.text} for Question ID {self.question.id}"


class UserQuestAttempt(models.Model):
    """
    Model to store the user's attempt for each quest
    When the user starts a quest attempt, a record will be created
    """
    student = models.ForeignKey(EduquestUser, on_delete=models.CASCADE, related_name='attempted_quests')
    quest = models.ForeignKey(Quest, on_delete=models.CASCADE, related_name='attempted_by')
    submitted = models.BooleanField(default=False)
    first_attempted_date = models.DateTimeField(blank=True, null=True)  # blank for imported quests
    last_attempted_date = models.DateTimeField(blank=True, null=True)  # blank for imported quests
    total_score_achieved = models.FloatField(default=0)
    bonus_points = models.FloatField(default=0)
    bonus_awarded = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.student.username} attempted {self.quest.name}"

    def calculate_total_score_achieved(self):
        """
        Calculate the total score achieved by the user for the quest
        Set the score_achieved for each answer attempt.
        """
        total_score = 0
        user_answer_attempts_to_update = []
        questions = self.quest.questions.all()

        for question in questions:
            answers = question.answers.all()
            num_options = answers.count()
            num_correct = answers.filter(is_correct=True).count()

            if num_options == 0:
                continue  # Avoid division by zero

            weight_per_option = question.max_score / (num_correct or 1)
            user_answers = self.answer_attempts.filter(question=question)
            question_score = 0

            for ua in user_answers:
                # Use the is_correct field from UserAnswerAttempt (tracks if THIS student got it right)
                # Only award points if the student selected this answer AND it was correct for them
                if ua.is_selected and ua.answer.is_correct:
                    ua.score_achieved = weight_per_option
                    question_score += weight_per_option
                else:
                    ua.score_achieved = 0
                user_answer_attempts_to_update.append(ua)

            hint_used = user_answers.filter(hint_used=True).exists()
            if hint_used:
                remaining_penalty = 5
                for ua in user_answers:
                    if ua.score_achieved > 0 and remaining_penalty > 0:
                        deduction = min(ua.score_achieved, remaining_penalty)
                        ua.score_achieved -= deduction
                        remaining_penalty -= deduction
                question_score = max(0, question_score - 5)

            total_score += question_score

        # Bulk update all UserAnswerAttempt instances' score_achieved fields
        UserAnswerAttempt.objects.bulk_update(user_answer_attempts_to_update, ['score_achieved'])

        return total_score

    @property
    def time_taken(self):
        if not self.first_attempted_date or not self.last_attempted_date:
            return 0
        # Calculate the total time taken by subtracting the first_attempted_date from the last_attempted_date
        time_difference = self.last_attempted_date - self.first_attempted_date
        # If negative, return 0
        if time_difference.total_seconds() < 0:
            return 0
        return int(time_difference.total_seconds() * 1000)  # Convert to milliseconds


    def save(self, *args, **kwargs):
        is_new_instance = self.pk is None
        old_submitted_value = None
        if not is_new_instance:
            old_instance = UserQuestAttempt.objects.get(pk=self.pk)
            old_submitted_value = old_instance.submitted

        super(UserQuestAttempt, self).save(*args, **kwargs)

        # After saving the instance, check if 'submitted' changed from False to True
        if old_submitted_value == False and self.submitted == True:
            # Import tasks locally to avoid circular import
            from .tasks import (
                award_first_attempt_badge,
                calculate_score_and_issue_points,
                generate_personalised_feedback,
                update_cognitive_profile
            )
            # Trigger all tasks
            calculate_score_and_issue_points.delay(self.id)
            award_first_attempt_badge.delay(self.id)
            generate_personalised_feedback.delay(self.id)
            update_cognitive_profile.delay(self.id)
        elif self.submitted and not hasattr(self, 'personalised_feedback'):
            # Fallback: ensure feedback is generated if missing after submission
            from .tasks import generate_personalised_feedback
            generate_personalised_feedback.delay(self.id)

class UserAnswerAttempt(models.Model):
    """
    Model to store the user's selected answer options for each question attempt
    """
    user_quest_attempt = models.ForeignKey(UserQuestAttempt, on_delete=models.CASCADE, related_name='answer_attempts')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='user_answer_attempts')
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE)
    is_selected = models.BooleanField(default=False)
    is_correct = models.BooleanField(default=False)  # Whether this specific student got this answer correct
    hint_used = models.BooleanField(default=False)
    score_achieved = models.FloatField(default=0)

    def __str__(self):
        return f"{self.user_quest_attempt.student.username} selected {self.answer.text} for question {self.question.number}"


class Badge(models.Model):
    """
    Model to store badges that can be earned by users
    """
    name = models.CharField(max_length=50)
    description = models.TextField()
    type = models.CharField(max_length=50)  # Course Type or Quest Type
    condition = models.CharField(max_length=250)  # Condition to be met to earn the badge
    image = models.ForeignKey(Image, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.name}"




class UserCourseBadge(models.Model):
    """
    Model to store the user's earned badges from completing courses
    These badges are awarded based on 'course' related conditions
    """
    badge = models.ForeignKey(
        Badge,
        on_delete=models.CASCADE,
        related_name='awarded_to_course_completion'
    )
    user_course_group_enrollment = models.ForeignKey(
        UserCourseGroupEnrollment,
        on_delete=models.CASCADE,
        related_name='earned_course_badges'
    )
    awarded_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (f"{self.user_course_group_enrollment.student.username} earned {self.badge.name} from Course "
                f"{self.user_course_group_enrollment.course_group.course.code} - "
                f"{self.user_course_group_enrollment.course_group.name}")


class UserQuestBadge(models.Model):
    """
    Model to store the user's earned badges from attempting quests
    These badges are awarded based on 'quest' related conditions
    """
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name='awarded_to_quest_attempt')
    user_quest_attempt = models.ForeignKey(UserQuestAttempt, on_delete=models.CASCADE, related_name='earned_quest_badges')
    awarded_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (f"{self.user_quest_attempt.student.username} earned {self.badge.name} from Quest "
                f"{self.user_quest_attempt.quest.name}")


class Document(models.Model):
    """
    Model to store documents and their records uploaded by users
    """
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to='documents/')
    size = models.FloatField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(EduquestUser, on_delete=models.CASCADE, related_name='uploaded_documents')

    def save(self, *args, **kwargs):
        if self.file:
            storage = AzureStorage()
            file_name, file_extension = os.path.splitext(self.file.name)
            unique_file_name = self.file.name

            # Generate a unique file name using UUID
            while storage.exists(unique_file_name):
                unique_file_name = f"{file_name}_{uuid.uuid4().hex}{file_extension}"

            self.file.name = unique_file_name

        super(Document, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        storage = AzureStorage()
        if storage.exists(self.file.name):
            storage.delete(self.file.name)
        super(Document, self).delete(*args, **kwargs)

    def __str__(self):
        return self.name

class Cosmetic(models.Model):
    """
    Model to store cosmetic items that users can equip
    """
    class TypeOfCosmetic(models.TextChoices):
        Picture = 'Picture', _('Picture')
        Border = 'Border', _('Border')
        Banner = 'Banner', _('Banner')

    name = models.CharField(max_length=100)
    type = models.CharField(max_length=50, choices=TypeOfCosmetic.choices)
    image = models.ForeignKey(Image, on_delete=models.SET_NULL, null=True, blank=True)
    cost = models.FloatField(default=0)

    def get_type(self) -> TypeOfCosmetic:
        return self.TypeOfCosmetic(self.type)

    def __str__(self):
        return self.name

class UserCosmetics(models.Model):
    """
    Model to store user's profile cosmetics and display preferences.
    """
    user = models.OneToOneField(EduquestUser, on_delete=models.CASCADE)
    profile_picture = models.ForeignKey(Cosmetic, on_delete=models.SET_NULL, null=True, blank=True, related_name='usercosmetics_profile_picture')
    profile_background = models.CharField(max_length=255, blank=True, default="")
    profile_border = models.ForeignKey(Cosmetic, on_delete=models.SET_NULL, null=True, blank=True, related_name='usercosmetics_profile_border')
    banner = models.ForeignKey(Cosmetic, on_delete=models.SET_NULL, null=True, blank=True, related_name='usercosmetics_banner')
    displayed_badges = models.ManyToManyField('Badge', blank=True)
    about_me = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        errors = {}

        if self.profile_picture and self.profile_picture.type != Cosmetic.TypeOfCosmetic.Picture:
            errors['profile_picture'] = 'Only cosmetics classified as Picture may be used for profile_picture.'

        if self.profile_border and self.profile_border.type != Cosmetic.TypeOfCosmetic.Border:
            errors['profile_border'] = 'Only cosmetics classified as Border may be used for profile_border.'

        if self.banner and self.banner.type != Cosmetic.TypeOfCosmetic.Banner:
            errors['banner'] = 'Only cosmetics classified as Banner may be used for banner.'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super(UserCosmetics, self).save(*args, **kwargs)

    def __str__(self):
        return f"Cosmetics for {self.user.username}"


class StudentCognitiveProfile(models.Model):
    """
    Track student's cognitive performance across topics and difficulty levels
    """

    student = models.OneToOneField(EduquestUser, on_delete=models.CASCADE, related_name='cognitive_profile')
    
    # Performance based on Bloom's taxonomy levels
    remember_accuracy = models.FloatField(default=0.0)  # % correct based on quests
    understand_accuracy = models.FloatField(default=0.0)
    apply_accuracy = models.FloatField(default=0.0)
    analyse_accuracy = models.FloatField(default=0.0)
    evaluate_accuracy = models.FloatField(default=0.0)
    create_accuracy = models.FloatField(default=0.0)

    # Weak topics (JSON field storing topic names and accuracy)
    weak_topics = models.JSONField(default=dict)  # {topic_name: accuracy} e.g. {"Data Structures": 45.0, "Algorithms": 60.0}

    # Overall Assessment
    competency_level = models.CharField(max_length=50, default="Beginner")  # Beginner, Intermediate, Advanced
    recommend_difficulty = models.FloatField(default=5.0)  # 1-10 scale

    # Timestamp of last update (show to user when profile was last updated)
    last_updated_datetime = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cognitive Profile of {self.student.username}"


class StudentFeedback(models.Model):
    """
    Model to store personalised feedback for each quest attempt
    """

    user_quest_attempt = models.OneToOneField(UserQuestAttempt, on_delete=models.CASCADE, related_name='personalised_feedback')

    # Legacy feedback (kept for backward compatibility)
    strengths = models.JSONField(default=list, blank=True)  # List of strengths and topics done well
    weaknesses = models.JSONField(default=list, blank=True)  # List of weaknesses and topics to improve
    recommendations = models.TextField(blank=True, default="")  # AI-generated recommendations
    question_feedback = models.JSONField(default=dict, blank=True)  # {question_id: {feedback, explanation, study_tip}}

    # Bloom-based feedback (current schema)
    quest_summary = models.JSONField(default=dict, blank=True)  # {overall_bloom_rating, overall_bloom_level, summary}
    subtopic_feedback = models.JSONField(default=list, blank=True)  # [{subtopic, bloom_rating, bloom_level, evidence, improvement_focus}]
    study_tips = models.JSONField(default=list, blank=True)  # [tip, ...]

    datetime_created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback for {self.user_quest_attempt.student.username} on Quest {self.user_quest_attempt.quest.name}"


class StudentAttendanceOverride(models.Model):
    """
    Manual attendance correction per student and tutorial quest.
    is_present=True forces attendance to 1, is_present=False forces attendance to 0.
    """

    student = models.ForeignKey(EduquestUser, on_delete=models.CASCADE, related_name='attendance_overrides')
    quest = models.ForeignKey(Quest, on_delete=models.CASCADE, related_name='attendance_overrides')
    is_present = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        EduquestUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='attendance_overrides_updated'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'quest')

    def __str__(self):
        state = 'Present' if self.is_present else 'Absent'
        return f"{self.student.username} - {self.quest.name} ({state})"


class UserDailyCheckin(models.Model):
    """
    Model to store all daily check-in records for users
    This allows tracking the complete history of check-in dates instead of just the last one
    """
    student = models.ForeignKey(EduquestUser, on_delete=models.CASCADE, related_name='daily_checkins')
    checkin_date = models.DateField()

    class Meta:
        unique_together = ('student', 'checkin_date')

    def __str__(self):
        return f"{self.student.username} checked in on {self.checkin_date}"
