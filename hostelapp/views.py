from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count, Sum
from django.http import HttpResponse, JsonResponse, QueryDict
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.conf import settings
import io
import random
import calendar
from collections import defaultdict
from datetime import date, timedelta, date as date_cls
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib.pagesizes import A4, landscape
from django.contrib.auth.models import User as UserModel, Group, Permission
from django.contrib.contenttypes.models import ContentType
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                 Paragraph, Spacer)
from .models import (StudentProfile, Room, RoomAllotment, Complaint, Notice,
                     NoticeRead, StaffMember, OTPVerification, Attendance,
                     ComplaintUpvote, Message, Notification, HostelRule,
                     LeaveRequest, FeePayment, RoomPhoto, HostelGallery,
                     StudentDocument,WardenMessage, HostelBlock)
from .forms import (StudentRegistrationForm, StudentProfileForm, RoomForm,
                    RoomAllotmentForm, ComplaintForm, ComplaintUpdateForm,
                    NoticeForm, StaffMemberForm,)


def is_admin(user):
    """Allow superusers, staff, OR users with any hostelapp permission."""
    if user.is_superuser or user.is_staff:
        return True
    hostel_permissions = [
        'hostelapp.add_room', 'hostelapp.change_room',
        'hostelapp.add_roomallotment', 'hostelapp.change_roomallotment',
        'hostelapp.change_complaint', 'hostelapp.view_studentprofile',
        'hostelapp.add_notice', 'hostelapp.change_notice',
    ]
    return any(user.has_perm(p) for p in hostel_permissions)


def can_manage_rooms(user):
    return user.is_superuser or user.is_staff or user.has_perm('hostelapp.add_room') or user.has_perm('hostelapp.change_room')


def can_manage_allotments(user):
    return user.is_superuser or user.is_staff or user.has_perm('hostelapp.add_roomallotment') or user.has_perm('hostelapp.change_roomallotment')


def can_manage_complaints(user):
    return user.is_superuser or user.is_staff or user.has_perm('hostelapp.change_complaint')


def can_view_students(user):
    return user.is_superuser or user.is_staff or user.has_perm('hostelapp.view_studentprofile')


def is_warden(user):
    """Check if user is a warden (staff but not superuser, in warden group)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    return user.is_staff and user.groups.filter(name='Warden').exists()


def is_super_admin(user):
    """Full admin — superuser only."""
    return user.is_superuser


# ── PUBLIC VIEWS ──────────────────────────────────────────────────────────────

def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'hostelapp/home.html')  # fixed


def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(email, otp):
    subject = 'HostelHub - Email Verification OTP'
    message = f"""Hello,

Your OTP for HostelHub registration is:

    {otp}

This OTP is valid for {getattr(settings, 'OTP_EXPIRY_MINUTES', 10)} minutes.
Do not share this OTP with anyone.

If you did not request this, please ignore this email.

Regards,
HostelHub Team"""
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)


def register(request):
    """Step 1: Fill form → send OTP to email."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        user_form = StudentRegistrationForm(request.POST)
        profile_form = StudentProfileForm(request.POST, request.FILES)
        if user_form.is_valid() and profile_form.is_valid():
            email = user_form.cleaned_data['email']
            # Check roll_number uniqueness before sending OTP
            roll_number = request.POST.get('roll_number', '').strip().upper()
            if StudentProfile.objects.filter(roll_number=roll_number).exists():
                messages.error(request, f'Roll number "{roll_number}" is already registered.')
                return render(request, 'hostelapp/register.html', {
                    'user_form': user_form, 'profile_form': profile_form,
                    'blocks': HostelBlock.objects.filter(is_active=True)})
            # Save form data in session (not DB yet — wait for OTP)
            request.session['reg_user_form']    = request.POST.dict()
            request.session['reg_has_photo']    = bool(request.FILES.get('profile_photo'))
            # Generate & send OTP
            otp = generate_otp()
            OTPVerification.objects.filter(email=email, is_used=False).delete()
            OTPVerification.objects.create(email=email, otp=otp)
            try:
                send_otp_email(email, otp)
                request.session['otp_email'] = email
                messages.success(request, f'OTP sent to {email}. Please check your inbox.')
                return redirect('verify_otp')
            except Exception as e:
                messages.error(request, f'Failed to send OTP: {str(e)}. Check email settings.')
        else:
            # Show exact errors
            for field, errs in user_form.errors.items():
                for err in errs:
                    messages.error(request, f'{field}: {err}')
            for field, errs in profile_form.errors.items():
                for err in errs:
                    messages.error(request, f'{field}: {err}')
    else:
        user_form = StudentRegistrationForm()
        profile_form = StudentProfileForm()
    return render(request, 'hostelapp/register.html', {
        'user_form':    user_form,
        'profile_form': profile_form,
        'blocks':       HostelBlock.objects.filter(is_active=True),
    })


