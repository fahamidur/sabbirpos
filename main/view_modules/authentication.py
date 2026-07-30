"""Authentication views."""

from .common import *
from .common import (
    _load_admin_credentials,
    _save_admin_credentials,
)
def login_view(request):
    if request.session.get("is_logged_in"):
        return redirect("dashboard")

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        creds = _load_admin_credentials()

        # Check credentials
        if hmac.compare_digest(username, creds["username"]) and check_password(password, creds["password_hash"]):
            # Set session variable to track login
            request.session['is_logged_in'] = True
            request.session['username'] = username
            request.session.set_expiry(60 * 60 * 12)  # 12 hours
            return redirect("dashboard")  # Redirect to the dashboard
        else:
            return render(request, "login.html", {"error": "Invalid username or password"})

    return render(request, "login.html")


@require_POST
def request_password_reset_code(request):
    _load_admin_credentials()
    reset_code = f"{random.randint(100000, 999999)}"
    expires_at = (timezone.now() + timedelta(minutes=10)).isoformat()

    request.session["admin_reset_code"] = reset_code
    request.session["admin_reset_email"] = PASSWORD_RESET_EMAIL
    request.session["admin_reset_expires_at"] = expires_at
    request.session["admin_reset_verified"] = False

    try:
        send_mail(
            subject="Rahmaniya Admin Password Reset Code",
            message=f"Your reset code is: {reset_code}\nThis code expires in 10 minutes.",
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[PASSWORD_RESET_EMAIL],
            fail_silently=False,
        )
        messages.success(request, f"Reset code sent to {PASSWORD_RESET_EMAIL}.", extra_tags="auth")
    except Exception as e:
        messages.error(request, f"Could not send reset code email: {e}", extra_tags="auth")

    return redirect("login")


@require_POST
def reset_admin_credentials(request):
    submitted_code = (request.POST.get("code") or "").strip()
    new_username = (request.POST.get("new_username") or "").strip()
    new_password = request.POST.get("new_password") or ""
    confirm_password = request.POST.get("confirm_password") or ""

    session_code = request.session.get("admin_reset_code")
    expires_at_raw = request.session.get("admin_reset_expires_at")

    if not session_code or not expires_at_raw:
        messages.error(request, "Reset code নেই। আগে 'Send Reset Code' চাপুন।", extra_tags="auth")
        return redirect("login")

    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
        if timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())
    except Exception:
        messages.error(request, "Invalid reset session. আবার কোড নিন।", extra_tags="auth")
        return redirect("login")

    if timezone.now() > expires_at:
        messages.error(request, "Reset code expired. নতুন কোড নিন।", extra_tags="auth")
        return redirect("login")

    if not hmac.compare_digest(submitted_code, session_code):
        messages.error(request, "Invalid reset code.", extra_tags="auth")
        return redirect("login")

    if not new_username:
        messages.error(request, "New username is required.", extra_tags="auth")
        return redirect("login")

    if len(new_password) < 6:
        messages.error(request, "Password must be at least 6 characters.", extra_tags="auth")
        return redirect("login")

    if new_password != confirm_password:
        messages.error(request, "Password and confirm password do not match.", extra_tags="auth")
        return redirect("login")

    _save_admin_credentials(new_username, make_password(new_password))
    for key in ("admin_reset_code", "admin_reset_email", "admin_reset_expires_at", "admin_reset_verified"):
        if key in request.session:
            del request.session[key]

    messages.success(request, "Username and password updated successfully. Please login.", extra_tags="auth")
    return redirect("login")


@require_POST
def logout_view(request):
    # Clear session data
    request.session.flush()
    return redirect("login")


@csrf_exempt
def salesman_login(request):
    if request.method == "POST":
        name = request.POST.get("name")
        code = request.POST.get("code")
        
        try:
            salesman = Salesman.objects.get(name=name, code=code)
            request.session['salesman_id'] = salesman.id
            request.session['salesman_name'] = salesman.name
            return redirect('salesman_pos')
        except Salesman.DoesNotExist:
            return render(request, "salesman_login.html", {"error": "Invalid name or code"})
    
    return render(request, "salesman_login.html")


@require_POST
def salesman_logout(request):
    if 'salesman_id' in request.session:
        del request.session['salesman_id']
        del request.session['salesman_name']
    return redirect('salesman_login')


