from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone
import os
import calendar

OTP_EXPIRY_SECONDS = 600  # 10 minutes


class HostelBlock(models.Model):
    BLOCK_TYPE_CHOICES = [
        ('boys', 'Boys Hostel'),
        ('girls', 'Girls Hostel'),
    ]
    name         = models.CharField(max_length=50)
    block_type   = models.CharField(max_length=10, choices=BLOCK_TYPE_CHOICES)
    description  = models.TextField(blank=True)
    warden       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='managed_blocks'
    )
    total_floors = models.PositiveIntegerField(default=1)
    is_active    = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['block_type', 'name']

    def __str__(self):
        return f'{self.name} ({self.get_block_type_display()})'

    @property
    def total_rooms(self):
        return self.rooms.count()

    @property
    def available_rooms(self):
        return self.rooms.filter(status='available').count()

    @property
    def total_students(self):
        return StudentProfile.objects.filter(block=self).count()


class StudentProfile(models.Model):
    GENDER_CHOICES = [('M', 'Male'), ('F', 'Female'), ('O', 'Other')]
    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    roll_number = models.CharField(max_length=20, unique=True)
    block       = models.ForeignKey(
        HostelBlock,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='students'
    )
    hostel_type = models.CharField(
        max_length=10,
        choices=[('boys', 'Boys Hostel'), ('girls', 'Girls Hostel')],
        default='boys'
    )
    phone          = models.CharField(max_length=10)
    gender         = models.CharField(max_length=1, choices=GENDER_CHOICES)
    address        = models.TextField()
    guardian_name  = models.CharField(max_length=100)
    guardian_phone = models.CharField(max_length=10)
    course         = models.CharField(max_length=100)
    year_of_study  = models.PositiveIntegerField(default=1)
    profile_photo  = models.ImageField(upload_to='students/', blank=True, null=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.roll_number})"


class Room(models.Model):
    ROOM_TYPE_CHOICES = [
        ('single', 'Single'),
        ('double', 'Double'),
        ('triple', 'Triple'),
        ('dormitory', 'Dormitory'),
    ]
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('full', 'Full'),
        ('maintenance', 'Under Maintenance'),
    ]
    block       = models.ForeignKey(
        HostelBlock,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='rooms'
    )
    room_number  = models.CharField(max_length=20, unique=True)
    floor        = models.PositiveIntegerField()
    room_type    = models.CharField(max_length=20, choices=ROOM_TYPE_CHOICES)
    capacity     = models.PositiveIntegerField()
    monthly_fee  = models.DecimalField(max_digits=8, decimal_places=2)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    amenities    = models.TextField(blank=True, help_text="Comma separated amenities e.g. WiFi, AC")
    description  = models.TextField(blank=True)

    def __str__(self):
        return f"Room {self.room_number} ({self.room_type})"

    @property
    def current_occupancy(self):
        return self.allotments.filter(is_active=True).count()

    @property
    def available_beds(self):
        return self.capacity - self.current_occupancy

    def update_status(self):
        if self.status == 'maintenance':
            return
        if self.current_occupancy >= self.capacity:
            self.status = 'full'
        else:
            self.status = 'available'
        self.save()


class RoomAllotment(models.Model):
    student        = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='allotments')
    room           = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='allotments')
    allotment_date = models.DateField(auto_now_add=True)
    vacating_date  = models.DateField(null=True, blank=True)
    is_active      = models.BooleanField(default=True)
    remarks        = models.TextField(blank=True)

    def __str__(self):
        return f"{self.student} -> Room {self.room.room_number}"


class Complaint(models.Model):
    CATEGORY_CHOICES = [
        ('electrical', 'Electrical'),
        ('plumbing', 'Plumbing'),
        ('furniture', 'Furniture'),
        ('cleanliness', 'Cleanliness'),
        ('internet', 'Internet/WiFi'),
        ('security', 'Security'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('rejected', 'Rejected'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    student       = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='complaints')
    room          = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True)
    category      = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    priority      = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    title         = models.CharField(max_length=200)
    description   = models.TextField()
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_remarks = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)
    resolved_at   = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} - {self.student}"

    class Meta:
        ordering = ['-created_at']