def verify_otp(request):
    """Step 2: Enter OTP → create account."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    email = request.session.get('otp_email')
    if not email:
        messages.error(request, 'Session expired. Please register again.')
        return redirect('register')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp', '').strip()
        action      = request.POST.get('action', '')

        # Resend OTP
        if action == 'resend':
            otp = generate_otp()
            OTPVerification.objects.filter(email=email, is_used=False).delete()
            OTPVerification.objects.create(email=email, otp=otp)
            try:
                send_otp_email(email, otp)
                messages.success(request, f'New OTP sent to {email}.')
            except Exception as e:
                messages.error(request, f'Failed to resend OTP: {e}')
            return redirect('verify_otp')

        # Verify OTP
        try:
            otp_obj = OTPVerification.objects.filter(email=email, is_used=False).latest('created_at')
        except OTPVerification.DoesNotExist:
            messages.error(request, 'No OTP found. Please register again.')
            return redirect('register')

        if otp_obj.is_expired():
            messages.error(request, 'OTP has expired. Please request a new one.')
            return render(request, 'hostelapp/verify_otp.html', {'email': email})

        if otp_obj.otp != entered_otp:
            messages.error(request, 'Invalid OTP. Please try again.')
            return render(request, 'hostelapp/verify_otp.html', {'email': email})

        # OTP correct — now create the user
        post_data = request.session.get('reg_user_form', {})
        qd = QueryDict(mutable=True)
        qd.update(post_data)
        user_form    = StudentRegistrationForm(qd)
        profile_form = StudentProfileForm(qd)

        if user_form.is_valid() and profile_form.is_valid():
            user    = user_form.save()
            profile = profile_form.save(commit=False)
            profile.user = user
            # Save guardian fields manually since they are custom HTML inputs
            profile.guardian_name  = post_data.get('guardian_name', '')
            # BUG FIX: strip non-digits and enforce 10-digit guardian phone
            raw_gphone = post_data.get('guardian_phone', '')
            profile.guardian_phone = ''.join(filter(str.isdigit, raw_gphone))[:10]

            # Save hostel type and block
            profile.hostel_type = post_data.get('hostel_type', 'boys')
            block_id = post_data.get('block', '')
            if block_id:
                try:
                    profile.block = HostelBlock.objects.get(pk=block_id)
                except HostelBlock.DoesNotExist:
                    profile.block = None

            profile.save()
            otp_obj.is_used = True
            otp_obj.save()
            # Clean session
            for key in ['otp_email', 'reg_user_form', 'reg_has_photo']:
                request.session.pop(key, None)
            login(request, user)
            # BUG FIX: Profile photo cannot be stored in session (files are not serializable).
            # Show a message so student knows to upload it from their profile page.
            if request.session.get('reg_has_photo'):
                messages.info(request, '📸 Profile photo could not be saved during registration. Please upload it from your profile page.')
            messages.success(request, 'Email verified! Welcome to HostelHub.')
            return redirect('dashboard')
        else:
            # Show exact errors for debugging
            errors = []
            for field, errs in user_form.errors.items():
                errors.append(f"{field}: {', '.join(errs)}")
            for field, errs in profile_form.errors.items():
                errors.append(f"{field}: {', '.join(errs)}")
            error_msg = ' | '.join(errors) if errors else 'Form error.'
            messages.error(request, f'Registration failed: {error_msg}. Please register again.')
            return redirect('register')

    return render(request, 'hostelapp/verify_otp.html', {'email': email})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        role = request.POST.get('role', 'student')  # 'admin' or 'student'
        if form.is_valid():
            user = form.get_user()
            if role == 'admin':
                # Allow superadmin and warden (staff users)
                if not (user.is_staff or user.is_superuser):
                    messages.error(request, '❌ Access denied. You are not an admin or warden. Please use Student login.')
                    return render(request, 'hostelapp/login.html', {'form': form, 'role': role})
            else:
                # Check if user is actually a student
                if user.is_staff or user.is_superuser:
                    messages.error(request, '❌ You are an admin/warden. Please use Admin login.')
                    return render(request, 'hostelapp/login.html', {'form': form, 'role': role})
                # Check student profile exists
                try:
                    _ = user.student_profile
                except StudentProfile.DoesNotExist:
                    messages.error(request, '❌ No student profile found. Please register first.')
                    return render(request, 'hostelapp/login.html', {'form': form, 'role': role})
            login(request, user)
            messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
        role = 'student'
    return render(request, 'hostelapp/login.html', {'form': form, 'role': role})


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.info(request, 'You have been logged out.')
    return redirect('login')


# ── DASHBOARD ─────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    u = request.user
    perm_rooms    = can_manage_rooms(u)
    perm_allot    = can_manage_allotments(u)
    perm_compl    = can_manage_complaints(u)
    perm_students = can_view_students(u)
    has_any_perm  = is_admin(u) or perm_rooms or perm_allot or perm_compl or perm_students

    warden = is_warden(u)
    if has_any_perm:
        today = date.today()

        if is_warden(request.user):
            warden_block = HostelBlock.objects.filter(warden=request.user, is_active=True).first()
            total_students = StudentProfile.objects.filter(block=warden_block).count() if warden_block else 0
        else:
            total_students = StudentProfile.objects.count()
        allotted_students = RoomAllotment.objects.filter(is_active=True).values('student').distinct().count()
        total_rooms       = Room.objects.count()
        available_rooms   = Room.objects.filter(status='available').count()
        full_rooms        = Room.objects.filter(status='full').count()
        maintenance_rooms = Room.objects.filter(status='maintenance').count()

        # Complaints breakdown
        pending_complaints    = Complaint.objects.filter(status='pending').count()
        in_progress_complaints= Complaint.objects.filter(status='in_progress').count()
        resolved_complaints   = Complaint.objects.filter(status='resolved').count()

        # Today's attendance
        today_att     = Attendance.objects.filter(date=today)
        att_present   = today_att.filter(status='present').count()
        att_absent    = today_att.filter(status='absent').count()
        att_marked    = today_att.count()
        att_pct       = round((att_present / att_marked * 100) if att_marked > 0 else 0)

        # Leave requests
        pending_leaves = LeaveRequest.objects.filter(status='pending').count()

        # Room occupancy percentage for chart
        from django.db.models import Sum
        capacity_agg = Room.objects.aggregate(total=Sum('capacity'))
        total_capacity = capacity_agg['total'] or 0
        total_occupied = allotted_students
        occupancy_pct  = round((total_occupied / total_capacity * 100) if total_capacity > 0 else 0)

        # Block wise stats
        boys_blocks    = HostelBlock.objects.filter(block_type='boys', is_active=True)
        girls_blocks   = HostelBlock.objects.filter(block_type='girls', is_active=True)
        boys_students  = StudentProfile.objects.filter(hostel_type='boys').count()
        girls_students = StudentProfile.objects.filter(hostel_type='girls').count()
        boys_rooms     = Room.objects.filter(block__block_type='boys').count()
        girls_rooms    = Room.objects.filter(block__block_type='girls').count()

        context = {
            'total_students':       total_students,
            'allotted_students':    allotted_students,
            'unallotted_students':  total_students - allotted_students,
            'total_rooms':          total_rooms,
            'available_rooms':      available_rooms,
            'full_rooms':           full_rooms,
            'maintenance_rooms':    maintenance_rooms,
            'pending_complaints':   pending_complaints,
            'in_progress_complaints': in_progress_complaints,
            'resolved_complaints':  resolved_complaints,
            'recent_complaints':    Complaint.objects.filter(status='pending').order_by('-created_at')[:5],
            'recent_allotments':    RoomAllotment.objects.filter(is_active=True).order_by('-allotment_date')[:5],
            'notices':              Notice.objects.filter(is_active=True)[:3],
            'total_staff':          StaffMember.objects.filter(status='active').count(),
            # Attendance
            'att_present':  att_present,
            'att_absent':   att_absent,
            'att_marked':   att_marked,
            'att_pct':      att_pct,
            'today':        today,
            # Leave
            'pending_leaves': pending_leaves,
            # Occupancy
            'occupancy_pct':    occupancy_pct,
            'total_capacity':   total_capacity,
            'total_occupied':   total_occupied,
            # Block stats
            'boys_blocks':    boys_blocks,
            'girls_blocks':   girls_blocks,
            'boys_students':  boys_students,
            'girls_students': girls_students,
            'boys_rooms':     boys_rooms,
            'girls_rooms':    girls_rooms,
            # Permissions & roles
            'is_admin':     True,
            'is_warden':    warden,
            'is_superadmin': u.is_superuser,
            'perm_rooms':   perm_rooms,
            'perm_allot':   perm_allot,
            'perm_compl':   perm_compl,
            'perm_students': perm_students,
        }
    else:
        try:
            profile = request.user.student_profile
        except StudentProfile.DoesNotExist:
            return redirect('register')

        today     = date.today()
        month_str = today.strftime('%Y-%m')
        year, month = today.year, today.month

        # Student attendance this month
        att_records = Attendance.objects.filter(
            student=profile, date__year=year, date__month=month)
        att_total   = att_records.count()
        att_present = att_records.filter(status='present').count()
        att_pct     = round((att_present / att_total * 100) if att_total > 0 else 0)

        # Student leave summary
        my_leaves = LeaveRequest.objects.filter(student=profile).order_by('-created_at')[:3]
        pending_leave = LeaveRequest.objects.filter(student=profile, status='pending').count()

        context = {
            'profile':          profile,
            'allotment':        RoomAllotment.objects.filter(student=profile, is_active=True).first(),
            'my_complaints':    Complaint.objects.filter(student=profile).order_by('-created_at')[:5],
            'notices':          Notice.objects.filter(is_active=True)[:3],
            'att_total':        att_total,
            'att_present':      att_present,
            'att_pct':          att_pct,
            'month_str':        month_str,
            'my_leaves':        my_leaves,
            'pending_leave':    pending_leave,
            'is_admin':         False,
            'perm_rooms':       False,
            'perm_allot':       False,
            'perm_compl':       False,
            'perm_students':    False,
            'unread_notice_count': max(0,
                Notice.objects.filter(is_active=True).count() -
                NoticeRead.objects.filter(student=profile).count()),
        }
    return render(request, 'hostelapp/dashboard.html', context)


# ── STUDENT VIEWS ─────────────────────────────────────────────────────────────

@login_required
def profile_view(request):
    try:
        profile = request.user.student_profile
    except StudentProfile.DoesNotExist:
        return redirect('register')
    if request.method == 'POST':
        form = StudentProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            updated_profile = form.save(commit=False)
            # BUG FIX: guardian fields are plain HTML inputs (not part of ModelForm),
            # so they must be saved manually from POST data
            guardian_name  = request.POST.get('guardian_name', '').strip()
            guardian_phone = request.POST.get('guardian_phone', '').strip()
            # BUG FIX: strip non-digits, enforce max 10 digits
            guardian_phone = ''.join(filter(str.isdigit, guardian_phone))[:10]
            if guardian_name:
                updated_profile.guardian_name  = guardian_name
            if guardian_phone:
                updated_profile.guardian_phone = guardian_phone
            updated_profile.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
    else:
        form = StudentProfileForm(instance=profile)
    return render(request, 'hostelapp/profile.html', {'form': form, 'profile': profile})


@login_required
@user_passes_test(can_view_students)
def student_list(request):
    query              = request.GET.get('q', '')
    hostel_type_filter = request.GET.get('hostel_type', '')
    block_filter       = request.GET.get('block', '')

    if is_warden(request.user):
        warden_block = HostelBlock.objects.filter(
            warden=request.user, is_active=True
        ).first()
        if warden_block:
            students = StudentProfile.objects.select_related('user', 'block').filter(
                block=warden_block
            ).order_by('roll_number')
        else:
            students = StudentProfile.objects.none()
    else:
        students = StudentProfile.objects.select_related('user', 'block').all().order_by('roll_number')

    if query:
        students = students.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(roll_number__icontains=query) |
            Q(course__icontains=query) |
            Q(user__email__icontains=query)
        )
    if hostel_type_filter:
        students = students.filter(hostel_type=hostel_type_filter)
    if block_filter:
        students = students.filter(block__id=block_filter)

    paginator   = Paginator(students, 20)
    page_number = request.GET.get('page')
    page_obj    = paginator.get_page(page_number)

    return render(request, 'hostelapp/student_list.html', {
        'students':           page_obj,
        'page_obj':           page_obj,
        'query':              query,
        'hostel_type_filter': hostel_type_filter,
        'block_filter':       block_filter,
        'blocks':             HostelBlock.objects.filter(is_active=True),
    })


# ── ROOM VIEWS ────────────────────────────────────────────────────────────────

@login_required
def room_list(request):
    block_filter = request.GET.get('block', '')
    if is_warden(request.user):
        warden_block = HostelBlock.objects.filter(
            warden=request.user, is_active=True
        ).first()
        if warden_block:
            rooms = Room.objects.select_related('block').filter(
                block=warden_block
            ).order_by('floor', 'room_number')
            # Warden only sees their own block in filter
            blocks = HostelBlock.objects.filter(pk=warden_block.pk)
        else:
            rooms  = Room.objects.none()
            blocks = HostelBlock.objects.none()
    else:
        rooms = Room.objects.select_related('block').all().order_by('floor', 'room_number')
        if block_filter:
            rooms = rooms.filter(block__id=block_filter)
        blocks = HostelBlock.objects.filter(is_active=True)
    return render(request, 'hostelapp/room_list.html', {
        'rooms':        rooms,
        'blocks':       blocks,
        'block_filter': block_filter,
    })


@login_required
@user_passes_test(can_manage_rooms)
def room_add(request):
    # Get warden's block if warden
    warden_block = None
    if is_warden(request.user):
        warden_block = HostelBlock.objects.filter(
            warden=request.user, is_active=True
        ).first()
        if not warden_block:
            messages.error(request, 'You are not assigned to any block.')
            return redirect('room_list')

    if request.method == 'POST':
        form = RoomForm(request.POST)
        if form.is_valid():
            room = form.save(commit=False)
            # Auto assign warden's block
            if is_warden(request.user) and warden_block:
                room.block = warden_block
            room.save()
            room.update_status()
            messages.success(request, 'Room added successfully.')
            return redirect('room_list')
    else:
        form = RoomForm()
    return render(request, 'hostelapp/room_form.html', {
        'form':         form,
        'title':        'Add Room',
        'warden_block': warden_block,
        'is_warden':    is_warden(request.user),
    })

@login_required
def room_detail(request, pk):
    room = get_object_or_404(Room, pk=pk)
    allotments = room.allotments.filter(is_active=True).select_related('student__user')
    return render(request, 'hostelapp/room_detail.html', {'room': room, 'allotments': allotments})

@login_required
@user_passes_test(can_manage_rooms)
def room_edit(request, pk):
    room = get_object_or_404(Room, pk=pk)
    warden_block = None
    if is_warden(request.user):
        warden_block = HostelBlock.objects.filter(
            warden=request.user, is_active=True
        ).first()

    if request.method == 'POST':
        form = RoomForm(request.POST, instance=room)
        if form.is_valid():
            updated_room = form.save(commit=False)
            # Always preserve block for warden
            if is_warden(request.user):
                updated_room.block = warden_block or room.block
            elif not request.POST.get('block'):
                updated_room.block = room.block
            updated_room.save()
            updated_room.update_status()
            messages.success(request, 'Room updated successfully.')
            return redirect('room_list')
    else:
        form = RoomForm(instance=room)
    return render(request, 'hostelapp/room_form.html', {
        'form':         form,
        'title':        'Edit Room',
        'room':         room,
        'warden_block': warden_block,
        'is_warden':    is_warden(request.user),
    })

# ── ALLOTMENT VIEWS ───────────────────────────────────────────────────────────

@login_required
@user_passes_test(can_manage_allotments)
def allotment_list(request):
    if is_warden(request.user):
        warden_block = HostelBlock.objects.filter(warden=request.user, is_active=True).first()
        if warden_block:
            allotments = RoomAllotment.objects.filter(
                is_active=True,
                student__block=warden_block
            ).select_related('student__user', 'room').order_by('-allotment_date')
        else:
            allotments = RoomAllotment.objects.none()
    else:
        allotments = RoomAllotment.objects.filter(is_active=True).select_related('student__user', 'room').order_by('-allotment_date')
    return render(request, 'hostelapp/allotment_list.html', {'allotments': allotments})


@login_required
@user_passes_test(can_manage_allotments)
def allotment_add(request):
    warden_block = None
    if is_warden(request.user):
        warden_block = HostelBlock.objects.filter(warden=request.user, is_active=True).first()

    if request.method == 'POST':
        form = RoomAllotmentForm(request.POST, warden_block=warden_block)
        if form.is_valid():
            allotment = form.save()
            allotment.room.update_status()
            create_notification(
                allotment.student.user, 'allotment',
                f'🏠 Room Allotted: Room {allotment.room.room_number}',
                f'You have been allotted Room {allotment.room.room_number} (Floor {allotment.room.floor}). Monthly fee: Rs.{allotment.room.monthly_fee}',
                '/rooms/'
            )
            messages.success(request, 'Room allotted successfully.')
            return redirect('allotment_list')
    else:
        form = RoomAllotmentForm(warden_block=warden_block)
    return render(request, 'hostelapp/allotment_form.html', {'form': form})


@login_required
@user_passes_test(can_manage_allotments)
def allotment_vacate(request, pk):
    allotment = get_object_or_404(RoomAllotment, pk=pk)
    if request.method == 'POST':
        allotment.is_active = False
        allotment.vacating_date = timezone.now().date()
        allotment.save()
        allotment.room.update_status()
        create_notification(
            allotment.student.user, 'allotment',
            f'🏠 Room Vacated: Room {allotment.room.room_number}',
            f'Your allotment for Room {allotment.room.room_number} has been vacated.',
            '/rooms/'
        )
        messages.success(request, f'Room vacated for {allotment.student}.')
        return redirect('allotment_list')
    return render(request, 'hostelapp/allotment_vacate.html', {'allotment': allotment})


# ── COMPLAINT VIEWS ───────────────────────────────────────────────────────────

@login_required
def complaint_list(request):
    admin = is_admin(request.user) or can_manage_rooms(request.user) or can_manage_complaints(request.user)
    if admin:
        if is_warden(request.user):
            warden_block = HostelBlock.objects.filter(warden=request.user, is_active=True).first()
            if warden_block:
                complaints = Complaint.objects.filter(student__block=warden_block).select_related('student__user', 'room')
            else:
                complaints = Complaint.objects.none()
        else:
            complaints = Complaint.objects.all().select_related('student__user', 'room')
        sort = request.GET.get('sort', '')
        status_filter = request.GET.get('status', '')
        if status_filter:
            complaints = complaints.filter(status=status_filter)
        # BUG FIX: always annotate upvote_count so template {{ complaint.upvote_count }} never crashes
        if sort == 'upvotes':
            complaints = complaints.annotate(upvote_count=Count('upvotes')).order_by('-upvote_count')
        else:
            complaints = complaints.annotate(upvote_count=Count('upvotes')).order_by('-created_at')
        upvoted_ids = set()
        return render(request, 'hostelapp/complaint_list.html', {
            'complaints':  complaints,
            'is_admin':    True,
            'upvoted_ids': upvoted_ids,
            'sort':        sort,
        })
    else:
        try:
            profile = request.user.student_profile
            complaints = Complaint.objects.filter(student=profile).select_related('student__user', 'room').order_by('-created_at')
            status_filter = request.GET.get('status', '')
            if status_filter:
                complaints = complaints.filter(status=status_filter)
            upvoted_ids = set(ComplaintUpvote.objects.filter(student=profile).values_list('complaint_id', flat=True))
            # Annotate upvote count
            complaints = complaints.annotate(upvote_count=Count('upvotes'))
            for c in complaints:
                c.user_upvoted = c.id in upvoted_ids
        except StudentProfile.DoesNotExist:
            complaints  = Complaint.objects.none()
            upvoted_ids = set()

        # Pass empty form for new complaint tab
        form = ComplaintForm()
        show_form = request.GET.get('tab') == 'new'

        return render(request, 'hostelapp/complaint_list.html', {
            'complaints':  complaints,
            'is_admin':    False,
            'upvoted_ids': upvoted_ids,
            'sort':        '',
            'form':        form,
            'show_form':   show_form,
        })


@login_required
def complaint_add(request):
    try:
        profile = request.user.student_profile
    except StudentProfile.DoesNotExist:
        messages.error(request, 'You need a student profile to file a complaint.')
        return redirect('dashboard')
    if request.method == 'POST':
        form = ComplaintForm(request.POST)
        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.student = profile
            allotment = RoomAllotment.objects.filter(student=profile, is_active=True).first()
            if allotment:
                complaint.room = allotment.room
            complaint.save()
            # Notify all admins and wardens
            for admin_user in UserModel.objects.filter(is_staff=True):
                create_notification(
                    admin_user, 'complaint',
                    f'📢 New Complaint: {complaint.title}',
                    f'{profile.user.get_full_name()} ({profile.roll_number}) filed a {complaint.get_priority_display()} priority complaint in {complaint.get_category_display()}.',
                    f'/complaints/{complaint.pk}/'
                )
            messages.success(request, 'Complaint submitted successfully.')
            return redirect('complaint_list')
    else:
        form = ComplaintForm()
    return render(request, 'hostelapp/complaint_form.html', {'form': form})

@login_required
def complaint_detail(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk)
    if not is_admin(request.user):
        try:
            if complaint.student != request.user.student_profile:
                messages.error(request, 'Access denied.')
                return redirect('complaint_list')
        except StudentProfile.DoesNotExist:
            return redirect('dashboard')

    update_form = None
    if is_admin(request.user) or can_manage_rooms(request.user) or can_manage_complaints(request.user):
        if request.method == 'POST':
            update_form = ComplaintUpdateForm(request.POST, instance=complaint)
            if update_form.is_valid():
                c = update_form.save(commit=False)
                if c.status == 'resolved':
                    c.resolved_at = timezone.now()
                c.save()
                messages.success(request, 'Complaint updated.')
                # Notify student
                # BUG FIX: was missing 'message' argument — caused TypeError
                status_emoji = {'pending':'⏳','in_progress':'🔧','resolved':'✅','rejected':'❌'}.get(c.status, '📋')
                create_notification(
                    complaint.student.user, 'complaint',
                    f'{status_emoji} Complaint {c.get_status_display()}: {complaint.title}',
                    f'Your complaint "{complaint.title}" status changed to {c.get_status_display()}.' +
                    (f' Admin remarks: {c.admin_remarks}' if c.admin_remarks else ''),
                    f'/complaints/{pk}/'
                )
                return redirect('complaint_detail', pk=pk)
        else:
            update_form = ComplaintUpdateForm(instance=complaint)

    return render(request, 'hostelapp/complaint_detail.html', {
        'complaint': complaint,
        'update_form': update_form,
        'is_admin': is_admin(request.user)
    })


# ── NOTICE VIEWS ──────────────────────────────────────────────────────────────

@login_required
def notice_list(request):
    notices = Notice.objects.filter(is_active=True)
    unread_ids = []
    if not is_admin(request.user):
        try:
            profile = request.user.student_profile
            read_ids = NoticeRead.objects.filter(student=profile).values_list('notice_id', flat=True)
            unread_ids = list(notices.exclude(id__in=read_ids).values_list('id', flat=True))
        except StudentProfile.DoesNotExist:
            pass
    return render(request, 'hostelapp/notice_list.html', {
        'notices': notices,
        'unread_ids': unread_ids,
        'is_admin': is_admin(request.user),
    })


@login_required
def notice_add(request):
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('notice_list')
    if request.method == 'POST':
        form = NoticeForm(request.POST, request.FILES)
        if form.is_valid():
            notice = form.save(commit=False)
            notice.posted_by = request.user
            notice.save()
            # Notify all students
            priority_label = '🔴 URGENT' if notice.priority == 'urgent' else '📋 Normal'
            notify_all_students('notice', f'{priority_label} Notice: {notice.title}',
                notice.content[:100], '/notices/')
            messages.success(request, 'Notice posted successfully.')
            return redirect('notice_list')
    else:
        form = NoticeForm()
    return render(request, 'hostelapp/notice_form.html', {'form': form, 'title': 'Post Notice'})


@login_required
def notice_edit(request, pk):
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('notice_list')
    notice = get_object_or_404(Notice, pk=pk)
    if request.method == 'POST':
        form = NoticeForm(request.POST, request.FILES, instance=notice)
        if form.is_valid():
            form.save()
            messages.success(request, 'Notice updated.')
            return redirect('notice_list')
    else:
        form = NoticeForm(instance=notice)
    return render(request, 'hostelapp/notice_form.html', {'form': form, 'title': 'Edit Notice', 'notice': notice})


@login_required
def notice_delete(request, pk):
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('notice_list')
    notice = get_object_or_404(Notice, pk=pk)
    if request.method == 'POST':
        notice.is_active = False
        notice.save()
        messages.success(request, 'Notice removed.')
    return redirect('notice_list')


@login_required
def notice_mark_read(request, pk):
    """Mark a notice as read for the current student."""
    notice = get_object_or_404(Notice, pk=pk)
    try:
        profile = request.user.student_profile
        NoticeRead.objects.get_or_create(student=profile, notice=notice)
        messages.success(request, 'Notice marked as read.')
    except StudentProfile.DoesNotExist:
        pass
    return redirect('notice_list')


@login_required
def notice_mark_all_read(request):
    """Mark all notices as read for current student."""
    try:
        profile = request.user.student_profile
        notices = Notice.objects.filter(is_active=True)
        # Get already-read notice IDs to avoid duplicates
        already_read = NoticeRead.objects.filter(
            student=profile).values_list('notice_id', flat=True)
        # Bulk create only the unread ones — much faster than loop
        unread = notices.exclude(id__in=already_read)
        NoticeRead.objects.bulk_create([
            NoticeRead(student=profile, notice=n) for n in unread
        ], ignore_conflicts=True)
        messages.success(request, 'All notices marked as read.')
    except StudentProfile.DoesNotExist:
        pass
    return redirect('notice_list')



@login_required
def staff_list(request):
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    staff = StaffMember.objects.all()
    # filter
    role   = request.GET.get('role', '')
    status = request.GET.get('status', '')
    search = request.GET.get('q', '')
    if role:
        staff = staff.filter(role=role)
    if status:
        staff = staff.filter(status=status)
    if search:
        staff = staff.filter(name__icontains=search)
    return render(request, 'hostelapp/staff_list.html', {
        'staff': staff,
        'role_choices': StaffMember.ROLE_CHOICES,
        'status_choices': StaffMember.STATUS_CHOICES,
        'selected_role': role,
        'selected_status': status,
        'search': search,
        'total_staff': StaffMember.objects.filter(status='active').count(),
    })


@login_required
def staff_add(request):
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('staff_list')
    if request.method == 'POST':
        form = StaffMemberForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Staff member added successfully.')
            return redirect('staff_list')
    else:
        form = StaffMemberForm()
    return render(request, 'hostelapp/staff_form.html', {'form': form, 'title': 'Add Staff Member'})


@login_required
def staff_detail(request, pk):
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    member = get_object_or_404(StaffMember, pk=pk)
    return render(request, 'hostelapp/staff_detail.html', {'member': member})


@login_required
def staff_edit(request, pk):
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('staff_list')
    member = get_object_or_404(StaffMember, pk=pk)
    if request.method == 'POST':
        form = StaffMemberForm(request.POST, request.FILES, instance=member)
        if form.is_valid():
            form.save()
            messages.success(request, 'Staff member updated.')
            return redirect('staff_detail', pk=pk)
    else:
        form = StaffMemberForm(instance=member)
    return render(request, 'hostelapp/staff_form.html', {'form': form, 'title': 'Edit Staff Member', 'member': member})


@login_required
def staff_delete(request, pk):
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('staff_list')
    member = get_object_or_404(StaffMember, pk=pk)
    if request.method == 'POST':
        member.delete()
        messages.success(request, 'Staff member removed.')
        return redirect('staff_list')
    return render(request, 'hostelapp/staff_confirm_delete.html', {'member': member})

# ── EXPORT VIEWS ──────────────────────────────────────────────────────────────


def make_excel_styles():
    header_font  = Font(bold=True, color="FFFFFF", size=11)
    header_fill  = PatternFill("solid", fgColor="1a1a2e")
    center       = Alignment(horizontal="center", vertical="center")
    wrap         = Alignment(wrap_text=True, vertical="center")
    thin         = Side(style="thin", color="DDDDDD")
    border       = Border(left=thin, right=thin, top=thin, bottom=thin)
    return header_font, header_fill, center, wrap, border


def style_excel_header(ws, headers, col_widths):
    header_font, header_fill, center, _, border = make_excel_styles()
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font       = header_font
        cell.fill       = header_fill
        cell.alignment  = center
        cell.border     = border
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    ws.row_dimensions[1].height = 22


def style_excel_rows(ws, start_row, end_row, col_count):
    _, _, _, wrap, border = make_excel_styles()
    alt_fill = PatternFill("solid", fgColor="F0F4FF")
    for row in range(start_row, end_row + 1):
        fill = alt_fill if row % 2 == 0 else None
        for col in range(1, col_count + 1):
            cell = ws.cell(row=row, column=col)
            cell.alignment = wrap
            cell.border    = border
            if fill:
                cell.fill = fill
        ws.row_dimensions[row].height = 18


# ── PDF helper ────────────────────────────────────────────────────────────────
def make_pdf_table_style(header_color=colors.HexColor("#1a1a2e")):
    return TableStyle([
        ('BACKGROUND',  (0, 0), (-1, 0),  header_color),
        ('TEXTCOLOR',   (0, 0), (-1, 0),  colors.white),
        ('FONTNAME',    (0, 0), (-1, 0),  'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1, 0),  9),
        ('ALIGN',       (0, 0), (-1, 0),  'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F4FF")]),
        ('FONTNAME',    (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',    (0, 1), (-1, -1), 8),
        ('ALIGN',       (0, 1), (-1, -1), 'LEFT'),
        ('VALIGN',      (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID',        (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ('ROWHEIGHT',   (0, 0), (-1, -1), 18),
        ('TOPPADDING',  (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING',(0,0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',(0, 0), (-1, -1), 6),
    ])


def pdf_title_style():
    styles = getSampleStyleSheet()
    title  = ParagraphStyle('title', parent=styles['Title'],
                             fontSize=16, textColor=colors.HexColor("#1a1a2e"),
                             spaceAfter=4)
    sub    = ParagraphStyle('sub', parent=styles['Normal'],
                             fontSize=9, textColor=colors.HexColor("#6c757d"),
                             spaceAfter=12)
    return title, sub


# ── MAIN EXPORT VIEW ──────────────────────────────────────────────────────────
@login_required
def export_data(request):
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard')

    data_type = request.GET.get('type', 'students')
    fmt       = request.GET.get('format', 'excel')

    if fmt == 'excel':
        return export_excel(data_type)
    else:
        return export_pdf(data_type, request)

def export_excel(data_type):
    wb = Workbook()
    ws = wb.active

    if data_type == 'students':
        ws.title = "Students"
        headers = ["#", "Full Name", "Username", "Email", "Roll Number",
                   "Phone", "Gender", "Course", "Year", "Guardian Name",
                   "Guardian Phone", "Joined Date"]
        col_widths = [4, 20, 16, 28, 14, 14, 10, 12, 6, 20, 14, 14]
        style_excel_header(ws, headers, col_widths)
        students = StudentProfile.objects.select_related('user').all().order_by('roll_number')
        for i, s in enumerate(students, 1):
            ws.append([
                i, s.user.get_full_name() or s.user.username,
                s.user.username, s.user.email or '-',
                s.roll_number, s.phone, s.get_gender_display(),
                s.course, s.year_of_study,
                s.guardian_name or '-', s.guardian_phone or '-',
                s.created_at.strftime('%d-%m-%Y') if s.created_at else '-',
            ])
        style_excel_rows(ws, 2, ws.max_row, len(headers))
        filename = "HostelHub_Students.xlsx"

    elif data_type == 'allotments':
        ws.title = "Allotments"
        headers = ["#", "Student Name", "Roll Number", "Room No", "Floor",
                   "Room Type", "Monthly Fee", "Allotment Date", "Status", "Remarks"]
        col_widths = [4, 20, 14, 10, 8, 14, 14, 16, 10, 24]
        style_excel_header(ws, headers, col_widths)
        allotments = RoomAllotment.objects.select_related('student__user', 'room').order_by('-allotment_date')
        for i, a in enumerate(allotments, 1):
            ws.append([
                i, a.student.user.get_full_name() or a.student.user.username,
                a.student.roll_number, a.room.room_number,
                f"Floor {a.room.floor}", a.room.get_room_type_display(),
                f"Rs. {a.room.monthly_fee}", a.allotment_date.strftime('%d-%m-%Y'),
                "Active" if a.is_active else "Vacated",
                a.remarks or '-',
            ])
        style_excel_rows(ws, 2, ws.max_row, len(headers))
        filename = "HostelHub_Allotments.xlsx"

    elif data_type == 'complaints':
        ws.title = "Complaints"
        headers = ["#", "Student", "Roll No", "Title", "Category",
                   "Priority", "Status", "Filed On", "Resolved On", "Admin Remarks"]
        col_widths = [4, 18, 12, 24, 14, 10, 12, 14, 14, 28]
        style_excel_header(ws, headers, col_widths)
        complaints = Complaint.objects.select_related('student__user').order_by('-created_at')
        for i, c in enumerate(complaints, 1):
            # BUG FIX: was missing admin_remarks value in row data (had 10 headers but 9 values)
            ws.append([
                i, c.student.user.get_full_name() or c.student.user.username,
                c.student.roll_number, c.title,
                c.get_category_display(), c.get_priority_display(),
                c.get_status_display(),
                c.created_at.strftime('%d-%m-%Y'),
                c.resolved_at.strftime('%d-%m-%Y') if c.resolved_at else '-',
                c.admin_remarks or '-',
            ])
        style_excel_rows(ws, 2, ws.max_row, len(headers))
        filename = "HostelHub_Complaints.xlsx"

    elif data_type == 'staff':
        ws.title = "Staff"
        headers = ["#", "Name", "Role", "Phone", "Email",
                   "Shift", "Status", "Joined Date", "Address"]
        col_widths = [4, 20, 18, 14, 28, 22, 12, 14, 30]
        style_excel_header(ws, headers, col_widths)
        staff = StaffMember.objects.all().order_by('name')
        for i, s in enumerate(staff, 1):
            ws.append([
                i, s.name, s.get_role_display(),
                s.phone, s.email or '-',
                s.shift or '-', s.get_status_display(),
                s.joined_date.strftime('%d-%m-%Y') if s.joined_date else '-',
                s.address or '-',
            ])
        style_excel_rows(ws, 2, ws.max_row, len(headers))
        filename = "HostelHub_Staff.xlsx"

    else:
        filename = "HostelHub_Export.xlsx"

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def export_pdf(data_type, request=None):
    buffer   = io.BytesIO()
    doc      = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                                  leftMargin=1.5*cm, rightMargin=1.5*cm,
                                  topMargin=1.5*cm, bottomMargin=1.5*cm)
    title_style, sub_style = pdf_title_style()
    elements = []
    now_str  = timezone.now().strftime('%d %B %Y, %I:%M %p')

    if data_type == 'students':
        elements.append(Paragraph("HostelHub — Students List", title_style))
        elements.append(Paragraph(f"Exported on {now_str}", sub_style))
        elements.append(Spacer(1, 0.3*cm))
        headers = [["#", "Full Name", "Roll No", "Email", "Phone", "Gender", "Course", "Year", "Joined"]]
        students = StudentProfile.objects.select_related('user').all().order_by('roll_number')
        data = headers + [
            [i, s.user.get_full_name() or s.user.username,
             s.roll_number, s.user.email or '-', s.phone,
             s.get_gender_display(), s.course, s.year_of_study,
             s.created_at.strftime('%d-%m-%Y') if s.created_at else '-']
            for i, s in enumerate(students, 1)
        ]
        col_widths = [1*cm, 4.5*cm, 3*cm, 5*cm, 3*cm, 2*cm, 3*cm, 1.5*cm, 3*cm]
        filename = "HostelHub_Students.pdf"

    elif data_type == 'allotments':
        elements.append(Paragraph("HostelHub — Room Allotments", title_style))
        elements.append(Paragraph(f"Exported on {now_str}", sub_style))
        elements.append(Spacer(1, 0.3*cm))
        headers = [["#", "Student Name", "Roll No", "Room No", "Floor", "Type", "Fee", "Date", "Status"]]
        allotments = RoomAllotment.objects.select_related('student__user', 'room').order_by('-allotment_date')
        data = headers + [
            [i, a.student.user.get_full_name() or a.student.user.username,
             a.student.roll_number, a.room.room_number,
             f"F{a.room.floor}", a.room.get_room_type_display(),
             f"Rs.{a.room.monthly_fee}", a.allotment_date.strftime('%d-%m-%Y'),
             "Active" if a.is_active else "Vacated"]
            for i, a in enumerate(allotments, 1)
        ]
        col_widths = [1*cm, 4.5*cm, 3*cm, 2.5*cm, 2*cm, 3*cm, 3*cm, 3*cm, 2.5*cm]
        filename = "HostelHub_Allotments.pdf"

    elif data_type == 'complaints':
        elements.append(Paragraph("HostelHub — Complaints Report", title_style))
        elements.append(Paragraph(f"Exported on {now_str}", sub_style))
        elements.append(Spacer(1, 0.3*cm))
        headers = [["#", "Student", "Roll No", "Title", "Category", "Priority", "Status", "Filed On"]]
        complaints = Complaint.objects.select_related('student__user').order_by('-created_at')
        data = headers + [
            [i, c.student.user.get_full_name() or c.student.user.username,
             c.student.roll_number, c.title[:30],
             c.get_category_display(), c.get_priority_display(),
             c.get_status_display(), c.created_at.strftime('%d-%m-%Y')]
            for i, c in enumerate(complaints, 1)
        ]
        col_widths = [1*cm, 4*cm, 3*cm, 5.5*cm, 3*cm, 2.5*cm, 3*cm, 3*cm]
        filename = "HostelHub_Complaints.pdf"

    elif data_type == 'staff':
        elements.append(Paragraph("HostelHub — Staff Directory", title_style))
        elements.append(Paragraph(f"Exported on {now_str}", sub_style))
        elements.append(Spacer(1, 0.3*cm))
        headers = [["#", "Name", "Role", "Phone", "Email", "Shift", "Status", "Joined"]]
        staff = StaffMember.objects.all().order_by('name')
        data = headers + [
            [i, s.name, s.get_role_display(), s.phone,
             s.email or '-', s.shift or '-',
             s.get_status_display(),
             s.joined_date.strftime('%d-%m-%Y') if s.joined_date else '-']
            for i, s in enumerate(staff, 1)
        ]
        col_widths = [1*cm, 4.5*cm, 3.5*cm, 3*cm, 5*cm, 4*cm, 2.5*cm, 3*cm]
        filename = "HostelHub_Staff.pdf"
    else:
        data, col_widths, filename = [[["No data"]]], [10*cm], "HostelHub_Export.pdf"

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(make_pdf_table_style())
    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ── ATTENDANCE VIEWS ──────────────────────────────────────────────────────────


@login_required
def attendance_list(request):
    """Admin/Warden: view attendance by date. Student: view own attendance."""
    # BUG FIX: wardens have attendance permissions but is_admin() alone may miss them.
    # Use the same has_any_perm logic as dashboard so wardens see the admin view.
    user_is_admin = is_admin(request.user) or can_manage_allotments(request.user) or \
                    request.user.has_perm('hostelapp.add_attendance') or \
                    request.user.has_perm('hostelapp.change_attendance') or \
                    request.user.has_perm('hostelapp.view_studentprofile')
    if user_is_admin:
        # Date filter
        date_str = request.GET.get('date', str(date.today()))
        try:
            sel_date = date.fromisoformat(date_str)
        except ValueError:
            sel_date = date.today()

        if is_warden(request.user):
            warden_block = HostelBlock.objects.filter(warden=request.user, is_active=True).first()
            if warden_block:
                students = StudentProfile.objects.select_related('user').filter(block=warden_block).order_by('roll_number')
            else:
                students = StudentProfile.objects.none()
        else:
            students = StudentProfile.objects.select_related('user').order_by('roll_number')
        attendance  = Attendance.objects.filter(date=sel_date).select_related('student')
        att_map     = {a.student_id: a for a in attendance}

        rows = []
        for s in students:
            att = att_map.get(s.id)
            rows.append({
                'student': s,
                'status':  att.status if att else None,
                'remarks': att.remarks if att else '',
                'marked':  att is not None,
            })

        stats = {
            'total_students': students.count(),
            'marked_today':   attendance.count(),
            'present_today':  attendance.filter(status='present').count(),
            'absent_today':   attendance.filter(status='absent').count(),
        }

        return render(request, 'hostelapp/attendance_list.html', {
            'rows':     rows,
            'sel_date': sel_date,
            'today':    date.today(),
            'stats':    stats,
            'stats_list': [
                ('Total Students',  stats['total_students'],  '#3b82f6'),
                ('Marked Today',    stats['marked_today'],    '#f59e0b'),
                ('Present Today',   stats['present_today'],   '#10b981'),
                ('Absent Today',    stats['absent_today'],    '#ef4444'),
            ],
        })
    else:
        # Student view — own attendance
        try:
            profile = request.user.student_profile
        except StudentProfile.DoesNotExist:
            return redirect('dashboard')

        month_str = request.GET.get('month', date.today().strftime('%Y-%m'))
        try:
            year, month = map(int, month_str.split('-'))
        except Exception:
            year, month  = date.today().year, date.today().month

        records = Attendance.objects.filter(
            student=profile,
            date__year=year,
            date__month=month,
        ).order_by('date')

        total   = records.count()
        present = records.filter(status='present').count()
        absent  = records.filter(status='absent').count()
        pct     = round((present / total * 100) if total > 0 else 0)

        return render(request, 'hostelapp/attendance_student.html', {
            'records':   records,
            'month_str': month_str,
            'year':      year,
            'month':     month,
            'total':     total,
            'present':   present,
            'absent':    absent,
            'pct':       pct,
        })


@login_required
def attendance_mark(request):
    """Admin/Warden: mark/update attendance for a date (bulk POST)."""
    # BUG FIX: was only checking is_admin(), wardens with attendance perms were blocked
    can_mark = is_admin(request.user) or request.user.has_perm('hostelapp.add_attendance') or \
               request.user.has_perm('hostelapp.change_attendance')
    if not can_mark:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')

    if request.method == 'POST':
        date_str = request.POST.get('date', str(date.today()))
        try:
            sel_date = date.fromisoformat(date_str)
        except ValueError:
            sel_date = date.today()

        # Block future dates
        if sel_date > date.today():
            messages.error(request, 'Cannot mark attendance for future dates.')
            return redirect('attendance_list')

        # BUG FIX: was querying students twice
        if is_warden(request.user):
            warden_block = HostelBlock.objects.filter(warden=request.user, is_active=True).first()
            students = list(StudentProfile.objects.filter(block=warden_block).select_related('user')) if warden_block else []
        else:
            students = list(StudentProfile.objects.all().select_related('user'))
        for student in students:
            status  = request.POST.get(f'status_{student.id}', 'absent')
            remarks = request.POST.get(f'remarks_{student.id}', '')
            if status not in ['present', 'absent']:
                status = 'absent'
            Attendance.objects.update_or_create(
                student=student,
                date=sel_date,
                defaults={
                    'status':    status,
                    'remarks':   remarks,
                    'marked_by': request.user,
                }
            )
        count = len(students)

        # Notify each student
        for student in students:
            status = request.POST.get(f'status_{student.id}', 'absent')
            emoji  = '✅' if status == 'present' else '❌'
            create_notification(
                student.user, 'attendance',
                f'{emoji} Attendance: {sel_date.strftime("%d %B %Y")}',
                f'Your attendance for {sel_date.strftime("%d %B %Y")} has been marked as: {status.capitalize()}',
                '/attendance/'
            )
        messages.success(request, f'Attendance marked for {count} students on {sel_date.strftime("%d %B %Y")}.')
        return redirect(f'/attendance/?date={sel_date}')

    return redirect('attendance_list')


@login_required
def attendance_report(request):
    """Admin/Warden: monthly attendance summary per student."""
    # BUG FIX: was only checking is_admin() — wardens with attendance perms were blocked
    can_view = is_admin(request.user) or \
               request.user.has_perm('hostelapp.view_attendance') or \
               request.user.has_perm('hostelapp.add_attendance')
    if not can_view:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')

    month_str = request.GET.get('month', date.today().strftime('%Y-%m'))
    try:
        year, month = map(int, month_str.split('-'))
    except Exception:
        year, month = date.today().year, date.today().month

    if is_warden(request.user):
        warden_block = HostelBlock.objects.filter(
            warden=request.user, is_active=True
        ).first()
        if warden_block:
            students = StudentProfile.objects.select_related('user').filter(
                block=warden_block
            ).order_by('roll_number')
        else:
            students = StudentProfile.objects.none()
    else:
        students = StudentProfile.objects.select_related('user').order_by('roll_number')
    # Fix N+1: get all attendance for this month in one query, then group in Python
    all_records = Attendance.objects.filter(
        date__year=year, date__month=month
    ).values('student_id', 'status')

    # Build lookup: student_id -> {present, absent, total}
    att_map = defaultdict(lambda: {'present': 0, 'absent': 0})
    for r in all_records:
        att_map[r['student_id']][r['status']] += 1

    rows = []
    for s in students:
        data    = att_map[s.id]
        present = data['present']
        absent  = data['absent']
        total   = present + absent
        pct     = round((present / total * 100) if total > 0 else 0)
        rows.append({'student': s, 'total': total,
                     'present': present, 'absent': absent, 'pct': pct})

    month_date = date_cls(year, month, 1)
    return render(request, 'hostelapp/attendance_report.html', {
        'rows': rows, 'month_str': month_date, 'year': year, 'month': month,
    })


# ── COMPLAINT UPVOTE ──────────────────────────────────────────────────────────

@login_required
def complaint_upvote(request, pk):
    """Toggle upvote on a complaint. Students only."""
    if request.method != 'POST':
        return redirect('complaint_list')

    complaint = get_object_or_404(Complaint, pk=pk)

    try:
        profile = request.user.student_profile
    except StudentProfile.DoesNotExist:
        messages.error(request, 'Students only.')
        return redirect('complaint_list')

    # Cannot upvote your own complaint
    if complaint.student == profile:
        messages.warning(request, 'You cannot upvote your own complaint.')
        return redirect('complaint_list')

    existing = ComplaintUpvote.objects.filter(complaint=complaint, student=profile).first()
    if existing:
        existing.delete()
        # BUG FIX: was returning JsonResponse but template uses plain form POST.
        # Now returns redirect so page reloads correctly.
    else:
        ComplaintUpvote.objects.create(complaint=complaint, student=profile)

    # If request is AJAX/fetch, return JSON; otherwise redirect (form POST from template)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
       request.content_type == 'application/json':
        count   = complaint.upvotes.count()
        upvoted = not bool(existing)
        return JsonResponse({'upvoted': upvoted, 'count': count})

    return redirect('complaint_list')


# ── MESSAGING VIEWS ───────────────────────────────────────────────────────────

@login_required
def inbox(request):
    """Admin: list all students with message threads.
       Student: go directly to their own chat."""
    if is_admin(request.user):
        if is_warden(request.user):
            warden_block = HostelBlock.objects.filter(warden=request.user, is_active=True).first()
            if warden_block:
                students = StudentProfile.objects.select_related('user').filter(block=warden_block).order_by('roll_number')
            else:
                students = StudentProfile.objects.none()
        else:
            students = StudentProfile.objects.select_related('user').order_by('roll_number')
        # Fix N+1: annotate unread count and get last message per student efficiently
        from django.db.models import Max, OuterRef, Subquery
        last_msg_qs = Message.objects.filter(
            student=OuterRef('pk')
        ).order_by('-created_at').values('content')[:1]

        rows = []
        for s in students:
            msgs   = Message.objects.filter(student=s)
            unread = msgs.filter(is_read=False).exclude(
                sender__is_staff=True).exclude(sender__is_superuser=True).count()
            last_msg = msgs.order_by('-created_at').first()
            rows.append({'student': s, 'unread': unread, 'last_msg': last_msg})
        rows.sort(key=lambda x: (-x['unread'], -(x['last_msg'].pk if x['last_msg'] else 0)))
        return render(request, 'hostelapp/inbox.html', {'rows': rows})
    else:
        try:
            profile = request.user.student_profile
        except StudentProfile.DoesNotExist:
            return redirect('dashboard')
        return redirect('chat', student_id=profile.id)


@login_required
def chat(request, student_id):
    """Chat view between admin and a specific student."""
    student   = get_object_or_404(StudentProfile, pk=student_id)
    user_admin = is_admin(request.user)  # cache — was called 4 times

    # Permission check
    if not user_admin:
        try:
            if request.user.student_profile != student:
                messages.error(request, 'Access denied.')
                return redirect('dashboard')
        except StudentProfile.DoesNotExist:
            return redirect('dashboard')

    # Mark messages as read
    if user_admin:
        Message.objects.filter(student=student, is_read=False).exclude(
            sender__is_staff=True
        ).exclude(sender__is_superuser=True).update(is_read=True)
    else:
        Message.objects.filter(student=student, is_read=False).filter(
            sender__is_staff=True
        ).update(is_read=True)

    # Send message
    if request.method == 'POST':
        content = request.POST.get('content', '').strip()
        if content:
            Message.objects.create(student=student, sender=request.user, content=content)
            if user_admin:
                create_notification(
                    student.user, 'message',
                    f'💬 New message from Admin',
                    content[:100],
                    f'/chat/{student.id}/'
                )
            else:
                for admin_user in UserModel.objects.filter(is_staff=True):
                    create_notification(
                        admin_user, 'message',
                        f'💬 New message from {request.user.get_full_name() or request.user.username}',
                        content[:100],
                        f'/chat/{student.id}/'
                    )
        return redirect('chat', student_id=student_id)

    chat_messages = Message.objects.filter(student=student).select_related('sender')
    return render(request, 'hostelapp/chat.html', {
        'student':       student,
        'chat_messages': chat_messages,
        'is_admin':      user_admin,
    })


@login_required
def chat_unread_count(request):
    """Returns unread message count as JSON for badge."""
    if is_admin(request.user):
        count = Message.objects.filter(is_read=False).exclude(
            sender__is_staff=True
        ).exclude(sender__is_superuser=True).count()
    else:
        try:
            profile = request.user.student_profile
            count   = Message.objects.filter(
                student=profile, is_read=False
            ).filter(sender__is_staff=True).count()
        except StudentProfile.DoesNotExist:
            count = 0
    return JsonResponse({'count': count})


# ── NOTIFICATION HELPERS & VIEWS ──────────────────────────────────────────────

def create_notification(user, notif_type, title, message, link=''):
    """Helper to create a notification for a user."""
    Notification.objects.create(
        user=user, notif_type=notif_type,
        title=title, message=message, link=link
    )


def notify_all_students(notif_type, title, message, link=''):
    """Send notification to all students."""
    students = StudentProfile.objects.select_related('user').all()
    notifs = [
        Notification(user=s.user, notif_type=notif_type,
                     title=title, message=message, link=link)
        for s in students
    ]
    Notification.objects.bulk_create(notifs)


@login_required
def notifications_list(request):
    """Show all notifications for current user."""
    notifs = Notification.objects.filter(user=request.user)
    unread = notifs.filter(is_read=False).count()
    # Mark all as read when page is opened
    notifs.filter(is_read=False).update(is_read=True)
    return render(request, 'hostelapp/notifications.html', {
        'notifs': notifs,
        'unread': unread,
    })


@login_required
def notifications_unread(request):
    """Returns unread notification count as JSON."""
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    # Also get latest 5 unread for dropdown
    latest = Notification.objects.filter(
        user=request.user, is_read=False
    ).values('id', 'title', 'message', 'notif_type', 'link', 'created_at')[:5]
    return JsonResponse({
        'count': count,
        'latest': list(latest)
    })


@login_required
def notification_mark_read(request, pk):
    """Mark a single notification as read."""
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.is_read = True
    notif.save()
    if notif.link:
        return redirect(notif.link)
    return redirect('notifications_list')


@login_required
def notifications_mark_all_read(request):
    """Mark all notifications as read."""
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect('notifications_list')


# ── PRINT ATTENDANCE VIEWS ────────────────────────────────────────────────────

@login_required
def attendance_print_daily(request):
    """Printable daily attendance sheet."""
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard')

    date_str = request.GET.get('date', str(date.today()))
    try:
        sel_date = date.fromisoformat(date_str)
    except ValueError:
        sel_date = date.today()

    students   = StudentProfile.objects.select_related('user').order_by('roll_number')
    attendance = Attendance.objects.filter(date=sel_date).select_related('student')
    att_map    = {a.student_id: a for a in attendance}

    rows = []
    for s in students:
        att = att_map.get(s.id)
        rows.append({
            'student': s,
            'status':  att.status if att else None,
            'remarks': att.remarks if att else '',
        })

    return render(request, 'hostelapp/attendance_print.html', {
        'rows':     rows,
        'sel_date': sel_date,
        'print_type': 'daily',
        'total':    len(rows),
        'present':  sum(1 for r in rows if r['status'] == 'present'),
        'absent':   sum(1 for r in rows if r['status'] == 'absent'),
        'unmarked': sum(1 for r in rows if r['status'] is None),
    })


@login_required
def attendance_print_monthly(request):
    """Printable monthly attendance report."""
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard')

    month_str = request.GET.get('month', date.today().strftime('%Y-%m'))
    try:
        year, month = map(int, month_str.split('-'))
    except Exception:
        year, month = date.today().year, date.today().month

    students = StudentProfile.objects.select_related('user').order_by('roll_number')

    # Fix N+1: fetch all records for the month in one query
    all_records = Attendance.objects.filter(
        date__year=year, date__month=month
    ).values('student_id', 'status')
    att_map = defaultdict(lambda: {'present': 0, 'absent': 0})
    for r in all_records:
        att_map[r['student_id']][r['status']] += 1

    rows = []
    for s in students:
        data    = att_map[s.id]
        present = data['present']
        absent  = data['absent']
        total   = present + absent
        pct     = round((present / total * 100) if total > 0 else 0)
        rows.append({'student': s, 'total': total,
                     'present': present, 'absent': absent, 'pct': pct})

    month_name = calendar.month_name[month]

    return render(request, 'hostelapp/attendance_print.html', {
        'rows':       rows,
        'print_type': 'monthly',
        'month_name': month_name,
        'year':       year,
        'month':      month,
    })


# ── HOSTEL RULES VIEWS ────────────────────────────────────────────────────────

RULE_CATEGORIES = [
    ('room',         'Room Rules',          '🏠'),
    ('visitor',      'Visitor Rules',       '👥'),
    ('fee',          'Fee Rules',           '💰'),
    ('disciplinary', 'Disciplinary Rules',  '⚖️'),
    ('gate',         'Gate Timing Rules',   '🚪'),
    ('wifi',         'Internet/WiFi Rules', '📶'),
    ('leave',        'Holiday/Leave Rules', '🗓️'),
    ('emergency',    'Emergency Rules',     '🚨'),
]


@login_required
def rules_list(request):
    """Show all hostel rules grouped by category."""
    rules = HostelRule.objects.filter(is_active=True)
    grouped = {}
    for cat, label, icon in RULE_CATEGORIES:
        cat_rules = rules.filter(category=cat)
        if cat_rules.exists() or is_admin(request.user):
            grouped[cat] = {
                'label': label,
                'icon':  icon,
                'rules': cat_rules,
            }
    return render(request, 'hostelapp/rules_list.html', {
        'grouped':    grouped,
        'is_admin':   is_admin(request.user),
        'categories': RULE_CATEGORIES,
    })


@login_required
def rule_add(request):
    """Admin: add a new rule."""
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('rules_list')
    if request.method == 'POST':
        category    = request.POST.get('category')
        title       = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        order       = request.POST.get('order', 0)
        if title and description and category:
            HostelRule.objects.create(
                category=category, title=title,
                description=description, order=order
            )
            messages.success(request, f'Rule added successfully!')
            return redirect('rules_list')
        else:
            messages.error(request, 'Please fill all fields.')
    return render(request, 'hostelapp/rule_form.html', {
        'categories': RULE_CATEGORIES,
        'title': 'Add Rule',
    })


@login_required
def rule_edit(request, pk):
    """Admin: edit a rule."""
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('rules_list')
    rule = get_object_or_404(HostelRule, pk=pk)
    if request.method == 'POST':
        rule.category    = request.POST.get('category', rule.category)
        rule.title       = request.POST.get('title', rule.title).strip()
        rule.description = request.POST.get('description', rule.description).strip()
        rule.order       = request.POST.get('order', rule.order)
        rule.save()
        messages.success(request, 'Rule updated successfully!')
        return redirect('rules_list')
    return render(request, 'hostelapp/rule_form.html', {
        'categories': RULE_CATEGORIES,
        'rule':  rule,
        'title': 'Edit Rule',
    })


@login_required
def rule_delete(request, pk):
    """Admin: delete a rule."""
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('rules_list')
    rule = get_object_or_404(HostelRule, pk=pk)
    if request.method == 'POST':
        rule.delete()
        messages.success(request, 'Rule deleted.')
    return redirect('rules_list')


# ── LEAVE MANAGEMENT VIEWS ────────────────────────────────────────────────────

@login_required
def leave_list(request):
    """Admin: all leave requests. Student: own leave requests."""
    if is_admin(request.user):
        if is_warden(request.user):
            warden_block = HostelBlock.objects.filter(warden=request.user, is_active=True).first()
            if warden_block:
                leaves = LeaveRequest.objects.filter(student__block=warden_block).select_related('student__user')
            else:
                leaves = LeaveRequest.objects.none()
        else:
            leaves = LeaveRequest.objects.select_related('student__user').all()
        status_filter = request.GET.get('status', '')
        if status_filter:
            leaves = leaves.filter(status=status_filter)
        return render(request, 'hostelapp/leave_list.html', {
            'leaves':        leaves,
            'is_admin':      True,
            'status_filter': status_filter,
            'pending_count': LeaveRequest.objects.filter(status='pending').count(),
            'filter_tabs': [
                ('pending',  'Pending',   '#f59e0b'),
                ('approved', 'Approved',  '#10b981'),
                ('rejected', 'Rejected',  '#e94560'),
                ('cancelled','Cancelled', '#6b7280'),
            ],
        })
    else:
        try:
            profile = request.user.student_profile
        except StudentProfile.DoesNotExist:
            return redirect('dashboard')
        leaves = LeaveRequest.objects.filter(student=profile)
        return render(request, 'hostelapp/leave_list.html', {
            'leaves':   leaves,
            'is_admin': False,
        })


@login_required
def leave_apply(request):
    """Student applies for leave."""
    try:
        profile = request.user.student_profile
    except StudentProfile.DoesNotExist:
        messages.error(request, 'Student profile not found.')
        return redirect('dashboard')

    if request.method == 'POST':
        leave_type = request.POST.get('leave_type')
        from_date  = request.POST.get('from_date')
        to_date    = request.POST.get('to_date')
        reason     = request.POST.get('reason', '').strip()

        if not all([leave_type, from_date, to_date, reason]):
            messages.error(request, 'Please fill all fields.')
        else:
            try:
                fd = date.fromisoformat(from_date)
                td = date.fromisoformat(to_date)
                if fd > td:
                    messages.error(request, 'From date cannot be after To date.')
                elif fd < date.today():
                    messages.error(request, 'From date cannot be in the past.')
                else:
                    # Check for overlapping active leave requests
                    overlapping = LeaveRequest.objects.filter(
                        student=profile,
                        status__in=['pending', 'approved'],
                        from_date__lte=td,
                        to_date__gte=fd,
                    ).exists()
                    if overlapping:
                        messages.error(request, 'You already have a leave request for these dates.')
                    else:
                        leave = LeaveRequest.objects.create(
                            student=profile, leave_type=leave_type,
                            from_date=fd, to_date=td, reason=reason
                        )
                        for admin_user in UserModel.objects.filter(is_staff=True):
                            create_notification(
                                admin_user, 'notice',
                                f'🗓️ Leave Request from {profile.user.get_full_name() or profile.user.username}',
                                f'{leave.get_leave_type_display()} from {fd} to {td}. Reason: {reason[:80]}',
                                '/leave/'
                            )
                        messages.success(request, 'Leave request submitted successfully!')
                        return redirect('leave_list')
            except ValueError:
                messages.error(request, 'Invalid date format.')

    leave_types = LeaveRequest.LEAVE_TYPES
    return render(request, 'hostelapp/leave_apply.html', {'leave_types': leave_types})


@login_required
def leave_review(request, pk):
    """Admin approves or rejects leave."""
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('leave_list')

    leave = get_object_or_404(LeaveRequest, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action in ['approved', 'rejected']:
            # BUG FIX: was calling leave.save() twice — once before admin_remark
            # was set, then again after. Now set all fields first, save once.
            admin_remark         = request.POST.get('admin_remark', '').strip()
            leave.status         = action
            leave.reviewed_by    = request.user
            leave.admin_remark   = admin_remark
            leave.save()

            emoji = '✅' if action == 'approved' else '❌'
            create_notification(
                leave.student.user, 'notice',
                f'{emoji} Leave {action.capitalize()}: {leave.get_leave_type_display()}',
                f'Your leave from {leave.from_date} to {leave.to_date} has been {action}.' +
                (f' Remark: {admin_remark}' if admin_remark else ''),
                '/leave/'
            )
            # Send email
            if leave.student.user.email:
                try:
                    send_mail(
                        f'HostelHub — Leave {action.capitalize()}',
                        f"""Dear {leave.student.user.get_full_name() or leave.student.user.username},

