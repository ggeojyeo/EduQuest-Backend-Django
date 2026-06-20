from django.contrib import admin
from .models import (
    EduquestUser,
    Image,
    AcademicYear,
    Term,
    Course,
    CourseGroup,
    UserCourseGroupEnrollment,
    Quest,
    Question,
    Answer,
    UnstructuredAnswer,
    UserQuestAttempt,
    UserAnswerAttempt,
    UserShortAnswerAttempt,
    TestScore,
    UserTestScore,
    Badge,
    UserQuestBadge,
    UserCourseBadge,
    Document,
    Cosmetic
)


# Register your models here.
admin.site.register(EduquestUser)
admin.site.register(AcademicYear)
admin.site.register(Term)
admin.site.register(Course)
admin.site.register(CourseGroup)
admin.site.register(UserCourseGroupEnrollment)
admin.site.register(Quest)
admin.site.register(Question)
admin.site.register(Answer)
admin.site.register(UnstructuredAnswer)
admin.site.register(UserAnswerAttempt)
admin.site.register(UserShortAnswerAttempt)
admin.site.register(UserQuestAttempt)
admin.site.register(TestScore)
admin.site.register(UserTestScore)
admin.site.register(Badge)
admin.site.register(UserQuestBadge)
admin.site.register(UserCourseBadge)
admin.site.register(Image)
admin.site.register(Document)
admin.site.register(Cosmetic)

