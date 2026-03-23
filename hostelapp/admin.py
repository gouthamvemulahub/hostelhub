from django.contrib import admin
from .models import StudentProfile, Room, RoomAllotment, Complaint, Notice, NoticeRead, StaffMember, OTPVerification, Attendance, ComplaintUpvote, Message, Notification, HostelRule, LeaveRequest, FeePayment, RoomPhoto, HostelGallery, StudentDocument, HostelBlock


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'roll_number', 'course', 'year_of_study', 'phone']
    search_fields = ['user__first_name', 'user__last_name', 'roll_number']
    list_filter = ['course', 'year_of_study', 'gender']

    def get_actions(self, request):
        actions = super().get_actions(request)
        for block in HostelBlock.objects.all():
            action_name = f'assign_to_{block.pk}'
            action = self.make_assign_action(block)
            actions[action_name] = (action, action_name, f'Assign to {block.name} (Boys)')
            action_name_girls = f'assign_girls_to_{block.pk}'
            action_girls = self.make_assign_action_girls(block)
            actions[action_name_girls] = (action_girls, action_name_girls, f'Assign to {block.name} (Girls)')
        return actions

    def make_assign_action(self, block):
        def assign_to_block(modeladmin, request, queryset):
            queryset.update(block=block, hostel_type='boys')
            self.message_user(request, f'{queryset.count()} students assigned to {block.name} as Boys')
        assign_to_block.short_description = f'Assign to {block.name} (Boys)'
        return assign_to_block

    def make_assign_action_girls(self, block):
        def assign_to_block_girls(modeladmin, request, queryset):
            queryset.update(block=block, hostel_type='girls')
            self.message_user(request, f'{queryset.count()} students assigned to {block.name} as Girls')
        assign_to_block_girls.short_description = f'Assign to {block.name} (Girls)'
        return assign_to_block_girls

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['room_number', 'floor', 'room_type', 'capacity', 'current_occupancy', 'status', 'monthly_fee']
    list_filter = ['room_type', 'status', 'floor']
    search_fields = ['room_number']

    def get_actions(self, request):
        actions = super().get_actions(request)
        # Add one action per block
        for block in HostelBlock.objects.all():
            action_name = f'assign_to_{block.pk}'
            action = self.make_assign_action(block)
            action.short_description = f'Assign to {block.name}'
            actions[action_name] = (action, action_name, f'Assign to {block.name}')
        return actions

    def make_assign_action(self, block):
        def assign_to_block(modeladmin, request, queryset):
            queryset.update(block=block)
            self.message_user(request, f'{queryset.count()} rooms assigned to {block.name}')
        assign_to_block.short_description = f'Assign to {block.name}'
        return assign_to_block


@admin.register(RoomAllotment)
class RoomAllotmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'room', 'allotment_date', 'is_active']
    list_filter = ['is_active']


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ['title', 'student', 'category', 'priority', 'status', 'created_at']
    list_filter = ['status', 'category', 'priority']
    search_fields = ['title', 'student__user__first_name']


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = ['title', 'posted_by', 'created_at', 'is_active']


@admin.register(NoticeRead)
class NoticeReadAdmin(admin.ModelAdmin):
    list_display = ['student', 'notice', 'read_at']

@admin.register(StaffMember)
class StaffMemberAdmin(admin.ModelAdmin):
    list_display = ['name', 'role', 'phone', 'status', 'shift']
    list_filter = ['role', 'status']
    search_fields = ['name', 'phone']

@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ['email', 'otp', 'created_at', 'is_used']
    list_filter  = ['is_used']

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display  = ['student', 'date', 'status', 'marked_by']
    list_filter   = ['status', 'date']
    search_fields = ['student__roll_number', 'student__user__first_name']

@admin.register(ComplaintUpvote)
class ComplaintUpvoteAdmin(admin.ModelAdmin):
    list_display = ['complaint', 'student', 'created_at']

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display  = ['student', 'sender', 'content', 'is_read', 'created_at']
    list_filter   = ['is_read']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ['user', 'notif_type', 'title', 'is_read', 'created_at']
    list_filter   = ['notif_type', 'is_read']

@admin.register(HostelRule)
class HostelRuleAdmin(admin.ModelAdmin):
    list_display  = ['category', 'title', 'order', 'is_active']
    list_filter   = ['category', 'is_active']
    ordering      = ['category', 'order']

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display  = ['student', 'leave_type', 'from_date', 'to_date', 'status']
    list_filter   = ['status', 'leave_type']

#@admin.register(FeePayment)
#class FeePaymentAdmin(admin.ModelAdmin):
 #   list_display  = ['student', 'month', 'year', 'amount', 'payment_method', 'status', 'paid_on']
  #  list_filter   = ['status', 'payment_method', 'year']

@admin.register(RoomPhoto)
class RoomPhotoAdmin(admin.ModelAdmin):
    list_display = ["room", "caption", "uploaded_at"]

@admin.register(HostelGallery)
class HostelGalleryAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "is_featured", "uploaded_at"]
    list_filter  = ["category", "is_featured"]

@admin.register(StudentDocument)
class StudentDocumentAdmin(admin.ModelAdmin):
    list_display  = ["student", "document_type", "title", "is_verified", "uploaded_at"]
    list_filter   = ["document_type", "is_verified"]


@admin.register(HostelBlock)
class HostelBlockAdmin(admin.ModelAdmin):
    list_display  = ['name', 'block_type', 'warden', 'total_floors', 'is_active']
    list_filter   = ['block_type', 'is_active']
    search_fields = ['name']