class Notice(models.Model):
    PRIORITY_CHOICES = [
        ('normal', 'Normal'),
        ('urgent', 'Urgent'),
    ]
    title      = models.CharField(max_length=200)
    content    = models.TextField()
    priority   = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    photo      = models.ImageField(upload_to='notices/', blank=True, null=True)
    posted_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active  = models.BooleanField(default=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']


class NoticeRead(models.Model):
    """Tracks which students have read which notices."""
    student  = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='read_notices')
    notice   = models.ForeignKey(Notice, on_delete=models.CASCADE, related_name='reads')
    read_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'notice')

    def __str__(self):
        return f"{self.student} read {self.notice.title}"


class StaffMember(models.Model):
    ROLE_CHOICES = [
        ('warden', 'Warden'),
        ('assistant_warden', 'Assistant Warden'),
        ('security', 'Security Guard'),
        ('cleaner', 'Cleaner / Housekeeping'),
        ('electrician', 'Electrician'),
        ('plumber', 'Plumber'),
        ('cook', 'Cook / Mess Staff'),
        ('admin', 'Admin Staff'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('on_leave', 'On Leave'),
    ]

    name        = models.CharField(max_length=100)
    role        = models.CharField(max_length=30, choices=ROLE_CHOICES)
    phone       = models.CharField(max_length=15)
    email       = models.EmailField(blank=True)
    address     = models.TextField(blank=True)
    shift       = models.CharField(max_length=50, blank=True, help_text="e.g. Morning 6AM-2PM")
    photo       = models.ImageField(upload_to='staff/', blank=True, null=True)
    status      = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active')
    joined_date = models.DateField(null=True, blank=True)
    notes       = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"

    class Meta:
        ordering = ['role', 'name']


class OTPVerification(models.Model):
    """Stores OTP for email verification during registration."""
    email      = models.EmailField()
    otp        = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used    = models.BooleanField(default=False)

    def is_expired(self):
        return (timezone.now() - self.created_at).total_seconds() > OTP_EXPIRY_SECONDS

    def __str__(self):
        return f"OTP for {self.email}"

    class Meta:
        ordering = ['-created_at']


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent',  'Absent'),
    ]
    student    = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='attendances')
    date       = models.DateField()
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default='present')
    marked_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='marked_attendances')
    remarks    = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'date')
        ordering = ['-date', 'student__roll_number']

    def __str__(self):
        return f"{self.student.roll_number} - {self.date} - {self.status}"


class ComplaintUpvote(models.Model):
    """A student can upvote a complaint once to show it affects them too."""
    complaint  = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='upvotes')
    student    = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='upvoted_complaints')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('complaint', 'student')

    def __str__(self):
        return f"{self.student.roll_number} upvoted complaint {self.complaint.id}"


class Message(models.Model):
    """Private message between a student and admin."""
    student    = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='messages')
    sender     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content    = models.TextField()
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Msg from {self.sender.username} re {self.student.roll_number}"

    @property
    def is_from_admin(self):
        return self.sender.is_staff or self.sender.is_superuser


class Notification(models.Model):
    NOTIF_TYPES = [
        ('notice',     'New Notice'),
        ('complaint',  'Complaint Update'),
        ('allotment',  'Room Allotment'),
        ('attendance', 'Attendance Marked'),
        ('message',    'New Message'),
        ('fee',        'Fee Reminder'),
    ]
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notif_type = models.CharField(max_length=20, choices=NOTIF_TYPES)
    title      = models.CharField(max_length=200)
    message    = models.TextField()
    link       = models.CharField(max_length=200, blank=True)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.title}"


class HostelRule(models.Model):
    CATEGORY_CHOICES = [
        ('room',         'Room Rules'),
        ('visitor',      'Visitor Rules'),
        ('fee',          'Fee Rules'),
        ('disciplinary', 'Disciplinary Rules'),
        ('gate',         'Gate Timing Rules'),
        ('wifi',         'Internet/WiFi Rules'),
        ('leave',        'Holiday/Leave Rules'),
        ('emergency',    'Emergency Rules'),
    ]
    category    = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    title       = models.CharField(max_length=200)
    description = models.TextField()
    order       = models.PositiveIntegerField(default=0)
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'order', 'created_at']

    def __str__(self):
        return f"[{self.get_category_display()}] {self.title}"


