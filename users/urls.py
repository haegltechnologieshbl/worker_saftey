from django.urls import path
from . import views

urlpatterns = [
    # Public / shared
    path('', views.HomeView.as_view(), name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('employee-otp/', views.employee_otp, name='employee_otp'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('profile/', views.profile, name='profile'),
    path('profile/update/', views.ProfileUpdateView.as_view(), name='profile-update'),

    # Employee-side
    path('dashboard/', views.employee_dashboard, name='employee_dashboard'),
    path('my/violations/', views.my_violations, name='my_violations'),

    # Admin / manage
    path('manage/', views.manage_dashboard, name='manage_dashboard'),
    path('manage/employees/', views.employee_list, name='employee_list'),
    path('manage/employees/add/', views.employee_add, name='employee_add'),
    path('manage/employees/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('manage/employees/<int:pk>/edit/', views.employee_edit, name='employee_edit'),
    path('manage/employees/<int:pk>/delete/', views.employee_delete, name='employee_delete'),
    path('manage/employees/<int:pk>/reset-password/', views.employee_reset_password, name='employee_reset_password'),
    path('manage/violations/', views.violation_list, name='violation_list'),
    path('manage/violations/search-all/', views.violation_search_all_unknown, name='violation_search_all_unknown'),
    path('manage/violations/delete-all/', views.violations_delete_all, name='violations_delete_all'),
    path('manage/violations/<int:pk>/', views.violation_detail, name='violation_detail'),
    path('manage/violations/<int:pk>/search/', views.violation_search, name='violation_search'),
    path('manage/violations/<int:pk>/send-email/', views.violation_send_email, name='violation_send_email'),
    path('manage/violations/<int:pk>/delete/', views.violation_delete, name='violation_delete'),
    path('manage/leaderboard/', views.leaderboard, name='leaderboard'),

    # Detection
    path('live-detection/', views.live_detection_page, name='live_detection'),
    path('live-detect/', views.live_detect_api, name='live_detect_api'),
    path('video_upload1/', views.video_upload, name='video_upload1'),
    path('video_lists/', views.video_lists, name='video_lists'),
]
