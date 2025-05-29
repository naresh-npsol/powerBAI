import jwt
from django.urls import reverse, reverse_lazy
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.utils.encoding import force_str
from django.shortcuts import render, redirect,resolve_url
from django.contrib.auth import get_user_model, authenticate, login, logout
from django.contrib.auth.views import (
    LoginView, PasswordResetView, PasswordResetConfirmView, PasswordChangeView
)
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView
from django.contrib.messages.views import SuccessMessageMixin
from django.utils.http import url_has_allowed_host_and_scheme

from .models import User
from .forms import (
    RegistrationForm, LoginForm, UserPasswordResetForm, 
    UserSetPasswordForm, UserPasswordChangeForm, CustomUserCreationForm
)
from utils.token_generator import send_token


# Login View
class UserLoginView(LoginView):
    template_name = 'accounts/sign-in.html'
    form_class = LoginForm

    def form_valid(self, form):
        user = form.get_user()
        login(self.request, user)
        messages.success(self.request, f"Welcome back, {user.email}!")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Invalid credentials. Please try again.")
        return super().form_invalid(form)
    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=self.request.get_host()):
            return next_url
        return resolve_url('dashboard')  # Replace 'dashboard' with the name of your dashboard URL pattern
    
    
# Registration View
class UserRegistration(CreateView):
    template_name = 'accounts/sign-up.html'
    form_class = RegistrationForm
    success_url = "/accounts/login/"

    def form_valid(self, form):
        user = form.save(commit=False)
        user.is_active = False  # User needs email verification
        user.save()
        send_token(user.email)
        messages.success(self.request, "Registration successful! Please verify your email.")
        return redirect(reverse('verification-alert') + f'?email={user.email}')

    def form_invalid(self, form):
        messages.error(self.request, "Registration failed. Please correct the errors below.")
        return super().form_invalid(form)

# Logout View
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('login')

# Password Reset View
class UserPasswordResetView(SuccessMessageMixin, PasswordResetView):
    template_name = 'accounts/password_reset.html'
    form_class = UserPasswordResetForm
    email_template_name = 'accounts/password_reset_email.html'
    success_message = "Password reset instructions have been sent to your email."
    success_url = reverse_lazy('password_reset_done')

# Password Reset Confirm View
class UserPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    form_class = UserSetPasswordForm
    success_url = reverse_lazy('accounts:password_reset_complete')

# Password Change View
class UserPasswordChangeView(SuccessMessageMixin, PasswordChangeView):
    template_name = 'accounts/password_change.html'
    form_class = UserPasswordChangeForm
    success_message = "Your password has been changed successfully."
    success_url = reverse_lazy('password_change_done')

# Email Verification Alert
def verification_alert(request):
    email = request.GET.get('email', '')
    return render(request, 'accounts/verification-alert.html', {'email': email})

# Resend Verification Email
def verification_resend(request):
    if request.method == "POST":
        email = request.POST.get('email')
        user = get_user_model().objects.filter(email=email).first()
        if not user:
            messages.error(request, f"No account found for email: {email}")
        elif user.is_active:
            messages.info(request, f"The email {email} is already active.")
        else:
            send_token(email)
            messages.success(request, f"Verification email resent to {email}.")
            return redirect('verification-alert')
    return render(request, 'accounts/resend-confirmation.html')




#old code

def verification_alert(request):
    """
        alert that the user has to verify their email
    """
    email = request.GET.get('email') or ''
    return render(request, 'html/accounts/verification-alert.html', context={'from_email': settings.EMAIL_HOST,
                                                                'to_email': email   
                                                            })


@require_http_methods(["GET", "POST"])
def verification_resend(request):
    """
        resend the confirmation email
    """

    if request.method == "POST":

        email = request.POST.get('email')

        user = User.objects.filter(email=email)

        if not user.exists():

            return render(request, 'html/accounts/resend-confirmation.html', {'error': f'The email {email} is not registered'})

        if user.filter(is_active=True):
            return render(request, 'html/accounts/resend-confirmation.html', {'error': f'The email {email} is already active'})

        send_token(email)
        url = reverse('verification-alert') + f'?email={email}'
        return redirect(url)

    return render(request, 'html/accounts/resend-confirmation.html')


def verify_email(request):
    token = request.GET.get('token')
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        email = payload['email']

        user = get_user_model().objects.get(email=email)
        user.is_active = True
        user.save()

        send_token(email)

        return redirect('login')  # Redirect to a success page

    except jwt.ExpiredSignatureError:
        return render(request, 'html/authentication/email-verification.html', context={'error': 'Token expired, request another'})

    except (jwt.DecodeError, Exception):
        return render(request, 'html/authentication/email-verification.html', context={'error': 'Unknown error occurred, request a new token'})
    



