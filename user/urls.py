from django.urls import path

from .views import (verify_email,
                    verification_alert, verification_resend, logout_view,UserLoginView,UserRegistration,UserPasswordChangeView,
                    UserPasswordResetView,UserPasswordResetConfirmView,)

from django.contrib.auth import views as auth_views

urlpatterns = [

  
    path('email/verify/', verify_email, name='verify-email'),

    path('email/verification/resend/', verification_resend, name='resend-verification'),
    path('email/verification-alert/', verification_alert, name='verification-alert'),

    # Authentication
    path('accounts/login/', UserLoginView.as_view(), name='login'),
    path('accounts/logout/', logout_view, name='logout'),
    path('accounts/register/', UserRegistration.as_view(), name='register'),


    path('accounts/password-change/', UserPasswordChangeView.as_view(), name='password_change'),
    path('accounts/password-change-done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='accounts/password_change_done.html'
    ), name="password_change_done"),
    

    path('accounts/password-reset/', UserPasswordResetView.as_view(), name='password_reset'),
    path('accounts/password-reset-confirm/<uidb64>/<token>/', 
        UserPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('accounts/password-reset-done/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_done.html'
    ), name='password_reset_done'),

  
]