Your leave request has been {action}.

Leave Type  : {leave.get_leave_type_display()}
From Date   : {leave.from_date.strftime('%d %B %Y')}
To Date     : {leave.to_date.strftime('%d %B %Y')}
Total Days  : {leave.days} day(s)
Status      : {action.upper()}

Regards,
HostelHub Management
""",
                        settings.DEFAULT_FROM_EMAIL,
                        [leave.student.user.email],
                        fail_silently=True
                    )
                except Exception:
                    pass
            messages.success(request, f'Leave {action} successfully!')
        return redirect('leave_list')

    return render(request, 'hostelapp/leave_review.html', {'leave': leave})


@login_required
def leave_cancel(request, pk):
    """Student cancels their own pending leave."""
    leave = get_object_or_404(LeaveRequest, pk=pk)
    try:
        profile = request.user.student_profile
        if leave.student != profile:
            messages.error(request, 'Access denied.')
            return redirect('leave_list')
    except StudentProfile.DoesNotExist:
        return redirect('dashboard')

    if leave.status == 'pending':
        leave.status = 'cancelled'
        leave.save()
        messages.success(request, 'Leave request cancelled.')
    else:
        messages.error(request, 'Only pending leaves can be cancelled.')
    return redirect('leave_list')


# ── ADMIN PROFILE VIEW ────────────────────────────────────────────────────────
@login_required
def admin_profile(request):
    """Admin/Warden profile page — update name, email, password."""
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('profile')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_info':
            first_name = request.POST.get('first_name', '').strip()
            last_name  = request.POST.get('last_name', '').strip()
            email      = request.POST.get('email', '').strip()
            if first_name:
                request.user.first_name = first_name
            if last_name:
                request.user.last_name = last_name
            if email:
                request.user.email = email
            request.user.save()
            messages.success(request, '✅ Profile updated successfully!')

        elif action == 'change_password':
            current  = request.POST.get('current_password', '')
            new_pass = request.POST.get('new_password', '')
            confirm  = request.POST.get('confirm_password', '')
            if not request.user.check_password(current):
                messages.error(request, '❌ Current password is incorrect.')
            elif len(new_pass) < 6:
                messages.error(request, '❌ New password must be at least 6 characters.')
            elif new_pass != confirm:
                messages.error(request, '❌ Passwords do not match.')
            else:
                request.user.set_password(new_pass)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, '✅ Password changed successfully!')

        return redirect('admin_profile')

    return render(request, 'hostelapp/admin_profile.html', {'user': request.user})


# ── FEE RECEIPT PDF ───────────────────────────────────────────────────────────

# ── GALLERY VIEWS ─────────────────────────────────────────────────────────────

@login_required
def gallery(request):
    """Hostel photo gallery — all users can view."""
    category    = request.GET.get('category', '')
    photos      = HostelGallery.objects.all()
    if category:
        photos = photos.filter(category=category)
    featured    = HostelGallery.objects.filter(is_featured=True)[:6]
    categories  = HostelGallery.CATEGORY_CHOICES
    return render(request, 'hostelapp/gallery.html', {
        'photos':    photos,
        'featured':  featured,
        'categories': categories,
        'category':  category,
        'is_admin':  is_admin(request.user),
    })


@login_required
def gallery_upload(request):
    """Admin uploads photos to gallery."""
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('gallery')
    if request.method == 'POST':
        title       = request.POST.get('title', '').strip()
        category    = request.POST.get('category', 'hostel')
        description = request.POST.get('description', '').strip()
        is_featured = request.POST.get('is_featured') == 'on'
        photos      = request.FILES.getlist('photos')
        if not photos:
            messages.error(request, 'Please select at least one photo.')
        else:
            for photo in photos:
                HostelGallery.objects.create(
                    photo=photo,
                    title=title or photo.name,
                    category=category,
                    description=description,
                    is_featured=is_featured,
                    uploaded_by=request.user
                )
            messages.success(request, f'{len(photos)} photo(s) uploaded successfully!')
            return redirect('gallery')
    return render(request, 'hostelapp/gallery_upload.html', {
        'categories': HostelGallery.CATEGORY_CHOICES
    })


@login_required
def gallery_delete(request, pk):
    """Admin deletes a gallery photo."""
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('gallery')
    photo = get_object_or_404(HostelGallery, pk=pk)
    if request.method == 'POST':
        photo.photo.delete()
        photo.delete()
        messages.success(request, 'Photo deleted.')
    return redirect('gallery')


@login_required
def room_photo_add(request, pk):
    """Admin adds photo to a specific room."""
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('room_list')
    room = get_object_or_404(Room, pk=pk)
    if request.method == 'POST':
        photos = request.FILES.getlist('photos')
        caption = request.POST.get('caption', '')
        for photo in photos:
            RoomPhoto.objects.create(
                room=room, photo=photo,
                caption=caption, uploaded_by=request.user
            )
        messages.success(request, f'{len(photos)} photo(s) added to Room {room.room_number}!')
        return redirect('room_detail', pk=pk)
    return render(request, 'hostelapp/room_photo_add.html', {'room': room})


@login_required
def room_photo_delete(request, pk):
    """Admin deletes a room photo."""
    if not is_admin(request.user):
        return redirect('room_list')
    photo = get_object_or_404(RoomPhoto, pk=pk)
    room_pk = photo.room.pk
    if request.method == 'POST':
        photo.photo.delete()
        photo.delete()
        messages.success(request, 'Photo deleted.')
    return redirect('room_detail', pk=room_pk)


# ── WARDEN MANAGEMENT ─────────────────────────────────────────────────────────
@login_required
def warden_list(request):
    """List all wardens — superadmin only."""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    warden_group, _ = Group.objects.get_or_create(name='Warden')
    wardens = UserModel.objects.filter(groups=warden_group)
    # Get assigned block for each warden
    warden_blocks = {}
    for block in HostelBlock.objects.filter(is_active=True):
        if block.warden_id:
            warden_blocks[block.warden_id] = block
    return render(request, 'hostelapp/warden_list.html', {
        'wardens': wardens,
        'warden_blocks': warden_blocks,
    })


@login_required
def warden_create(request):
    """Create a new warden account — superadmin only."""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')

    if request.method == 'POST':
        username   = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        email      = request.POST.get('email', '').strip()
        password   = request.POST.get('password', '')
        confirm    = request.POST.get('confirm_password', '')

        # Validations
        if not username or not password:
            messages.error(request, 'Username and password are required.')
        elif len(password) < 6:
            messages.error(request, 'Password must be at least 6 characters.')
        elif password != confirm:
            messages.error(request, 'Passwords do not match.')
        else:

            if UserModel.objects.filter(username=username).exists():
                messages.error(request, f'Username "{username}" already exists.')
            else:
                # Create user
                user = UserModel.objects.create_user(
                    username=username,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    is_staff=True
                )

                # Create/get Warden group with permissions
                group, created = Group.objects.get_or_create(name='Warden')
                # Always ensure permissions are set (not just on first creation)
                warden_perms = [
                    ('hostelapp','studentprofile','view'),
                    ('hostelapp','room','view'),
                    ('hostelapp','roomallotment','view'),
                    ('hostelapp','complaint','view'),
                    ('hostelapp','complaint','change'),
                    ('hostelapp','notice','view'),
                    ('hostelapp','notice','add'),
                    ('hostelapp','notice','change'),
                    ('hostelapp','attendance','view'),
                    ('hostelapp','attendance','add'),
                    ('hostelapp','attendance','change'),
                    ('hostelapp','leaverequest','view'),
                    ('hostelapp','leaverequest','change'),
                    ('hostelapp','message','view'),
                    ('hostelapp','message','add'),
                ]
                for app, model, action in warden_perms:
                    try:
                        ct   = ContentType.objects.get(app_label=app, model=model)
                        perm = Permission.objects.get(content_type=ct, codename=f'{action}_{model}')
                        group.permissions.add(perm)
                    except Exception:
                        pass

                user.groups.add(group)

                # Assign block to warden if selected
                block_id = request.POST.get('block', '')
                if block_id:
                    try:
                        block = HostelBlock.objects.get(pk=block_id)
                        block.warden = user
                        block.save()
                    except HostelBlock.DoesNotExist:
                        pass

                messages.success(request, f'✅ Warden "{username}" created successfully!')
                return redirect('warden_list')

    blocks = HostelBlock.objects.filter(is_active=True)
    return render(request, 'hostelapp/warden_create.html', {'blocks': blocks})


@login_required
def warden_delete(request, pk):
    """Delete a warden account."""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    user = get_object_or_404(UserModel, pk=pk)
    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f'Warden "{username}" deleted.')
    return redirect('warden_list')


# ── STUDENT DOCUMENTS ─────────────────────────────────────────────────────────
@login_required
def document_list(request):
    if is_admin(request.user):
        sel_student = request.GET.get('student', '')
        documents = StudentDocument.objects.select_related(
            'student__user').all().order_by('-uploaded_at')
        if sel_student:
            documents = documents.filter(student__id=sel_student)
        return render(request, 'hostelapp/document_list.html', {
            'documents':   documents,
            'is_admin':    True,
            'students':    StudentProfile.objects.select_related('user').all(),
            'sel_student': sel_student,
        })
    try:
        profile = request.user.student_profile
    except StudentProfile.DoesNotExist:
        return redirect('dashboard')
    documents = StudentDocument.objects.filter(student=profile)
    return render(request, 'hostelapp/document_list.html', {
        'documents': documents,
        'is_admin':  False,
        'doc_types': StudentDocument.DOCUMENT_TYPES,
    })


@login_required
def document_upload(request):
    """Student uploads a document — admin has no access."""
    if is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    try:
        profile = request.user.student_profile
    except StudentProfile.DoesNotExist:
        return redirect('dashboard')

    if request.method == 'POST':
        doc_type = request.POST.get('document_type')
        title    = request.POST.get('title', '').strip()
        file     = request.FILES.get('file')

        if not doc_type or not file:
            messages.error(request, 'Please select document type and upload a file.')
        else:
            # Check file size (max 5MB)
            if file.size > 5 * 1024 * 1024:
                messages.error(request, 'File too large! Maximum size is 5MB.')
            else:
                # Check file type
                allowed = ['jpg','jpeg','png','pdf','gif','webp']
                ext = file.name.split('.')[-1].lower()
                if ext not in allowed:
                    messages.error(request, f'File type .{ext} not allowed. Use JPG, PNG or PDF.')
                else:
                    StudentDocument.objects.create(
                        student=profile,
                        document_type=doc_type,
                        title=title or dict(StudentDocument.DOCUMENT_TYPES).get(doc_type, doc_type),
                        file=file
                    )
                    # Notify admin
                    for admin_user in UserModel.objects.filter(is_superuser=True):
                        create_notification(
                            admin_user, 'notice',
                            f'📄 Document Uploaded: {profile.user.get_full_name()}',
                            f'{dict(StudentDocument.DOCUMENT_TYPES).get(doc_type)} uploaded by {profile.roll_number}',
                            '/documents/'
                        )
                    messages.success(request, 'Document uploaded successfully!')
                    return redirect('document_list')

    return render(request, 'hostelapp/document_upload.html', {
        'doc_types': StudentDocument.DOCUMENT_TYPES,
    })


@login_required
def document_delete(request, pk):
    """Student deletes own document."""
    # BUG FIX: removed dead/unreachable code that appeared after return statement
    doc = get_object_or_404(StudentDocument, pk=pk)
    if not is_admin(request.user):
        try:
            if doc.student != request.user.student_profile:
                messages.error(request, 'Access denied.')
                return redirect('document_list')
        except StudentProfile.DoesNotExist:
            return redirect('dashboard')
    if request.method == 'POST':
        doc.file.delete()
        doc.delete()
        messages.success(request, 'Document deleted.')
    return redirect('document_list')

@login_required
def document_verify(request, pk):
    """Admin verifies a document."""
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('document_list')
    doc = get_object_or_404(StudentDocument, pk=pk)
    # BUG FIX: removed doc.verified_by — field doesn't exist in StudentDocument model
    doc.is_verified = not doc.is_verified
    doc.save()
    status = 'verified' if doc.is_verified else 'unverified'
    messages.success(request, f'Document {status}.')
    create_notification(
        doc.student.user, 'notice',
        f'{"✅" if doc.is_verified else "❌"} Document {status.capitalize()}: {doc.title}',
        f'Your {doc.get_document_type_display()} has been {status} by admin.',
        '/documents/'
    )
    return redirect('document_list')
# ── WARDEN ↔ ADMIN MESSAGING ──────────────────────────────────────────────────

@login_required
def warden_inbox(request):
    """Superadmin sees all wardens. Warden goes directly to chat."""
    if not (is_warden(request.user) or request.user.is_superuser):
        messages.error(request, 'Access denied.')
        return redirect('dashboard')

    if request.user.is_superuser:
        warden_group, _ = Group.objects.get_or_create(name='Warden')
        wardens = UserModel.objects.filter(groups=warden_group)
        rows = []
        for w in wardens:
            unread = WardenMessage.objects.filter(
                sender=w, recipient=request.user, is_read=False).count()
            last = WardenMessage.objects.filter(
                sender=w, recipient=request.user
            ).order_by('-created_at').first() or \
            WardenMessage.objects.filter(
                sender=request.user, recipient=w
            ).order_by('-created_at').first()
            rows.append({'warden': w, 'unread': unread, 'last_msg': last})
        rows.sort(key=lambda x: (-x['unread'], -(x['last_msg'].pk if x['last_msg'] else 0)))
        return render(request, 'hostelapp/warden_inbox.html', {'rows': rows})
    else:
        superadmin = UserModel.objects.filter(is_superuser=True).first()
        if not superadmin:
            messages.error(request, 'No admin found.')
            return redirect('dashboard')
        return redirect('warden_chat', user_id=superadmin.pk)


@login_required
def warden_chat(request, user_id):
    """Chat between warden and superadmin."""
    if not (is_warden(request.user) or request.user.is_superuser):
        messages.error(request, 'Access denied.')
        return redirect('dashboard')

    other_user = get_object_or_404(UserModel, pk=user_id)

    # Mark received messages as read
    WardenMessage.objects.filter(
        sender=other_user, recipient=request.user, is_read=False
    ).update(is_read=True)

    if request.method == 'POST':
        content = request.POST.get('content', '').strip()
        if content:
            WardenMessage.objects.create(
                sender=request.user,
                recipient=other_user,
                content=content
            )
            create_notification(
                other_user, 'message',
                f'💬 Message from {request.user.get_full_name() or request.user.username}',
                content[:100],
                f'/warden-chat/{request.user.pk}/'
            )
        return redirect('warden_chat', user_id=user_id)

    # Get full conversation both sides
    chat_messages = (
        WardenMessage.objects.filter(sender=request.user, recipient=other_user) |
        WardenMessage.objects.filter(sender=other_user, recipient=request.user)
    ).order_by('created_at')

    return render(request, 'hostelapp/warden_chat.html', {
        'chat_messages': chat_messages,
        'other_user':    other_user,
        'is_superadmin': request.user.is_superuser,
    })
# ── HOSTEL BLOCK VIEWS ────────────────────────────────────────────────────────

@login_required
def block_list(request):
    """List all hostel blocks."""
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    boys_blocks  = HostelBlock.objects.filter(block_type='boys', is_active=True)
    girls_blocks = HostelBlock.objects.filter(block_type='girls', is_active=True)
    return render(request, 'hostelapp/block_list.html', {
        'boys_blocks':  boys_blocks,
        'girls_blocks': girls_blocks,
    })


@login_required
def block_add(request):
    """Admin adds a new block."""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied.')
        return redirect('block_list')
    if request.method == 'POST':
        name         = request.POST.get('name', '').strip()
        block_type   = request.POST.get('block_type', 'boys')
        description  = request.POST.get('description', '').strip()
        total_floors = request.POST.get('total_floors', 1)
        warden_id    = request.POST.get('warden', '')
        if not name:
            messages.error(request, 'Block name is required.')
        else:
            block = HostelBlock.objects.create(
                name=name,
                block_type=block_type,
                description=description,
                total_floors=total_floors,
            )
            if warden_id:
                try:
                    warden = UserModel.objects.get(pk=warden_id)
                    block.warden = warden
                    block.save()
                except UserModel.DoesNotExist:
                    pass
            messages.success(request, f'Block "{name}" created successfully!')
            return redirect('block_list')
    wardens = UserModel.objects.filter(is_staff=True, is_superuser=False)
    return render(request, 'hostelapp/block_form.html', {
        'title':   'Add Block',
        'wardens': wardens,
    })


@login_required
def block_edit(request, pk):
    """Admin edits a block."""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied.')
        return redirect('block_list')
    block = get_object_or_404(HostelBlock, pk=pk)
    if request.method == 'POST':
        block.name         = request.POST.get('name', block.name).strip()
        block.block_type   = request.POST.get('block_type', block.block_type)
        block.description  = request.POST.get('description', '').strip()
        block.total_floors = request.POST.get('total_floors', block.total_floors)
        block.is_active    = request.POST.get('is_active') == 'on'
        warden_id          = request.POST.get('warden', '')
        if warden_id:
            try:
                block.warden = UserModel.objects.get(pk=warden_id)
            except UserModel.DoesNotExist:
                block.warden = None
        else:
            block.warden = None
        block.save()
        messages.success(request, f'Block "{block.name}" updated successfully!')
        return redirect('block_list')
    wardens = UserModel.objects.filter(is_staff=True, is_superuser=False)
    return render(request, 'hostelapp/block_form.html', {
        'title':   'Edit Block',
        'block':   block,
        'wardens': wardens,
    })


@login_required
def block_delete(request, pk):
    """Admin deletes a block."""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied.')
        return redirect('block_list')
    block = get_object_or_404(HostelBlock, pk=pk)
    if request.method == 'POST':
        name = block.name
        block.delete()
        messages.success(request, f'Block "{name}" deleted.')
    return redirect('block_list')


@login_required
def block_detail(request, pk):
    """View block details — rooms and students."""
    if not is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    block    = get_object_or_404(HostelBlock, pk=pk)
    rooms    = Room.objects.filter(block=block).order_by('floor', 'room_number')
    students = StudentProfile.objects.filter(block=block).select_related('user')
    return render(request, 'hostelapp/block_detail.html', {
        'hostel_block': block,
        'rooms':        rooms,
        'students':     students,
    })