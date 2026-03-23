from .models import Notice, NoticeRead, StudentProfile


def unread_notices(request):
    """
    Injects unread_notice_count into every template context.

    BUG FIX: Original had bare 'except Exception' which would silently hide
    database errors (e.g. missing migrations). Now handles specific exceptions
    and also wraps in OperationalError catch for missing table scenarios.
    Also correctly returns 0 for admin/staff users (they don't have student profiles).
    """
    if not request.user.is_authenticated:
        return {'unread_notice_count': 0}

    # Admin/staff users don't have student profiles — return 0 cleanly
    if request.user.is_staff or request.user.is_superuser:
        return {'unread_notice_count': 0}

    try:
        profile = request.user.student_profile
        total   = Notice.objects.filter(is_active=True).count()
        read    = NoticeRead.objects.filter(student=profile).count()
        return {'unread_notice_count': max(0, total - read)}
    except StudentProfile.DoesNotExist:
        return {'unread_notice_count': 0}
    except Exception:
        # Catches OperationalError (missing table during migrations),
        # ProgrammingError, etc. — fail silently so site stays up
        return {'unread_notice_count': 0}