class LeaveRequest(models.Model):
    LEAVE_TYPES = [
        ('home',      'Home Visit'),
        ('medical',   'Medical/Health'),
        ('emergency', 'Family Emergency'),
        ('festival',  'Festival/Holiday'),
        ('other',     'Other'),
    ]
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('approved',  'Approved'),
        ('rejected',  'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    student      = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type   = models.CharField(max_length=20, choices=LEAVE_TYPES)
    from_date    = models.DateField()
    to_date      = models.DateField()
    reason       = models.TextField()
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_remark = models.TextField(blank=True)
    reviewed_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_leaves')
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.roll_number} - {self.get_leave_type_display()} ({self.from_date} to {self.to_date})"

    @property
    def days(self):
        return (self.to_date - self.from_date).days + 1


class FeePayment(models.Model):
    PAYMENT_METHODS = [
        ('cash',   'Cash'),
        ('upi',    'UPI'),
        ('bank',   'Bank Transfer'),
        ('online', 'Online Payment'),
    ]
    STATUS_CHOICES = [
        ('paid',    'Paid'),
        ('pending', 'Pending'),
        ('partial', 'Partial'),
    ]
    VERIFY_STATUS = [
        ('unverified', 'Unverified'),
        ('verified',   'Verified'),
        ('rejected',   'Rejected'),
    ]
    student        = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='fee_payments')
    month          = models.PositiveIntegerField()
    year           = models.PositiveIntegerField()
    amount         = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    transaction_id = models.CharField(max_length=100, blank=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='paid')
    verify_status  = models.CharField(max_length=20, choices=VERIFY_STATUS, default='unverified')
    payment_proof  = models.ImageField(upload_to='fee_proofs/', blank=True, null=True)
    remarks        = models.TextField(blank=True)
    recorded_by    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_payments')
    paid_on        = models.DateField()
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-year', '-month']
        unique_together = ('student', 'month', 'year')

    def __str__(self):
        return f"{self.student.roll_number} - {calendar.month_name[self.month]} {self.year} - Rs.{self.amount}"

    @property
    def month_name(self):
        return calendar.month_name[self.month]


class RoomPhoto(models.Model):
    room        = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='photos')
    photo       = models.ImageField(upload_to='room_photos/', blank=True, null=True)
    caption     = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Photo of Room {self.room.room_number}"


class HostelGallery(models.Model):
    CATEGORY_CHOICES = [
        ('hostel',  'Hostel Building'),
        ('common',  'Common Areas'),
        ('mess',    'Mess/Dining'),
        ('sports',  'Sports & Recreation'),
        ('events',  'Events'),
        ('other',   'Other'),
    ]
    photo       = models.ImageField(upload_to='gallery/', blank=True, null=True)
    title       = models.CharField(max_length=200)
    category    = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='hostel')
    description = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_featured = models.BooleanField(default=False)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.title


class StudentDocument(models.Model):
    DOCUMENT_TYPES = [
        ('aadhar',      'Aadhar Card'),
        ('pan',         'PAN Card'),
        ('college_id',  'College ID Card'),
        ('bonafide',    'Bonafide Certificate'),
        ('fee_receipt', 'Fee Receipt'),
        ('photo',       'Passport Photo'),
        ('other',       'Other Document'),
    ]
    student       = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    title         = models.CharField(max_length=200)
    file          = models.FileField(upload_to='student_documents/')
    uploaded_at   = models.DateTimeField(auto_now_add=True)
    is_verified   = models.BooleanField(default=False)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.student.roll_number} - {self.get_document_type_display()}"

    @property
    def file_extension(self):
        return os.path.splitext(self.file.name)[1].lower()

    @property
    def is_image(self):
        return self.file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.webp']

    @property
    def is_pdf(self):
        return self.file_extension == '.pdf'


class WardenMessage(models.Model):
    sender     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='warden_sent')
    recipient  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='warden_received')
    content    = models.TextField()
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender} → {self.recipient}: {self.content[:40]}'