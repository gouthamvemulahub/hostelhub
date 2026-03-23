from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('admin-profile/', views.admin_profile, name='admin_profile'),

    # Wardens
    path('wardens/', views.warden_list, name='warden_list'),
    path('wardens/create/', views.warden_create, name='warden_create'),
    path('wardens/<int:pk>/delete/', views.warden_delete, name='warden_delete'),

    # Students
    path('students/', views.student_list, name='student_list'),

    # Rooms
    path('rooms/', views.room_list, name='room_list'),
    path('rooms/add/', views.room_add, name='room_add'),
    path('rooms/<int:pk>/', views.room_detail, name='room_detail'),
    path('rooms/<int:pk>/edit/', views.room_edit, name='room_edit'),

    # Allotments
    path('allotments/', views.allotment_list, name='allotment_list'),
    path('allotments/add/', views.allotment_add, name='allotment_add'),
    path('allotments/<int:pk>/vacate/', views.allotment_vacate, name='allotment_vacate'),

    # Complaints
    path('complaints/', views.complaint_list, name='complaint_list'),
    path('complaints/add/', views.complaint_add, name='complaint_add'),
    path('complaints/<int:pk>/', views.complaint_detail, name='complaint_detail'),
    path('complaints/<int:pk>/upvote/', views.complaint_upvote, name='complaint_upvote'),

    # Staff
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/add/', views.staff_add, name='staff_add'),
    path('staff/<int:pk>/', views.staff_detail, name='staff_detail'),
    path('staff/<int:pk>/edit/', views.staff_edit, name='staff_edit'),
    path('staff/<int:pk>/delete/', views.staff_delete, name='staff_delete'),

    # Notices
    path('notices/', views.notice_list, name='notice_list'),
    path('notices/add/', views.notice_add, name='notice_add'),
    path('notices/<int:pk>/edit/', views.notice_edit, name='notice_edit'),
    path('notices/<int:pk>/delete/', views.notice_delete, name='notice_delete'),
    path('notices/<int:pk>/read/', views.notice_mark_read, name='notice_mark_read'),
    path('notices/read-all/', views.notice_mark_all_read, name='notice_mark_all_read'),

    # Export
    path('export/', views.export_data, name='export_data'),

    # Leave Management
    path('leave/', views.leave_list, name='leave_list'),
    path('leave/apply/', views.leave_apply, name='leave_apply'),
    path('leave/<int:pk>/review/', views.leave_review, name='leave_review'),
    path('leave/<int:pk>/cancel/', views.leave_cancel, name='leave_cancel'),

    # Gallery
    path('gallery/', views.gallery, name='gallery'),
    path('gallery/upload/', views.gallery_upload, name='gallery_upload'),
    path('gallery/<int:pk>/delete/', views.gallery_delete, name='gallery_delete'),
    path('rooms/<int:pk>/photos/add/', views.room_photo_add, name='room_photo_add'),
    path('rooms/photos/<int:pk>/delete/', views.room_photo_delete, name='room_photo_delete'),
    # Hostel Blocks
    path('blocks/', views.block_list, name='block_list'),
    path('blocks/add/', views.block_add, name='block_add'),
    path('blocks/<int:pk>/', views.block_detail, name='block_detail'),
    path('blocks/<int:pk>/edit/', views.block_edit, name='block_edit'),
    path('blocks/<int:pk>/delete/', views.block_delete, name='block_delete'),

    # Rules
    path('rules/', views.rules_list, name='rules_list'),
    path('rules/add/', views.rule_add, name='rule_add'),
    path('rules/<int:pk>/edit/', views.rule_edit, name='rule_edit'),
    path('rules/<int:pk>/delete/', views.rule_delete, name='rule_delete'),

    # Notifications
    path('notifications/', views.notifications_list, name='notifications_list'),
    path('notifications/unread/', views.notifications_unread, name='notifications_unread'),
    path('notifications/<int:pk>/read/', views.notification_mark_read, name='notification_mark_read'),
    path('notifications/mark-all-read/', views.notifications_mark_all_read, name='notifications_mark_all_read'),

    # Student ↔ Admin Messaging
    path('inbox/', views.inbox, name='inbox'),
    path('chat/<int:student_id>/', views.chat, name='chat'),
    path('chat/unread/', views.chat_unread_count, name='chat_unread'),

    # Warden ↔ Admin Messaging
    path('warden-inbox/', views.warden_inbox, name='warden_inbox'),
    path('warden-chat/<int:user_id>/', views.warden_chat, name='warden_chat'),

    # Attendance
    path('attendance/', views.attendance_list, name='attendance_list'),
    path('attendance/mark/', views.attendance_mark, name='attendance_mark'),
    path('attendance/report/', views.attendance_report, name='attendance_report'),
    path('attendance/print/daily/', views.attendance_print_daily, name='attendance_print_daily'),
    path('attendance/print/monthly/', views.attendance_print_monthly, name='attendance_print_monthly'),

    # Documents
    path('documents/', views.document_list, name='document_list'),
    path('documents/upload/', views.document_upload, name='document_upload'),
    path('documents/<int:pk>/delete/', views.document_delete, name='document_delete'),
    path('documents/<int:pk>/verify/', views.document_verify, name='document_verify'),

    # Password Reset
    path('password-reset/',
         auth_views.PasswordResetView.as_view(
             template_name='hostelapp/password_reset.html',
             email_template_name='hostelapp/password_reset_email.txt',
             subject_template_name='hostelapp/password_reset_subject.txt',
             success_url='/password-reset/done/'
         ), name='password_reset'),
    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(
             template_name='hostelapp/password_reset_done.html'
         ), name='password_reset_done'),
    path('password-reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='hostelapp/password_reset_confirm.html',
             success_url='/password-reset/complete/'
         ), name='password_reset_confirm'),
    path('password-reset/complete/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='hostelapp/password_reset_complete.html'
         ), name='password_reset_complete'),
]